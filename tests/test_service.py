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


@pytest.mark.asyncio
async def test_random_single_result_expands_to_full_recipe() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/recipes/random":
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "picked", "title": "随机菜"}],
                    "meta": {"count": 1, "seed": "x", "total_available": 368},
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": "picked",
                    "title": "随机菜",
                    "ingredients": [],
                    "tools": [],
                    "steps": [],
                }
            },
        )

    client = HowToCookClient("http://cook.test/api", transport=httpx.MockTransport(handler))
    document = await execute_command(client, parse_command("随机 --种子 x"), Config())
    assert document.title == "随机菜"
    assert [request.url.path for request in requests] == [
        "/api/recipes/random",
        "/api/recipes/picked",
    ]


@pytest.mark.asyncio
async def test_aggregate_single_tip_expands_to_tip_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/search":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "recipes": {"total": 0, "items": []},
                        "tips": {
                            "total": 1,
                            "items": [{"id": "tip-one", "title": "厨房安全"}],
                        },
                    },
                    "meta": {"q": "安全"},
                },
            )
        assert request.url.path == "/api/tips/tip-one"
        return httpx.Response(
            200,
            json={"data": {"id": "tip-one", "title": "厨房安全", "content": {}}},
        )

    client = HowToCookClient("http://cook.test/api", transport=httpx.MockTransport(handler))
    document = await execute_command(client, parse_command("全局搜索 安全"), Config())
    assert document.title == "厨房安全"
    assert document.kicker == "HOW TO COOK · KITCHEN TIPS"


@pytest.mark.asyncio
async def test_menu_and_stats_use_dedicated_layouts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/menu":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "meat": [{"id": "m", "title": "肉"}],
                        "vegetable": [{"id": "v", "title": "菜"}],
                        "soup": [{"id": "s", "title": "汤"}],
                    },
                    "meta": {"seed": "x", "unfilled": []},
                },
            )
        assert request.url.path == "/api/stats"
        return httpx.Response(200, json={"data": {"recipes": 3, "tips": 1}})

    client = HowToCookClient("http://cook.test/api", transport=httpx.MockTransport(handler))
    menu = await execute_command(client, parse_command("配餐 --种子 x"), Config())
    stats = await execute_command(client, parse_command("统计"), Config())
    assert menu.layout == "menu"
    assert len(menu.recipe_choices) == 3
    assert stats.layout == "stats"
