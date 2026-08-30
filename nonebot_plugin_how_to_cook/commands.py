from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Any

from .config import ResponseMode, ThemeMode


class CommandError(ValueError):
    pass


@dataclass(slots=True)
class ParsedCommand:
    action: str
    identifier: str | None = None
    query: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    mode: ResponseMode | None = None
    theme: ThemeMode | None = None


_ACTIONS = {
    "帮助": "help",
    "help": "help",
    "?": "help",
    "健康": "health",
    "状态": "health",
    "health": "health",
    "分类": "categories",
    "categories": "categories",
    "搜索": "search",
    "搜菜": "search",
    "search": "search",
    "随机": "random",
    "推荐": "random",
    "random": "random",
    "配餐": "menu",
    "菜单": "menu",
    "menu": "menu",
    "食材": "by_ingredients",
    "食材找菜": "by_ingredients",
    "库存": "by_ingredients",
    "有什么做什么": "by_ingredients",
    "by-ingredients": "by_ingredients",
    "相关": "related",
    "相似": "related",
    "related": "related",
    "全局搜索": "aggregate_search",
    "聚合搜索": "aggregate_search",
    "综合搜索": "aggregate_search",
    "global-search": "aggregate_search",
    "统计": "stats",
    "数据统计": "stats",
    "stats": "stats",
    "内容版本": "content_info",
    "版本": "content_info",
    "content": "content_info",
    "内容检查": "content_check",
    "检查更新": "content_check",
    "content-check": "content_check",
    "详情": "recipe",
    "菜谱": "recipe",
    "做法": "recipe",
    "recipe": "recipe",
    "元信息": "recipe_meta",
    "meta": "recipe_meta",
    "原料": "ingredients",
    "菜谱原料": "ingredients",
    "食材清单": "ingredients",
    "ingredients": "ingredients",
    "工具": "tools",
    "tools": "tools",
    "步骤": "steps",
    "steps": "steps",
    "段落": "sections",
    "sections": "sections",
    "备注": "notes",
    "notes": "notes",
    "图片": "images",
    "images": "images",
    "markdown": "markdown",
    "md": "markdown",
    "html": "html",
    "原文": "raw",
    "raw": "raw",
    "技巧": "tips",
    "tips": "tips",
    "技巧详情": "tip",
    "tip": "tip",
    "技巧元信息": "tip_meta",
    "tip-meta": "tip_meta",
    "技巧md": "tip_markdown",
    "tip-md": "tip_markdown",
    "技巧html": "tip_html",
    "tip-html": "tip_html",
    "技巧原文": "tip_raw",
    "tip-raw": "tip_raw",
    "接口": "api",
    "api": "api",
}

_MODE_ALIASES: dict[str, ResponseMode] = {
    "合并": "forward",
    "合并消息": "forward",
    "forward": "forward",
    "单条": "single",
    "单消息": "single",
    "single": "single",
    "组合": "combined",
    "组合消息": "combined",
    "combined": "combined",
    "渲染": "render",
    "长图": "render",
    "图片": "render",
    "render": "render",
}
_THEME_ALIASES: dict[str, ThemeMode] = {
    "自动": "auto",
    "auto": "auto",
    "白天": "light",
    "浅色": "light",
    "light": "light",
    "夜间": "dark",
    "深色": "dark",
    "dark": "dark",
}
_INGREDIENT_MODE_ALIASES = {
    "loose": "loose",
    "宽松": "loose",
    "推荐": "loose",
    "strict": "strict",
    "严格": "strict",
    "齐全": "strict",
}

_COMMON_OPTIONS = {
    "--mode": "mode",
    "--模式": "mode",
    "-m": "mode",
    "--theme": "theme",
    "--主题": "theme",
}
_IMAGE_OPTIONS = {
    "--image-mode": "image_mode",
    "--图片模式": "image_mode",
}
_SEARCH_OPTIONS = {
    "--category": "category",
    "--分类": "category",
    "--difficulty": "difficulty",
    "--难度": "difficulty",
    "--max-difficulty": "max_difficulty",
    "--最高难度": "max_difficulty",
    "--ingredient": "ingredient",
    "--原料": "ingredient",
    "--sort": "sort",
    "--排序": "sort",
    "--page": "page",
    "--页": "page",
    "--page-size": "page_size",
    "--每页": "page_size",
    "--fields": "fields",
    "--字段": "fields",
    **_IMAGE_OPTIONS,
}
_RANDOM_OPTIONS = {
    "--count": "count",
    "--数量": "count",
    "--seed": "seed",
    "--种子": "seed",
    "--category": "category",
    "--分类": "category",
    "--difficulty": "difficulty",
    "--难度": "difficulty",
    **_IMAGE_OPTIONS,
}
_MENU_OPTIONS = {
    "--seed": "seed",
    "--种子": "seed",
    "--meat": "meat",
    "--荤": "meat",
    "--荤菜": "meat",
    "--vegetable": "vegetable",
    "--素": "vegetable",
    "--素菜": "vegetable",
    "--soup": "soup",
    "--汤": "soup",
    "--max-difficulty": "max_difficulty",
    "--最高难度": "max_difficulty",
    **_IMAGE_OPTIONS,
}
_INGREDIENT_OPTIONS = {
    "--match": "ingredient_mode",
    "--匹配": "ingredient_mode",
    "--limit": "limit",
    "--数量": "limit",
    "--上限": "limit",
    **_IMAGE_OPTIONS,
}
_INGREDIENT_FLAGS = {
    "--严格": ("ingredient_mode", "strict"),
    "--宽松": ("ingredient_mode", "loose"),
}
_RELATED_OPTIONS = {
    "--limit": "limit",
    "--数量": "limit",
    **_IMAGE_OPTIONS,
}
_AGGREGATE_OPTIONS = dict(_IMAGE_OPTIONS)
_TIP_OPTIONS = {
    "--group": "group",
    "--分组": "group",
    "--page": "page",
    "--页": "page",
    "--page-size": "page_size",
    "--每页": "page_size",
}
_QUERY_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
_INGREDIENT_SPLIT = re.compile(r"[,，、\s]+")


def _split_option(token: str) -> tuple[str, str | None]:
    if token.startswith("--") and "=" in token:
        return tuple(token.split("=", 1))  # type: ignore[return-value]
    return token, None


def _take_options(
    tokens: list[str],
    mapping: dict[str, str],
    *,
    flags: dict[str, tuple[str, str]] | None = None,
) -> tuple[list[str], dict[str, str]]:
    positional: list[str] = []
    options: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        name, inline = _split_option(tokens[index])
        if flags and name in flags:
            if inline is not None:
                raise CommandError(f"开关参数 {name} 不接受值")
            target, value = flags[name]
            options[target] = value
            index += 1
            continue
        target = mapping.get(name)
        if target is None:
            if tokens[index].startswith("-"):
                raise CommandError(f"未知参数：{tokens[index]}")
            positional.append(tokens[index])
            index += 1
            continue
        if inline is None:
            index += 1
            if index >= len(tokens):
                raise CommandError(f"参数 {name} 缺少值")
            inline = tokens[index]
        if not inline:
            raise CommandError(f"参数 {name} 不能为空")
        options[target] = inline
        index += 1
    return positional, options


def _extract_common(tokens: list[str]) -> tuple[list[str], ResponseMode | None, ThemeMode | None]:
    positional: list[str] = []
    values: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        name, inline = _split_option(tokens[index])
        target = _COMMON_OPTIONS.get(name)
        if target is None:
            positional.append(tokens[index])
            index += 1
            continue
        if inline is None:
            index += 1
            if index >= len(tokens):
                raise CommandError(f"参数 {name} 缺少值")
            inline = tokens[index]
        if not inline:
            raise CommandError(f"参数 {name} 不能为空")
        values[target] = inline
        index += 1
    raw_mode = values.get("mode")
    raw_theme = values.get("theme")
    mode = _MODE_ALIASES.get(raw_mode.casefold()) if raw_mode else None
    theme = _THEME_ALIASES.get(raw_theme.casefold()) if raw_theme else None
    if raw_mode and mode is None:
        raise CommandError("模式仅支持：合并、单条、组合、渲染")
    if raw_theme and theme is None:
        raise CommandError("主题仅支持：自动、白天、夜间")
    return positional, mode, theme


def _typed_options(
    values: dict[str, str],
    *,
    integer_rules: dict[str, tuple[int, int | None, str]] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    rules = integer_rules or {}
    for key, value in values.items():
        if key not in rules:
            result[key] = value
            continue
        minimum, maximum, label = rules[key]
        try:
            number = int(value)
        except ValueError as exc:
            raise CommandError(f"{label}必须是整数") from exc
        if number < minimum or (maximum is not None and number > maximum):
            if maximum is None:
                raise CommandError(f"{label}不能小于 {minimum}")
            raise CommandError(f"{label}必须在 {minimum} 到 {maximum} 之间")
        result[key] = number
    if result.get("image_mode") not in {None, "relative", "server", "proxy"}:
        raise CommandError("图片模式仅支持 relative、server、proxy")
    return result


def _parse_generic(tokens: list[str]) -> tuple[str, dict[str, str]]:
    if not tokens:
        raise CommandError("请提供接口路径，例如：接口 recipes q=红烧肉")
    endpoint = tokens[0]
    params: dict[str, str] = {}
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--"):
            key, inline = _split_option(token)
            key = key[2:].replace("-", "_")
            if inline is None:
                index += 1
                if index >= len(tokens):
                    raise CommandError(f"参数 --{key} 缺少值")
                inline = tokens[index]
            value = inline
        elif "=" in token:
            key, value = token.split("=", 1)
        else:
            raise CommandError(f"通用接口参数应写为 key=value：{token}")
        if not _QUERY_KEY.fullmatch(key) or not value:
            raise CommandError(f"无效接口参数：{token}")
        params[key] = value
        index += 1
    return endpoint, params


def _require_no_extra(label: str, remainder: list[str]) -> None:
    if remainder:
        raise CommandError(f"{label}不接受额外参数")


def parse_command(text: str) -> ParsedCommand:
    try:
        original = shlex.split(text, posix=True)
    except ValueError as exc:
        raise CommandError(f"参数引号不完整：{exc}") from exc
    if not original:
        return ParsedCommand("help")

    tokens, mode, theme = _extract_common(original)
    if not tokens:
        return ParsedCommand("help", mode=mode, theme=theme)
    action = _ACTIONS.get(tokens[0].casefold())
    remainder = tokens[1:]

    if action is None:
        action = "search"
        remainder = tokens
    if action in {"help", "health", "categories", "stats", "content_info", "content_check"}:
        _require_no_extra(tokens[0], remainder)
        return ParsedCommand(action, mode=mode, theme=theme)
    if action == "search":
        positional, raw_options = _take_options(remainder, _SEARCH_OPTIONS)
        query = " ".join(positional).strip()
        if not query and not any(
            raw_options.get(key)
            for key in ("category", "ingredient", "difficulty", "max_difficulty")
        ):
            raise CommandError("请提供菜名、拼音、原料或筛选条件")
        params = _typed_options(
            raw_options,
            integer_rules={
                "difficulty": (1, 5, "难度"),
                "max_difficulty": (1, 5, "最高难度"),
                "page": (1, None, "页码"),
                "page_size": (1, 100, "每页数量"),
            },
        )
        return ParsedCommand(action, query=query or None, params=params, mode=mode, theme=theme)
    if action == "random":
        positional, raw_options = _take_options(remainder, _RANDOM_OPTIONS)
        if len(positional) > 1 or (positional and not positional[0].isdigit()):
            raise CommandError("随机推荐可直接写数量，例如：做饭 随机 3")
        if positional:
            raw_options.setdefault("count", positional[0])
        params = _typed_options(
            raw_options,
            integer_rules={"count": (1, 20, "数量"), "difficulty": (1, 5, "难度")},
        )
        return ParsedCommand(action, params=params, mode=mode, theme=theme)
    if action == "menu":
        positional, raw_options = _take_options(remainder, _MENU_OPTIONS)
        if positional:
            raise CommandError(f"配餐参数无法识别：{' '.join(positional)}")
        params = _typed_options(
            raw_options,
            integer_rules={
                "meat": (0, 3, "荤菜数量"),
                "vegetable": (0, 3, "素菜数量"),
                "soup": (0, 3, "汤数量"),
                "max_difficulty": (1, 5, "最高难度"),
            },
        )
        if all(params.get(key) == 0 for key in ("meat", "vegetable", "soup")):
            raise CommandError("荤菜、素菜和汤不能同时为 0")
        return ParsedCommand(action, params=params, mode=mode, theme=theme)
    if action == "by_ingredients":
        positional, raw_options = _take_options(
            remainder,
            _INGREDIENT_OPTIONS,
            flags=_INGREDIENT_FLAGS,
        )
        ingredients = list(
            dict.fromkeys(value for value in _INGREDIENT_SPLIT.split(" ".join(positional)) if value)
        )
        if not ingredients:
            raise CommandError("请告诉我手头有什么，例如：做饭 食材 鸡蛋 西红柿")
        params = _typed_options(
            raw_options,
            integer_rules={"limit": (1, 50, "数量")},
        )
        raw_ingredient_mode = str(params.pop("ingredient_mode", "loose")).casefold()
        ingredient_mode = _INGREDIENT_MODE_ALIASES.get(raw_ingredient_mode)
        if ingredient_mode is None:
            raise CommandError("原料匹配仅支持：宽松、严格")
        params.update(have=",".join(ingredients), mode=ingredient_mode)
        return ParsedCommand(action, params=params, mode=mode, theme=theme)
    if action == "related":
        positional, raw_options = _take_options(remainder, _RELATED_OPTIONS)
        identifier = " ".join(positional).strip()
        if not identifier:
            raise CommandError("相关推荐需要菜谱 ID 或路径")
        params = _typed_options(
            raw_options,
            integer_rules={"limit": (1, 20, "数量")},
        )
        return ParsedCommand(
            action,
            identifier=identifier,
            params=params,
            mode=mode,
            theme=theme,
        )
    if action == "aggregate_search":
        positional, raw_options = _take_options(remainder, _AGGREGATE_OPTIONS)
        query = " ".join(positional).strip()
        if not query:
            raise CommandError("全局搜索需要关键词")
        return ParsedCommand(
            action,
            query=query,
            params=_typed_options(raw_options),
            mode=mode,
            theme=theme,
        )
    if action == "tips":
        positional, raw_options = _take_options(remainder, _TIP_OPTIONS)
        params = _typed_options(
            raw_options,
            integer_rules={"page": (1, None, "页码"), "page_size": (1, 100, "每页数量")},
        )
        return ParsedCommand(
            action,
            query=" ".join(positional).strip() or None,
            params=params,
            mode=mode,
            theme=theme,
        )
    if action == "api":
        endpoint, params = _parse_generic(remainder)
        return ParsedCommand(action, identifier=endpoint, params=params, mode=mode, theme=theme)

    if not remainder:
        raise CommandError(f"{tokens[0]} 需要菜谱或技巧 ID/路径")
    identifier = " ".join(remainder).strip()
    return ParsedCommand(action, identifier=identifier, mode=mode, theme=theme)
