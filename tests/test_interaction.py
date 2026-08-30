from types import SimpleNamespace

import pytest

from nonebot_plugin_how_to_cook import interaction
from nonebot_plugin_how_to_cook.interaction import (
    DetailBundleSelection,
    ShoppingListSelection,
    parse_recipe_selection,
    parse_selection,
    send_transient_notice,
    wait_for_recipe_selection,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", 0), (" 3 ", 2), ("取消", -1), ("cancel", -1), ("0", None), ("4", None)],
)
def test_parse_recipe_selection(value: str, expected: int | None) -> None:
    assert parse_recipe_selection(value, 3) == expected


def test_plan_selection_can_request_a_scaled_shopping_list() -> None:
    assert parse_selection("购物清单", 21, allow_shopping_list=True) == ShoppingListSelection()
    assert parse_selection("购物清单 4人", 21, allow_shopping_list=True) == ShoppingListSelection(4)
    assert parse_selection("购物清单 101", 21, allow_shopping_list=True) is None
    assert parse_selection("购物清单", 21) is None


def test_plan_selection_can_request_forward_detail_bundles() -> None:
    options = {
        "allow_detail_bundle": True,
        "detail_group_count": 7,
        "allow_full_bundle": True,
    }
    assert parse_selection("合并详情", 21, **options) == DetailBundleSelection()
    assert parse_selection("全部详情 4人", 21, **options) == DetailBundleSelection(servings=4)
    assert parse_selection("第1天", 21, **options) == DetailBundleSelection(group_index=0)
    assert parse_selection("7日 6份", 21, **options) == DetailBundleSelection(
        group_index=6,
        servings=6,
    )
    assert parse_selection("第8天", 21, **options) is None
    assert parse_selection("全部详情 101", 21, **options) is None
    assert parse_selection("全部详情", 21, allow_detail_bundle=True) is None


@pytest.mark.asyncio
async def test_waiter_keeps_session_and_returns_valid_index(monkeypatch) -> None:
    captured = {}

    class Reply:
        def get_plaintext(self) -> str:
            return "2"

    class FakeWaiter:
        def __init__(self, handler) -> None:
            self.handler = handler

        async def wait(self, *, timeout: int):
            captured["timeout"] = timeout
            return await self.handler(Reply())

    def fake_waiter(**kwargs):
        captured.update(kwargs)
        return FakeWaiter

    monkeypatch.setattr(interaction, "waiter", fake_waiter)

    assert await wait_for_recipe_selection(3, timeout=120) == 1
    assert captured["waits"] == ["message"]
    assert captured["keep_session"] is True
    assert captured["timeout"] == 120


@pytest.mark.asyncio
async def test_qiqi_notice_uses_shared_auto_recall(monkeypatch) -> None:
    captured = {}

    async def sender(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(
        interaction,
        "import_module",
        lambda _name: SimpleNamespace(send_with_auto_recall=sender),
    )

    bot = object()
    event = object()
    await send_transient_notice(bot, event, "请选择序号", delay=15)  # type: ignore[arg-type]

    assert captured == {
        "bot": bot,
        "event": event,
        "message": "请选择序号",
        "delay": 15,
        "at_sender": True,
    }


@pytest.mark.asyncio
async def test_notice_has_portable_plain_send_fallback(monkeypatch) -> None:
    class FakeBot:
        def __init__(self) -> None:
            self.sent = []

        async def send(self, event, message) -> None:
            self.sent.append((event, message))

    def unavailable(_name: str):
        raise ModuleNotFoundError("src")

    monkeypatch.setattr(interaction, "import_module", unavailable)
    bot = FakeBot()
    event = object()

    await send_transient_notice(bot, event, "请选择序号", delay=15)  # type: ignore[arg-type]

    assert bot.sent == [(event, "请选择序号")]
