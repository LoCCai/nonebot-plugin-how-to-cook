import struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message
from nonebot.adapters.onebot.v11.event import Sender

from nonebot_plugin_how_to_cook import delivery as delivery_module
from nonebot_plugin_how_to_cook.api import HowToCookClient
from nonebot_plugin_how_to_cook.config import Config
from nonebot_plugin_how_to_cook.content import Document, Section
from nonebot_plugin_how_to_cook.delivery import MessageDelivery


class FakeBot:
    self_id = "10001"

    def __init__(self) -> None:
        self.sent = []
        self.api_calls = []
        self.uploads = []

    async def send(self, event, message) -> None:
        self.sent.append((event, message))

    async def call_api(self, api: str, **data) -> None:
        self.api_calls.append((api, data))

    async def upload_group_file(self, *, group_id: int, file: str, name: str) -> None:
        assert Path(file).is_file()
        self.uploads.append((group_id, file, name))


def _event() -> GroupMessageEvent:
    return GroupMessageEvent(
        time=0,
        self_id=10001,
        post_type="message",
        sub_type="normal",
        user_id=20002,
        message_type="group",
        message_id=1,
        message=Message(""),
        original_message=Message(""),
        raw_message="",
        font=0,
        sender=Sender(user_id=20002, nickname="tester"),
        group_id=30003,
    )


def _delivery(config: Config | None = None) -> MessageDelivery:
    client = HowToCookClient(
        "http://cook.test/api",
        transport=httpx.MockTransport(lambda _request: httpx.Response(404)),
    )
    return MessageDelivery(config or Config(), client)


@pytest.mark.asyncio
async def test_combined_mode_sends_summary_then_details() -> None:
    bot = FakeBot()
    document = Document("菜谱", description="摘要", sections=[Section("步骤", "先做第一步")])
    outcome = await _delivery().deliver(bot, _event(), document, mode="combined")  # type: ignore[arg-type]
    assert outcome.messages == 2
    assert len(bot.sent) == 2
    assert "菜谱" in str(bot.sent[0][1])
    assert "步骤" in str(bot.sent[1][1])


@pytest.mark.asyncio
async def test_forward_mode_uses_forward_api(monkeypatch) -> None:
    monkeypatch.setattr(
        delivery_module,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ModuleNotFoundError("src")),
    )
    bot = FakeBot()
    document = Document("菜谱", sections=[Section("步骤", "做饭")])
    outcome = await _delivery().deliver(bot, _event(), document, mode="forward")  # type: ignore[arg-type]
    assert outcome.messages == 1
    assert bot.api_calls[0][0] == "send_group_forward_msg"


@pytest.mark.asyncio
async def test_forward_mode_reuses_qiqi_combined_sender_when_available(monkeypatch) -> None:
    captured = {"prepared": 0}

    async def prepare(message: Message) -> Message:
        captured["prepared"] += 1
        return message

    async def send_combined(bot, event, message) -> None:
        captured.update({"bot": bot, "event": event, "message": message})

    async def lower_level_must_not_run(**_kwargs) -> None:
        raise AssertionError("the unified QIQI sender should own dispatch")

    monkeypatch.setattr(
        delivery_module,
        "import_module",
        lambda _name: SimpleNamespace(
            prepare_exact_delivery_message=prepare,
            send_combined_message=send_combined,
            send_group_forward_msg=lower_level_must_not_run,
        ),
    )
    bot = FakeBot()
    event = _event()
    outcome = await _delivery().deliver(  # type: ignore[arg-type]
        bot,
        event,
        Document("菜谱", sections=[Section("步骤", "做饭")]),
        mode="forward",
    )

    assert outcome.messages == 1
    assert captured["prepared"] == 1
    assert captured["bot"] is bot
    assert captured["event"] is event
    assert captured["message"]["type"] == "forward"
    assert len(captured["message"]["content"]) == 1
    assert bot.api_calls == []


@pytest.mark.asyncio
async def test_forward_gallery_renders_recipe_cards_and_shopping_list(monkeypatch) -> None:
    delivery = _delivery()
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    delivery.renderer.render = AsyncMock(return_value=(fake_png, "light"))  # type: ignore[method-assign]
    monkeypatch.setattr(
        delivery_module,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ModuleNotFoundError("src")),
    )
    bot = FakeBot()
    documents = [
        Document("宫保鸡丁"),
        Document("炒青菜"),
        Document("采购清单", layout="shopping_list"),
    ]

    outcome = await delivery.deliver_forward_gallery(  # type: ignore[arg-type]
        bot,
        _event(),
        documents,
        title="今日配餐",
        theme="light",
    )

    assert outcome.mode == "forward"
    assert outcome.messages == 1
    assert bot.api_calls[0][0] == "send_group_forward_msg"
    nodes = bot.api_calls[0][1]["messages"]
    assert len(nodes) == 4
    assert "2 道完整菜谱卡" in str(nodes[0])
    assert "宫保鸡丁" in str(nodes[1])
    assert "购物清单" in str(nodes[-1])
    assert all("image" in str(node) for node in nodes[1:])


@pytest.mark.asyncio
async def test_large_render_is_uploaded_as_group_file() -> None:
    config = Config(how_to_cook_large_image_height=1000)
    delivery = _delivery(config)
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 10, 1001)
    delivery.renderer.render = AsyncMock(return_value=(fake_png, "light"))  # type: ignore[method-assign]
    bot = FakeBot()
    outcome = await delivery.deliver(bot, _event(), Document("超长菜谱"), mode="render")  # type: ignore[arg-type]
    assert outcome.uploaded_group_file is True
    assert len(bot.uploads) == 1
    assert bot.uploads[0][2] == "how-to-cook.png"
    assert not Path(bot.uploads[0][1]).exists()
