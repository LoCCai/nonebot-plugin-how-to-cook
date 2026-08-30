from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import import_module

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot_plugin_waiter import waiter

_CANCEL_WORDS = {"取消", "算了", "退出", "cancel", "quit", "q"}
_SHOPPING_RE = re.compile(r"^(?:购物清单|采购清单|买菜清单)(?:\s*(\d+)\s*(?:人份?|份)?)?$", re.I)


@dataclass(frozen=True, slots=True)
class ShoppingListSelection:
    servings: int | None = None


def parse_selection(
    value: str,
    result_count: int,
    *,
    allow_shopping_list: bool = False,
) -> int | ShoppingListSelection | None:
    text = value.strip().casefold()
    if text in _CANCEL_WORDS:
        return -1
    if allow_shopping_list:
        matched = _SHOPPING_RE.fullmatch(text)
        if matched:
            servings = int(matched.group(1)) if matched.group(1) else None
            if servings is None or 1 <= servings <= 100:
                return ShoppingListSelection(servings)
            return None
    if not text.isdigit():
        return None
    selected = int(text) - 1
    return selected if 0 <= selected < result_count else None


async def send_transient_notice(
    bot: Bot,
    event: MessageEvent,
    message: str,
    *,
    delay: int,
) -> None:
    """Use QIQI's reminder sender when available, with a portable fallback."""

    try:
        module = import_module("src.utils.message_fx")
        sender = module.send_with_auto_recall
    except Exception as exc:
        logger.debug(f"QIQI 自动撤回组件不可用，发送普通提示：{type(exc).__name__}")
        await bot.send(event, message)
        return

    await sender(
        bot=bot,
        event=event,
        message=message,
        delay=delay,
        at_sender=True,
    )


async def wait_for_selection(
    result_count: int,
    *,
    timeout: int,
    allow_shopping_list: bool = False,
) -> int | ShoppingListSelection | None:
    @waiter(waits=["message"], keep_session=True)
    async def selection_waiter(reply: MessageEvent) -> int | ShoppingListSelection | None:
        return parse_selection(
            reply.get_plaintext(),
            result_count,
            allow_shopping_list=allow_shopping_list,
        )

    return await selection_waiter.wait(timeout=timeout)


# Backward-compatible names for callers that imported the 0.1 API.
parse_recipe_selection = parse_selection
wait_for_recipe_selection = wait_for_selection
