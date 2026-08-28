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
    "详情": "recipe",
    "菜谱": "recipe",
    "做法": "recipe",
    "recipe": "recipe",
    "元信息": "recipe_meta",
    "meta": "recipe_meta",
    "原料": "ingredients",
    "食材": "ingredients",
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

_COMMON_OPTIONS = {
    "--mode": "mode",
    "--模式": "mode",
    "-m": "mode",
    "--theme": "theme",
    "--主题": "theme",
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
    "--image-mode": "image_mode",
    "--图片模式": "image_mode",
}
_TIP_OPTIONS = {
    "--group": "group",
    "--分组": "group",
    "--page": "page",
    "--页": "page",
    "--page-size": "page_size",
    "--每页": "page_size",
}
_INTEGER_OPTIONS = {"difficulty", "max_difficulty", "page", "page_size"}
_QUERY_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")


def _split_option(token: str) -> tuple[str, str | None]:
    if token.startswith("--") and "=" in token:
        return tuple(token.split("=", 1))  # type: ignore[return-value]
    return token, None


def _take_options(
    tokens: list[str],
    mapping: dict[str, str],
) -> tuple[list[str], dict[str, str]]:
    positional: list[str] = []
    options: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        name, inline = _split_option(tokens[index])
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


def _typed_options(values: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values.items():
        if key in _INTEGER_OPTIONS:
            try:
                number = int(value)
            except ValueError as exc:
                raise CommandError(f"{key} 必须是整数") from exc
            if number < 1:
                raise CommandError(f"{key} 必须大于 0")
            result[key] = number
        else:
            result[key] = value
    if "difficulty" in result and not 1 <= result["difficulty"] <= 5:
        raise CommandError("难度必须在 1 到 5 之间")
    if "max_difficulty" in result and not 1 <= result["max_difficulty"] <= 5:
        raise CommandError("最高难度必须在 1 到 5 之间")
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
    if action in {"help", "health", "categories"}:
        if remainder:
            raise CommandError(f"{tokens[0]} 不接受额外参数")
        return ParsedCommand(action, mode=mode, theme=theme)
    if action == "search":
        positional, raw_options = _take_options(remainder, _SEARCH_OPTIONS)
        query = " ".join(positional).strip()
        if not query and not any(
            raw_options.get(key)
            for key in ("category", "ingredient", "difficulty", "max_difficulty")
        ):
            raise CommandError("请提供菜名、拼音、原料或筛选条件")
        return ParsedCommand(
            action,
            query=query or None,
            params=_typed_options(raw_options),
            mode=mode,
            theme=theme,
        )
    if action == "tips":
        positional, raw_options = _take_options(remainder, _TIP_OPTIONS)
        return ParsedCommand(
            action,
            query=" ".join(positional).strip() or None,
            params=_typed_options(raw_options),
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
