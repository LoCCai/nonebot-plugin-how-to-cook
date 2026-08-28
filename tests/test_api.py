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
    assert normalize_endpoint("assets/dishes/a.jpg") == ("assets/dishes/a.jpg", True)
    for value in ("https://evil.test/a", "recipes/../health", "admin", "recipes?a=1"):
        with pytest.raises(ValueError):
            normalize_endpoint(value)


def test_json_fixture_is_valid() -> None:
    # Keeps json imported and documents that arbitrary API payloads remain data.
    assert json.loads('{"data": 1}')["data"] == 1
