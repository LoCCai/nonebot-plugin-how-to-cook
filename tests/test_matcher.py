import asyncio

import pytest
from nonebot.adapters.onebot.v11 import Message

from nonebot_plugin_how_to_cook import matcher
from nonebot_plugin_how_to_cook.content import ChoiceGroup, Document, RecipeListItem
from nonebot_plugin_how_to_cook.interaction import DetailBundleSelection, ShoppingListSelection


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

    async def fake_wait(
        result_count,
        *,
        timeout,
        allow_shopping_list,
        allow_detail_bundle,
        detail_group_count,
        allow_full_bundle,
    ):
        assert result_count == 2
        assert timeout == 120
        assert allow_shopping_list is False
        assert allow_detail_bundle is False
        assert detail_group_count == 0
        assert allow_full_bundle is False
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


@pytest.mark.asyncio
async def test_menu_waiter_can_build_shopping_list_for_all_dishes(monkeypatch) -> None:
    client = object()
    delivery = object()
    menu_document = Document(
        "配餐",
        layout="menu",
        recipe_choices=[
            RecipeListItem("first", "第一道菜"),
            RecipeListItem("second", "第二道菜"),
        ],
        shopping_recipe_ids=["first", "second"],
    )
    shopping_document = Document("采购清单", layout="shopping_list")
    delivered = []
    fetched = []

    async def fake_execute(*_args):
        return menu_document

    async def fake_deliver(_delivery, _bot, _event, document, **_kwargs):
        delivered.append(document)
        return True

    async def fake_notice(*_args, **_kwargs):
        return None

    async def fake_wait(
        result_count,
        *,
        timeout,
        allow_shopping_list,
        allow_detail_bundle,
        detail_group_count,
        allow_full_bundle,
    ):
        assert result_count == 2
        assert timeout == 120
        assert allow_shopping_list is True
        assert allow_detail_bundle is True
        assert detail_group_count == 0
        assert allow_full_bundle is True
        return ShoppingListSelection(4)

    async def fake_shopping(_client, identifiers, *, servings):
        fetched.append((identifiers, servings))
        return shopping_document

    monkeypatch.setattr(matcher, "_client", lambda: client)
    monkeypatch.setattr(matcher, "execute_command", fake_execute)
    monkeypatch.setattr(matcher, "MessageDelivery", lambda *_args: delivery)
    monkeypatch.setattr(matcher, "_deliver_document", fake_deliver)
    monkeypatch.setattr(matcher, "send_transient_notice", fake_notice)
    monkeypatch.setattr(matcher, "wait_for_selection", fake_wait)
    monkeypatch.setattr(matcher, "fetch_shopping_list_document", fake_shopping)

    await matcher.handle_how_to_cook(  # type: ignore[arg-type]
        object(),
        object(),
        Message("配餐"),
    )

    assert delivered == [menu_document, shopping_document]
    assert fetched == [(["first", "second"], 4)]


@pytest.mark.asyncio
async def test_week_waiter_reuses_matching_embedded_shopping_list(monkeypatch) -> None:
    client = object()
    delivery = object()
    embedded = Document("上游内嵌采购清单", layout="shopping_list")
    week_document = Document(
        "周计划",
        layout="week_plan",
        recipe_choices=[RecipeListItem("first", "第一道菜"), RecipeListItem("second", "第二道菜")],
        embedded_shopping_list=embedded,
        shopping_servings=4,
    )
    delivered = []

    async def fake_execute(*_args):
        return week_document

    async def fake_deliver(_delivery, _bot, _event, document, **_kwargs):
        delivered.append(document)
        return True

    async def fake_notice(*_args, **_kwargs):
        return None

    async def fake_wait(*_args, **_kwargs):
        # No repeated serving count: inherit --人数 4 from the plan command.
        return ShoppingListSelection()

    async def unexpected_fetch(*_args, **_kwargs):
        raise AssertionError("matching embedded shopping list must avoid a second API request")

    monkeypatch.setattr(matcher, "_client", lambda: client)
    monkeypatch.setattr(matcher, "execute_command", fake_execute)
    monkeypatch.setattr(matcher, "MessageDelivery", lambda *_args: delivery)
    monkeypatch.setattr(matcher, "_deliver_document", fake_deliver)
    monkeypatch.setattr(matcher, "send_transient_notice", fake_notice)
    monkeypatch.setattr(matcher, "wait_for_selection", fake_wait)
    monkeypatch.setattr(matcher, "fetch_shopping_list_document", unexpected_fetch)

    await matcher.handle_how_to_cook(  # type: ignore[arg-type]
        object(),
        object(),
        Message("周计划 --人数 4"),
    )

    assert delivered == [week_document, embedded]


@pytest.mark.asyncio
async def test_week_waiter_can_send_one_day_as_rendered_forward_bundle(monkeypatch) -> None:
    client = object()
    delivery = object()
    first_day = [
        RecipeListItem("meat", "荤菜"),
        RecipeListItem("vegetable", "素菜"),
        RecipeListItem("soup", "汤"),
    ]
    second_day = [RecipeListItem("next", "第二天")]
    week_document = Document(
        "周计划",
        layout="week_plan",
        recipe_choices=[*first_day, *second_day],
        choice_groups=[
            ChoiceGroup("day-1", "第 1 天", "01", first_day),
            ChoiceGroup("day-2", "第 2 天", "02", second_day),
        ],
        shopping_recipe_ids=["meat", "vegetable", "soup", "next"],
    )
    bundle_documents = [Document("荤菜详情"), Document("素菜详情"), Document("汤详情")]
    delivered = []
    fetched = []

    async def fake_execute(*_args):
        return week_document

    async def fake_deliver(_delivery, _bot, _event, document, **_kwargs):
        delivered.append(document)
        return True

    async def fake_notice(*_args, **_kwargs):
        return None

    async def fake_wait(_result_count, **kwargs):
        assert kwargs["allow_detail_bundle"] is True
        assert kwargs["detail_group_count"] == 2
        assert kwargs["allow_full_bundle"] is True
        return DetailBundleSelection(group_index=0, servings=4)

    async def fake_bundle(_client, choices, **kwargs):
        fetched.append(([choice.identifier for choice in choices], kwargs))
        return bundle_documents

    async def fake_gallery(_delivery, _bot, _event, documents, **kwargs):
        delivered.extend(documents)
        assert kwargs["title"] == "周计划 · 第 1 天 · 4 人份"
        return True

    monkeypatch.setattr(matcher, "_client", lambda: client)
    monkeypatch.setattr(matcher, "execute_command", fake_execute)
    monkeypatch.setattr(matcher, "MessageDelivery", lambda *_args: delivery)
    monkeypatch.setattr(matcher, "_deliver_document", fake_deliver)
    monkeypatch.setattr(matcher, "_deliver_forward_gallery", fake_gallery)
    monkeypatch.setattr(matcher, "send_transient_notice", fake_notice)
    monkeypatch.setattr(matcher, "wait_for_selection", fake_wait)
    monkeypatch.setattr(matcher, "fetch_detail_bundle_documents", fake_bundle)

    await matcher.handle_how_to_cook(  # type: ignore[arg-type]
        object(),
        object(),
        Message("周计划"),
    )

    assert delivered == [week_document, *bundle_documents]
    assert fetched[0][0] == ["meat", "vegetable", "soup"]
    assert fetched[0][1]["servings"] == 4
    assert fetched[0][1]["image_mode"] == "server"


@pytest.mark.asyncio
async def test_forward_mode_sends_plan_as_rich_bundle_immediately(monkeypatch) -> None:
    client = object()
    delivery = object()
    choices = [RecipeListItem("one", "一"), RecipeListItem("two", "二")]
    menu_document = Document(
        "配餐",
        layout="menu",
        recipe_choices=choices,
        shopping_recipe_ids=["one", "two"],
    )
    bundle_documents = [Document("一详情"), Document("二详情")]
    calls = []

    async def fake_execute(*_args):
        return menu_document

    async def fake_notice(*_args, **_kwargs):
        return None

    async def fake_bundle(_client, selected, **kwargs):
        calls.append((selected, kwargs))
        return bundle_documents

    async def fake_gallery(_delivery, _bot, _event, documents, **kwargs):
        calls.append((documents, kwargs))
        return True

    monkeypatch.setattr(matcher, "_client", lambda: client)
    monkeypatch.setattr(matcher, "execute_command", fake_execute)
    monkeypatch.setattr(matcher, "MessageDelivery", lambda *_args: delivery)
    monkeypatch.setattr(matcher, "send_transient_notice", fake_notice)
    monkeypatch.setattr(matcher, "fetch_detail_bundle_documents", fake_bundle)
    monkeypatch.setattr(matcher, "_deliver_forward_gallery", fake_gallery)

    await matcher.handle_how_to_cook(  # type: ignore[arg-type]
        object(),
        object(),
        Message("配餐 --模式 合并"),
    )

    assert calls[0][0] == choices
    assert calls[1][0] == bundle_documents
    assert calls[1][1]["title"] == "配餐 · 整桌详情"


@pytest.mark.asyncio
async def test_new_plan_supersedes_older_waiter_for_same_session(monkeypatch) -> None:
    client = object()
    delivery = object()
    bot = object()
    event = object()
    plan = Document(
        "配餐",
        layout="menu",
        recipe_choices=[
            RecipeListItem("first", "第一道菜"),
            RecipeListItem("second", "第二道菜"),
        ],
        shopping_recipe_ids=["first", "second"],
    )
    first_waiting = asyncio.Event()
    both_waiting = asyncio.Event()
    release_reply = asyncio.Event()
    wait_count = 0
    notices: list[str] = []
    bundle_calls = 0
    gallery_calls = 0

    async def fake_execute(*_args):
        return plan

    async def fake_deliver(*_args, **_kwargs):
        return True

    async def fake_notice(_bot, _event, message, **_kwargs):
        notices.append(message)

    async def fake_wait(*_args, **_kwargs):
        nonlocal wait_count
        wait_count += 1
        if wait_count == 1:
            first_waiting.set()
        elif wait_count == 2:
            both_waiting.set()
        await release_reply.wait()
        return DetailBundleSelection()

    async def fake_bundle(*_args, **_kwargs):
        nonlocal bundle_calls
        bundle_calls += 1
        return [Document("第一道菜详情")]

    async def fake_gallery(*_args, **_kwargs):
        nonlocal gallery_calls
        gallery_calls += 1
        return True

    monkeypatch.setattr(matcher, "_client", lambda: client)
    monkeypatch.setattr(matcher, "execute_command", fake_execute)
    monkeypatch.setattr(matcher, "MessageDelivery", lambda *_args: delivery)
    monkeypatch.setattr(matcher, "_deliver_document", fake_deliver)
    monkeypatch.setattr(matcher, "send_transient_notice", fake_notice)
    monkeypatch.setattr(matcher, "wait_for_selection", fake_wait)
    monkeypatch.setattr(matcher, "fetch_detail_bundle_documents", fake_bundle)
    monkeypatch.setattr(matcher, "_deliver_forward_gallery", fake_gallery)

    older = asyncio.create_task(
        matcher.handle_how_to_cook(bot, event, Message("配餐"))  # type: ignore[arg-type]
    )
    await first_waiting.wait()
    newer = asyncio.create_task(
        matcher.handle_how_to_cook(bot, event, Message("配餐"))  # type: ignore[arg-type]
    )
    await both_waiting.wait()
    release_reply.set()
    await asyncio.gather(older, newer)

    assert wait_count == 2
    assert bundle_calls == 1
    assert gallery_calls == 1
    assert sum("正在生成整桌详情" in message for message in notices) == 1
    assert matcher._active_selection_sessions == {}
