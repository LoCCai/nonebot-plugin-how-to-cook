import pytest

from nonebot_plugin_how_to_cook.commands import CommandError, parse_command


def test_empty_command_opens_help() -> None:
    assert parse_command("").action == "help"


def test_unknown_first_word_is_natural_search() -> None:
    command = parse_command("红烧肉")
    assert command.action == "search"
    assert command.query == "红烧肉"


def test_search_filters_and_presentation_overrides() -> None:
    command = parse_command(
        "搜索 土豆 牛肉 --原料 牛肉 --最高难度 3 --排序 -updated_at --页 2 "
        "--每页 6 --模式 组合 --主题 夜间"
    )
    assert command.action == "search"
    assert command.query == "土豆 牛肉"
    assert command.params == {
        "ingredient": "牛肉",
        "max_difficulty": 3,
        "sort": "-updated_at",
        "page": 2,
        "page_size": 6,
    }
    assert command.mode == "combined"
    assert command.theme == "dark"


@pytest.mark.parametrize(
    ("text", "action"),
    [
        ("详情 abc", "recipe"),
        ("原料 abc", "ingredients"),
        ("Markdown abc", "markdown"),
        ("技巧详情 tip-id", "tip"),
        ("技巧HTML tip-id", "tip_html"),
    ],
)
def test_identifier_actions(text: str, action: str) -> None:
    command = parse_command(text)
    assert command.action == action
    assert command.identifier


def test_tip_search_options() -> None:
    command = parse_command("技巧 厨房 --分组 advanced --页 2 --每页 10")
    assert command.query == "厨房"
    assert command.params == {"group": "advanced", "page": 2, "page_size": 10}


def test_generic_api_parameters() -> None:
    command = parse_command("接口 recipes q=番茄 --page-size 5 image_mode=server")
    assert command.identifier == "recipes"
    assert command.params == {"q": "番茄", "page_size": "5", "image_mode": "server"}


@pytest.mark.parametrize(
    "text",
    [
        "搜索",
        "详情",
        "搜索 肉 --难度 8",
        "搜索 肉 --未知 1",
        "接口 recipes bad",
        "健康 extra",
        "搜索 肉 --模式 未知",
    ],
)
def test_invalid_commands(text: str) -> None:
    with pytest.raises(CommandError):
        parse_command(text)
