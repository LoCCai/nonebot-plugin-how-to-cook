import json

import httpx
import pytest

from nonebot_plugin_how_to_cook.api import (
    HowToCookAPIError,
    HowToCookClient,
    normalize_endpoint,
)


def _client(handler) -> HowToCookClient:
    return HowToCookClient(
        "http://cook.test/api",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_structured_response_is_unwrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/recipes"
        assert request.url.params["q"] == "红烧肉"
        return httpx.Response(
            200,
            json={"data": [{"id": "abc"}], "meta": {"total": 1}},
        )

    result = await _client(handler).recipes(q="红烧肉")
    assert result.data == [{"id": "abc"}]
    assert result.meta == {"total": 1}
    assert result.content_type == "application/json"


@pytest.mark.asyncio
async def test_text_endpoints_are_not_forced_to_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/recipes/abc/markdown")
        return httpx.Response(
            200,
            text="# 一道菜\n\n正文",
            headers={"content-type": "text/markdown; charset=utf-8"},
        )

    result = await _client(handler).recipe("abc", resource="markdown")
    assert result.data.startswith("# 一道菜")
    assert result.content_type == "text/markdown"


@pytest.mark.asyncio
async def test_recipe_path_is_encoded_as_one_identifier() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {"id": "abc"}, "meta": {}})

    await _client(handler).recipe("dishes/meat dish/红烧肉.md")
    assert seen[0].url.raw_path.startswith(
        b"/api/recipes/dishes%2Fmeat%20dish%2F%E7%BA%A2%E7%83%A7%E8%82%89.md"
    )


@pytest.mark.asyncio
async def test_api_error_contract() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"error": {"code": "RECIPE_NOT_FOUND", "message": "菜谱不存在"}},
        )

    with pytest.raises(HowToCookAPIError) as caught:
        await _client(handler).recipe("missing")
    assert caught.value.code == "RECIPE_NOT_FOUND"
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_image_download_has_type_and_size_guards() -> None:
    def good(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"\x89PNG\r\n\x1a\n", headers={"content-type": "image/png"}
        )

    assert await _client(good).fetch_image("/assets/a.png") == b"\x89PNG\r\n\x1a\n"

    def bad(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not image", headers={"content-type": "text/plain"})

    with pytest.raises(HowToCookAPIError, match="非图片"):
        await _client(bad).fetch_image("/assets/a.png")


def test_generic_endpoint_allowlist() -> None:
    assert normalize_endpoint("/api/recipes/abc/steps") == ("recipes/abc/steps", False)
    assert normalize_endpoint("recipes/abc/related") == ("recipes/abc/related", False)
    assert normalize_endpoint("recipes/abc/jsonld") == ("recipes/abc/jsonld", False)
    assert normalize_endpoint("recipes/random") == ("recipes/random", False)
    assert normalize_endpoint("menu") == ("menu", False)
    assert normalize_endpoint("plan/week") == ("plan/week", False)
    assert normalize_endpoint("content/check") == ("content/check", False)
    assert normalize_endpoint("content/changelog") == ("content/changelog", False)
    assert normalize_endpoint("openapi.json") == ("openapi.json", False)
    assert normalize_endpoint("assets/dishes/a.jpg") == ("assets/dishes/a.jpg", True)
    for value in (
        "https://evil.test/a",
        "recipes/../health",
        "admin",
        "recipes?a=1",
        "content/update",
        "shopping-list",
    ):
        with pytest.raises(ValueError):
            normalize_endpoint(value)


@pytest.mark.asyncio
async def test_new_discovery_client_methods() -> None:
    seen: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, dict(request.url.params)))
        return httpx.Response(200, json={"data": [], "meta": {}})

    client = _client(handler)
    await client.random_recipes(count=3, seed="qiqi")
    await client.recipes_by_ingredients(have="鸡蛋,番茄", mode="strict", limit=8)
    await client.menu(meat=1, vegetable=1, soup=1, max_difficulty=3)
    await client.week_plan(days=7, seed="week", exclude_tags="seafood")
    await client.shopping_list(["abc", "def"], servings=4)
    await client.related_recipes("abc", limit=4, image_mode="server")
    await client.recipe("abc", resource="ingredients", servings=4)
    await client.recipe("abc", resource="jsonld")
    await client.search_all("备菜", image_mode="server")
    await client.stats()
    await client.content_info()
    await client.content_check()
    await client.content_changelog(days=30)

    assert [path for path, _params in seen] == [
        "/api/recipes/random",
        "/api/recipes/by-ingredients",
        "/api/menu",
        "/api/plan/week",
        "/api/shopping-list",
        "/api/recipes/abc/related",
        "/api/recipes/abc/ingredients",
        "/api/recipes/abc/jsonld",
        "/api/search",
        "/api/stats",
        "/api/content",
        "/api/content/check",
        "/api/content/changelog",
    ]
    assert seen[0][1] == {"count": "3", "seed": "qiqi"}
    assert seen[1][1]["have"] == "鸡蛋,番茄"
    assert seen[3][1]["exclude_tags"] == "seafood"
    assert seen[4][1] == {"ids": "abc,def", "servings": "4"}
    assert seen[5][1] == {"limit": "4", "image_mode": "server"}
    assert seen[6][1] == {"servings": "4"}


@pytest.mark.asyncio
async def test_shopping_list_is_the_only_explicit_post_computation() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"data": {"items": [], "recipes": [], "not_found": []}, "meta": {}},
        )

    await _client(handler).shopping_list(["a", "b"], servings=6)
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/shopping-list"
    assert dict(seen[0].url.params) == {"ids": "a,b", "servings": "6"}
    with pytest.raises(ValueError, match="内容更新 POST 不开放"):
        await _client(handler).post("content/update")
    assert len(seen) == 1


def test_json_fixture_is_valid() -> None:
    # Keeps json imported and documents that arbitrary API payloads remain data.
    assert json.loads('{"data": 1}')["data"] == 1
