import pytest
from nonebot.adapters.onebot.v11 import Message

from nonebot_plugin_how_to_cook import matcher
from nonebot_plugin_how_to_cook.content import Document, RecipeListItem


@pytest.mark.asyncio
async def test_multiple_search_results_deliver_list_then_selected_detail(monkeypatch) -> None:
    client = object()
    delivery = object()
    search_document = Document(
        "搜索结果",
        layout="recipe_list",
        recipe_choices=[
            RecipeListItem("first", "第一道菜"),
            RecipeListItem("second", "第二道菜"),
        ],
    )
    detail_document = Document("第二道菜详情")
    delivered = []
    notices = []
    fetched = []

    async def fake_execute(*_args):
        return search_document

    async def fake_deliver(_delivery, _bot, _event, document, **kwargs):
        delivered.append((document, kwargs))
        return True

    async def fake_notice(_bot, _event, message, *, delay):
        notices.append((message, delay))

    async def fake_wait(result_count, *, timeout):
        assert result_count == 2
        assert timeout == 120
        return 1

    async def fake_fetch(_client, choice, *, image_mode):
        fetched.append((choice.identifier, choice.kind, image_mode))
        return detail_document

    monkeypatch.setattr(matcher, "_client", lambda: client)
    monkeypatch.setattr(matcher, "execute_command", fake_execute)
    monkeypatch.setattr(matcher, "MessageDelivery", lambda *_args: delivery)
    monkeypatch.setattr(matcher, "_deliver_document", fake_deliver)
    monkeypatch.setattr(matcher, "send_transient_notice", fake_notice)
    monkeypatch.setattr(matcher, "wait_for_selection", fake_wait)
    monkeypatch.setattr(matcher, "fetch_selection_document", fake_fetch)

    await matcher.handle_how_to_cook(  # type: ignore[arg-type]
        object(),
        object(),
        Message("搜索 菜"),
    )

    assert [item[0] for item in delivered] == [search_document, detail_document]
    assert delivered[0][1] == {"mode": "render", "theme": None}
    assert fetched == [("second", "recipe", "server")]
    assert len(notices) == 1
    assert "1–2" in notices[0][0]
    assert notices[0][1] == 15
