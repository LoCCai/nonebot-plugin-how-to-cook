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


def test_random_menu_and_related_commands() -> None:
    random = parse_command("随机 3 --分类 soup --难度 2 --种子 dinner")
    assert random.action == "random"
    assert random.params == {
        "category": "soup",
        "difficulty": 2,
        "seed": "dinner",
        "count": 3,
    }

    menu = parse_command("配餐 --荤 2 --素 0 --汤 1 --最高难度 3 --种子 family")
    assert menu.action == "menu"
    assert menu.params == {
        "meat": 2,
        "vegetable": 0,
        "soup": 1,
        "max_difficulty": 3,
        "seed": "family",
    }

    related = parse_command("相关 dishes/staple/蛋炒饭.md --数量 6")
    assert related.action == "related"
    assert related.identifier == "dishes/staple/蛋炒饭.md"
    assert related.params == {"limit": 6}


def test_ingredient_discovery_and_aggregate_search() -> None:
    command = parse_command("食材 鸡蛋，番茄 土豆 --严格 --数量 7")
    assert command.action == "by_ingredients"
    assert command.params == {
        "limit": 7,
        "have": "鸡蛋,番茄,土豆",
        "mode": "strict",
    }

    aggregate = parse_command("全局搜索 厨房 安全 --图片模式 server")
    assert aggregate.action == "aggregate_search"
    assert aggregate.query == "厨房 安全"
    assert aggregate.params == {"image_mode": "server"}


@pytest.mark.parametrize(
    ("text", "action"),
    [
        ("统计", "stats"),
        ("内容版本", "content_info"),
        ("内容检查", "content_check"),
    ],
)
def test_new_read_only_status_commands(text: str, action: str) -> None:
    assert parse_command(text).action == action


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
        "随机 21",
        "配餐 --荤 0 --素 0 --汤 0",
        "食材",
        "食材 鸡蛋 --匹配 不知道",
        "全局搜索",
        "统计 extra",
    ],
)
def test_invalid_commands(text: str) -> None:
    with pytest.raises(CommandError):
        parse_command(text)
