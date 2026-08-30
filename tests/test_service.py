import httpx
import pytest

from nonebot_plugin_how_to_cook.api import HowToCookClient
from nonebot_plugin_how_to_cook.commands import CommandError, parse_command
from nonebot_plugin_how_to_cook.config import Config
from nonebot_plugin_how_to_cook.content import Document, RecipeListItem
from nonebot_plugin_how_to_cook.service import execute_command, fetch_detail_bundle_documents


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
            assert "servings" not in request.url.params
            assert request.url.params["breakfast"] == "1"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "meat": [{"id": "m", "title": "肉"}],
                        "vegetable": [{"id": "v", "title": "菜"}],
                        "soup": [{"id": "s", "title": "汤"}],
                        "breakfast": [{"id": "b", "title": "早餐"}],
                        "drink": [],
                        "dessert": [],
                    },
                    "meta": {"seed": "x", "unfilled": []},
                },
            )
        assert request.url.path == "/api/stats"
        return httpx.Response(200, json={"data": {"recipes": 3, "tips": 1}})

    client = HowToCookClient("http://cook.test/api", transport=httpx.MockTransport(handler))
    menu = await execute_command(client, parse_command("配餐 --早餐 1 --人数 4 --种子 x"), Config())
    stats = await execute_command(client, parse_command("统计"), Config())
    assert menu.layout == "menu"
    assert len(menu.recipe_choices) == 4
    assert stats.layout == "stats"


@pytest.mark.asyncio
async def test_week_plan_uses_live_contract_and_keeps_choices() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "days": [
                        {
                            "day": 1,
                            "meat": [{"id": "m", "title": "肉"}],
                            "vegetable": [{"id": "v", "title": "菜"}],
                            "soup": [],
                            "breakfast": [{"id": "b", "title": "早餐"}],
                            "drink": [],
                            "dessert": [],
                        }
                    ],
                    "shopping_list": {"items": [], "recipes": [], "not_found": []},
                },
                "meta": {
                    "seed": "week",
                    "days": 1,
                    "exclude_tags": ["seafood"],
                    "repeats": False,
                    "slots": {
                        "meat": [1],
                        "vegetable": [1],
                        "soup": [0],
                        "breakfast": [1],
                        "drink": [0],
                        "dessert": [0],
                    },
                    "shopping_list": {"items": 0, "servings": 4, "scaled": True},
                },
            },
        )

    client = HowToCookClient("http://cook.test/api", transport=httpx.MockTransport(handler))
    document = await execute_command(
        client,
        parse_command("周计划 1 --荤 1,2 --汤 0 --早餐 1 --人数 4 --忌口 海鲜 --种子 week"),
        Config(),
    )
    assert document.layout == "week_plan"
    assert [choice.identifier for choice in document.recipe_choices] == ["m", "v", "b"]
    assert requests[0].url.path == "/api/plan/week"
    assert requests[0].url.params["exclude_tags"] == "seafood"
    assert requests[0].url.params["meat"] == "1,2"
    assert requests[0].url.params["breakfast"] == "1"
    assert requests[0].url.params["with_shopping_list"] == "1"
    assert requests[0].url.params["servings"] == "4"
    assert document.embedded_shopping_list is not None


@pytest.mark.asyncio
async def test_shopping_list_resolves_exact_titles_then_posts() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/recipes":
            title = request.url.params["q"]
            identifier = "a" * 10 if title == "宫保鸡丁" else "b" * 10
            return httpx.Response(
                200,
                json={"data": [{"id": identifier, "title": title}], "meta": {"total": 1}},
            )
        assert request.method == "POST"
        assert request.url.path == "/api/shopping-list"
        return httpx.Response(
            200,
            json={
                "data": {
                    "items": [
                        {
                            "name": "鸡蛋",
                            "display_names": ["鸡蛋"],
                            "amounts": [{"value": 4, "unit": "个", "scaled": True}],
                            "unspecified": [],
                            "recipes": ["炒滑蛋"],
                        }
                    ],
                    "recipes": [
                        {"id": "a" * 10, "title": "宫保鸡丁"},
                        {"id": "b" * 10, "title": "炒滑蛋"},
                    ],
                    "not_found": [],
                },
                "meta": {"requested": 2, "servings": 4},
            },
        )

    client = HowToCookClient("http://cook.test/api", transport=httpx.MockTransport(handler))
    document = await execute_command(
        client,
        parse_command("购物清单 宫保鸡丁,炒滑蛋 --份数 4"),
        Config(),
    )
    assert document.layout == "shopping_list"
    assert requests[-1].method == "POST"
    assert requests[-1].url.params["ids"] == f"{'a' * 10},{'b' * 10}"
    assert requests[-1].url.params["servings"] == "4"


@pytest.mark.asyncio
async def test_detail_bundle_fetches_full_recipes_and_matching_shopping_list() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.startswith("/api/recipes/"):
            identifier = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200,
                json={
                    "data": {
                        "id": identifier,
                        "title": f"菜谱 {identifier}",
                        "ingredients": [],
                        "tools": [],
                        "steps": [],
                    }
                },
            )
        assert request.url.path == "/api/shopping-list"
        return httpx.Response(
            200,
            json={
                "data": {
                    "items": [],
                    "recipes": [
                        {"id": "first", "title": "第一道菜"},
                        {"id": "second", "title": "第二道菜"},
                    ],
                    "not_found": [],
                },
                "meta": {"servings": 4},
            },
        )

    client = HowToCookClient("http://cook.test/api", transport=httpx.MockTransport(handler))
    documents = await fetch_detail_bundle_documents(
        client,
        [RecipeListItem("first", "第一道菜"), RecipeListItem("second", "第二道菜")],
        image_mode="server",
        servings=4,
        concurrency=2,
    )

    assert [document.title for document in documents] == [
        "菜谱 first",
        "菜谱 second",
        "七七采购清单",
    ]
    assert requests[-1].method == "POST"
    assert requests[-1].url.params["ids"] == "first,second"
    assert requests[-1].url.params["servings"] == "4"


@pytest.mark.asyncio
async def test_detail_bundle_reuses_embedded_week_shopping_list() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/recipes/first"
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": "first",
                    "title": "第一道菜",
                    "ingredients": [],
                    "tools": [],
                    "steps": [],
                }
            },
        )

    client = HowToCookClient("http://cook.test/api", transport=httpx.MockTransport(handler))
    embedded = Document("上游内嵌采购清单", layout="shopping_list")
    documents = await fetch_detail_bundle_documents(
        client,
        [RecipeListItem("first", "第一道菜")],
        image_mode="server",
        servings=4,
        shopping_document=embedded,
    )

    assert documents[-1] is embedded
    assert [request.method for request in requests] == ["GET"]


@pytest.mark.asyncio
async def test_scaled_ingredients_and_changelog_are_exposed() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/ingredients"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "name": "鸡蛋",
                            "quantity": "4 个",
                            "quantity_original": "2 个",
                            "scaled": True,
                        }
                    ],
                    "meta": {
                        "id": "abc",
                        "title": "炒蛋",
                        "total": 1,
                        "servings": 4,
                        "base_servings": 2,
                        "factor": 2,
                        "per_serving_factor": 4,
                        "note": "静态数量乘 factor；公式型每份量乘 per_serving_factor",
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "added": [{"id": "a", "title": "新菜", "created_at": "2026-08-30"}],
                    "updated": [{"id": "b", "title": "旧菜", "updated_at": "2026-08-29"}],
                },
                "meta": {"days": 30, "added": 1, "updated": 1},
            },
        )

    client = HowToCookClient("http://cook.test/api", transport=httpx.MockTransport(handler))
    ingredients = await execute_command(client, parse_command("原料 abc --份数 4"), Config())
    changelog = await execute_command(client, parse_command("更新日志 30 --数量 2"), Config())
    assert "目标 4 人份" in ingredients.full_text()
    assert "静态数量：×2" in ingredients.full_text()
    assert "公式型每份量：×4" in ingredients.full_text()
    assert "上游 API 说明：" in ingredients.full_text()
    assert "静态数量乘 factor；公式型每份量乘 per_serving_factor" in ingredients.full_text()
    assert changelog.layout == "changelog"
    assert len(changelog.recipe_choices) == 2
    assert requests[0].url.params["servings"] == "4"
