import httpx
import pytest

from nonebot_plugin_how_to_cook.api import HowToCookClient
from nonebot_plugin_how_to_cook.commands import CommandError, parse_command
from nonebot_plugin_how_to_cook.config import Config
from nonebot_plugin_how_to_cook.service import execute_command


@pytest.mark.asyncio
async def test_search_service_applies_defaults() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"data": [], "meta": {"total": 0, "page": 1, "pages": 1, "q": "肉"}},
        )

    client = HowToCookClient("http://cook.test/api", transport=httpx.MockTransport(handler))
    document = await execute_command(client, parse_command("搜索 肉"), Config())
    assert document.title == "菜谱搜索结果"
    assert requests[0].url.params["page_size"] == "8"
    assert requests[0].url.params["image_mode"] == "server"


@pytest.mark.asyncio
async def test_single_search_result_returns_recipe_detail_directly() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/recipes":
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "only-one", "title": "唯一菜谱"}],
                    "meta": {"total": 1, "page": 1, "pages": 1, "q": "唯一"},
                },
            )
        assert request.url.path == "/api/recipes/only-one"
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": "only-one",
                    "title": "唯一菜谱",
                    "ingredients": [],
                    "tools": [],
                    "steps": [],
                },
                "meta": {},
            },
        )

    client = HowToCookClient("http://cook.test/api", transport=httpx.MockTransport(handler))
    document = await execute_command(client, parse_command("搜索 唯一"), Config())

    assert document.title == "唯一菜谱"
    assert document.layout == "article"
    assert document.recipe_choices == []
    assert len(requests) == 2
    assert requests[1].url.params["image_mode"] == "server"


@pytest.mark.asyncio
async def test_multiple_search_results_keep_choices_for_waiter() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "first", "title": "第一道菜"},
                    {"id": "second", "title": "第二道菜"},
                ],
                "meta": {"total": 2, "page": 1, "pages": 1, "q": "菜"},
            },
        )

    client = HowToCookClient("http://cook.test/api", transport=httpx.MockTransport(handler))
    document = await execute_command(client, parse_command("搜索 菜"), Config())

    assert [choice.identifier for choice in document.recipe_choices] == ["first", "second"]


@pytest.mark.asyncio
async def test_service_caps_bot_page_size() -> None:
    client = HowToCookClient(
        "http://cook.test/api",
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
    )
    with pytest.raises(CommandError, match="每页最多"):
        await execute_command(client, parse_command("搜索 肉 --每页 21"), Config())
