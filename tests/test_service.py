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
async def test_service_caps_bot_page_size() -> None:
    client = HowToCookClient(
        "http://cook.test/api",
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
    )
    with pytest.raises(CommandError, match="每页最多"):
        await execute_command(client, parse_command("搜索 肉 --每页 21"), Config())
