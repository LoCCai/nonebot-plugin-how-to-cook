from __future__ import annotations

import asyncio
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.exception import ActionFailed

from .api import HowToCookAPIError, HowToCookClient
from .config import Config, ResponseMode, ThemeMode
from .content import Document, split_text
from .render import CardRenderer, png_dimensions


class DeliveryError(RuntimeError):
    pass


class DeliveryResultUnknown(RuntimeError):
    """A network failure happened after an irreversible OneBot call started."""


@dataclass(slots=True)
class DeliveryOutcome:
    mode: ResponseMode
    messages: int = 0
    uploaded_group_file: bool = False
    rendered_bytes: int = 0


def _details(document: Document) -> str:
    full = document.full_text()
    summary = document.summary_text()
    if full.startswith(summary):
        return full[len(summary) :].strip()
    return full


def _summary_message(document: Document, cover: bytes | None) -> Message:
    message = Message(MessageSegment.text(document.summary_text()))
    if cover:
        message.append(MessageSegment.image(cover))
    return message


def _single_message(document: Document, cover: bytes | None) -> Message:
    message = _summary_message(document, cover)
    details = _details(document)
    if details:
        message.append(MessageSegment.text(f"\n\n{details}"))
    return message


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "-", value).strip(" .-")
    return (cleaned[:80] or "HowToCook-菜谱") + ".png"


def _write_private_png(data: bytes) -> Path:
    descriptor, name = tempfile.mkstemp(prefix="how-to-cook-", suffix=".png")
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        os.close(descriptor)
        Path(name).unlink(missing_ok=True)
        raise
    return Path(name)


class MessageDelivery:
    def __init__(self, config: Config, client: HowToCookClient) -> None:
        self.config = config
        self.client = client
        self.renderer = CardRenderer(config)

    async def _cover(self, document: Document) -> bytes | None:
        if document.attachment and (document.attachment_content_type or "").startswith("image/"):
            return document.attachment
        if not document.cover_url:
            return None
        try:
            return await self.client.fetch_image(document.cover_url)
        except HowToCookAPIError as exc:
            logger.warning(f"HowToCook 成品图下载失败，继续发送文本：{exc.code} {exc.message}")
            return None

    async def _send_forward(
        self,
        bot: Bot,
        event: MessageEvent,
        document: Document,
        cover: bytes | None,
    ) -> int:
        chunks = split_text(document.full_text(), self.config.how_to_cook_forward_node_size)
        if not chunks:
            chunks = [document.summary_text()]
        messages: list[MessageSegment] = []
        author_id = int(bot.self_id) if str(bot.self_id).isdigit() else int(event.user_id)
        for index, chunk in enumerate(chunks):
            content = Message(MessageSegment.text(chunk))
            if index == 0 and cover:
                content.append(MessageSegment.image(cover))
            messages.append(
                MessageSegment.node_custom(
                    user_id=author_id,
                    nickname=self.config.how_to_cook_forward_name,
                    content=content,
                )
            )
        try:
            if isinstance(event, GroupMessageEvent):
                await bot.call_api(
                    "send_group_forward_msg",
                    group_id=event.group_id,
                    messages=messages,
                )
            else:
                await bot.call_api(
                    "send_private_forward_msg",
                    user_id=event.user_id,
                    messages=messages,
                )
        except ActionFailed:
            # The platform explicitly rejected the forward message, so a normal
            # message fallback cannot duplicate an accepted forward.
            count = 0
            for index, chunk in enumerate(chunks):
                message = Message(MessageSegment.text(chunk))
                if index == 0 and cover:
                    message.append(MessageSegment.image(cover))
                await bot.send(event, message)
                count += 1
            return count
        return 1

    async def _send_combined(
        self,
        bot: Bot,
        event: MessageEvent,
        document: Document,
        cover: bytes | None,
    ) -> int:
        await bot.send(event, _summary_message(document, cover))
        count = 1
        details = _details(document)
        for chunk in split_text(details, self.config.how_to_cook_message_chunk_size):
            await bot.send(event, Message(MessageSegment.text(chunk)))
            count += 1
        return count

    async def _upload_render(
        self,
        bot: Bot,
        event: GroupMessageEvent,
        document: Document,
        image: bytes,
    ) -> None:
        path = await asyncio.to_thread(_write_private_png, image)
        try:
            await bot.upload_group_file(
                group_id=event.group_id,
                file=str(path),
                name=_safe_filename(document.filename_hint),
            )
        except ActionFailed as exc:
            raise DeliveryError(f"长图转群文件失败：{exc}") from exc
        except Exception as exc:
            raise DeliveryResultUnknown("长图群文件是否已被 OneBot 接收未知") from exc
        finally:
            path.unlink(missing_ok=True)

    def _is_large_render(self, image: bytes) -> bool:
        if len(image) > self.config.how_to_cook_large_image_bytes:
            return True
        dimensions = png_dimensions(image)
        return bool(dimensions and dimensions[1] > self.config.how_to_cook_large_image_height)

    async def _deliver_non_render(
        self,
        bot: Bot,
        event: MessageEvent,
        document: Document,
        mode: ResponseMode,
        cover: bytes | None,
    ) -> DeliveryOutcome:
        if mode == "single":
            await bot.send(event, _single_message(document, cover))
            return DeliveryOutcome(mode=mode, messages=1)
        if mode == "combined":
            count = await self._send_combined(bot, event, document, cover)
            return DeliveryOutcome(mode=mode, messages=count)
        count = await self._send_forward(bot, event, document, cover)
        return DeliveryOutcome(mode="forward", messages=count)

    async def deliver(
        self,
        bot: Bot,
        event: MessageEvent,
        document: Document,
        *,
        mode: ResponseMode,
        theme: ThemeMode | None = None,
    ) -> DeliveryOutcome:
        cover = await self._cover(document)
        if mode != "render":
            return await self._deliver_non_render(bot, event, document, mode, cover)
        try:
            image, _selected_theme = await self.renderer.render(
                document,
                theme=theme,
                cover_bytes=cover,
            )
        except Exception:
            logger.exception("HowToCook HTML 渲染失败，使用配置的文本消息模式降级")
            return await self._deliver_non_render(
                bot,
                event,
                document,
                self.config.how_to_cook_render_fallback_mode,
                cover,
            )

        if (
            self._is_large_render(image)
            and isinstance(event, GroupMessageEvent)
            and self.config.how_to_cook_upload_large_group_file
        ):
            await self._upload_render(bot, event, document, image)
            return DeliveryOutcome(
                mode="render",
                uploaded_group_file=True,
                rendered_bytes=len(image),
            )
        await bot.send(event, Message(MessageSegment.image(image)))
        return DeliveryOutcome(mode="render", messages=1, rendered_bytes=len(image))
