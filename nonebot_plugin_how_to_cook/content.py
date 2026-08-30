from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from typing import Any, Literal

from .api import APIResult

_TAG_RE = re.compile(r"<[^>]+>")
_MARKDOWN_MARK_RE = re.compile(r"(?m)^(#{1,6}|>|[-*+]\s)|[`*_~]")


@dataclass(slots=True)
class Section:
    title: str
    text: str


@dataclass(slots=True)
class RecipeListItem:
    identifier: str
    title: str
    number: int = 0
    kind: Literal["recipe", "tip"] = "recipe"
    badge: str = "菜谱"
    metadata: list[tuple[str, str]] = field(default_factory=list)
    cover_url: str | None = None
    cover_alt: str = "菜谱成品图"
    matched: list[str] = field(default_factory=list)
    note: str = ""


@dataclass(slots=True)
class ChoiceGroup:
    key: str
    title: str
    icon: str
    items: list[RecipeListItem] = field(default_factory=list)


@dataclass(slots=True)
class ChartBar:
    label: str
    value: str
    percent: float


@dataclass(slots=True)
class ChartGroup:
    title: str
    description: str = ""
    bars: list[ChartBar] = field(default_factory=list)


@dataclass(slots=True)
class ShoppingListItem:
    name: str
    amount: str
    aliases: list[str] = field(default_factory=list)
    recipes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Document:
    title: str
    kicker: str = "HOW TO COOK"
    description: str = ""
    stats: list[tuple[str, str]] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    cover_url: str | None = None
    cover_alt: str = "成品图"
    article_markdown: str | None = None
    article_html: str | None = None
    attachment: bytes | None = None
    attachment_content_type: str | None = None
    asset_base_url: str | None = None
    footer: str = "内容来自 HowToCook 社区，仅供烹饪参考"
    filename_hint: str = "how-to-cook"
    layout: Literal[
        "article",
        "recipe_list",
        "menu",
        "week_plan",
        "shopping_list",
        "changelog",
        "stats",
    ] = "article"
    recipe_choices: list[RecipeListItem] = field(default_factory=list)
    choice_groups: list[ChoiceGroup] = field(default_factory=list)
    charts: list[ChartGroup] = field(default_factory=list)
    shopping_items: list[ShoppingListItem] = field(default_factory=list)
    shopping_recipe_ids: list[str] = field(default_factory=list)
    embedded_shopping_list: Document | None = None
    shopping_servings: int | None = None

    def summary_text(self) -> str:
        lines = [f"🍳 {self.title}"]
        if self.description:
            lines.append(self.description.strip())
        if self.stats:
            lines.append(" · ".join(f"{label} {value}" for label, value in self.stats))
        return "\n".join(lines)

    def full_text(self) -> str:
        chunks = [self.summary_text()]
        for section in self.sections:
            if section.text.strip():
                chunks.append(f"【{section.title}】\n{section.text.strip()}")
        if not self.sections and self.article_markdown:
            chunks.append(_plain_markdown(self.article_markdown))
        elif not self.sections and self.article_html:
            chunks.append(_plain_html(self.article_html))
        if self.footer:
            chunks.append(self.footer)
        return "\n\n".join(chunk for chunk in chunks if chunk.strip())

    def render_markdown(self) -> str:
        if self.article_markdown:
            return self.article_markdown
        if self.article_html:
            return ""
        chunks: list[str] = []
        if self.description:
            chunks.append(self.description)
        for section in self.sections:
            chunks.append(f"## {section.title}\n\n{section.text}")
        return "\n\n".join(chunks)


def _text(value: Any, default: str = "—") -> str:
    if value is None or value == "":
        return default
    return str(value)


def _plain_markdown(value: str) -> str:
    return _MARKDOWN_MARK_RE.sub("", value).strip()


def _plain_html(value: str) -> str:
    return unescape(_TAG_RE.sub("", value)).strip()


def _compact_description(value: Any, limit: int = 210) -> str:
    text = _plain_markdown(_text(value, ""))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip("，。；、 ") + "…"


def _author_name(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("name"), "未知")
    return _text(value, "未知")


def _cover(data: dict[str, Any]) -> tuple[str | None, str]:
    cover = data.get("cover")
    if not isinstance(cover, dict):
        images = data.get("images")
        cover = (
            images[0]
            if isinstance(images, list) and images and isinstance(images[0], dict)
            else None
        )
    if not isinstance(cover, dict):
        return None, "成品图"
    return (
        str(cover.get("url")) if cover.get("url") else None,
        _text(cover.get("alt"), "成品图"),
    )


def _recipe_stats(data: dict[str, Any]) -> list[tuple[str, str]]:
    stats: list[tuple[str, str]] = []
    category = data.get("category")
    if isinstance(category, dict) and category.get("title"):
        stats.append(("分类", str(category["title"])))
    difficulty = data.get("difficulty_display") or data.get("difficulty")
    if difficulty:
        stats.append(("难度", str(difficulty)))
    estimate = data.get("time_estimate")
    if isinstance(estimate, dict) and estimate.get("text"):
        stats.append(("耗时", str(estimate["text"])))
    calories = data.get("calories")
    if isinstance(calories, dict) and calories.get("value") is not None:
        stats.append(("热量", f"{calories['value']} {calories.get('unit', '')}".strip()))
    methods = data.get("methods")
    if isinstance(methods, list) and methods:
        stats.append(("方式", " / ".join(str(item) for item in methods[:6])))
    author = _author_name(data.get("author"))
    if author != "未知":
        stats.append(("作者", author))
    diet_labels = _diet_labels(data.get("diet_tags"))
    if diet_labels:
        stats.append(("饮食标签", " / ".join(diet_labels)))
    return stats


def _search_metadata(data: dict[str, Any]) -> list[tuple[str, str]]:
    estimate = data.get("time_estimate")
    if isinstance(estimate, dict):
        duration = _text(estimate.get("text"), "未标注")
    else:
        duration = _text(estimate, "未标注")

    calories = data.get("calories")
    if isinstance(calories, dict) and calories.get("value") is not None:
        calorie_text = f"{calories['value']} {calories.get('unit', '')}".strip()
    else:
        calorie_text = "未标注"

    category = data.get("category")
    category_text = (
        _text(category.get("title"), "未分类") if isinstance(category, dict) else "未分类"
    )
    methods = data.get("methods")
    method_text = (
        " / ".join(str(item) for item in methods[:4])
        if isinstance(methods, list) and methods
        else "未标注"
    )
    updated_at = _text(data.get("updated_at"), "未标注")
    if updated_at != "未标注":
        updated_at = updated_at[:10]

    metadata = [
        ("作者", _author_name(data.get("author"))),
        ("耗时", duration),
        ("热量", calorie_text),
        ("难度", _text(data.get("difficulty_display") or data.get("difficulty"), "未标注")),
        ("分类", category_text),
        ("方式", method_text),
        ("更新", updated_at),
    ]
    diet_labels = _diet_labels(data.get("diet_tags"))
    if diet_labels:
        metadata.append(("标签", " / ".join(diet_labels)))
    return metadata


_DIET_TAG_LABELS = {
    "vegetarian": "素食",
    "spicy": "含辣",
    "seafood": "水产",
    "peanut": "花生",
    "egg": "蛋类",
    "dairy": "乳制品",
    "gluten": "麸质",
}


def _diet_labels(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [tag for tag in re.split(r"[,，、\s]+", value) if tag]
    if not isinstance(value, list):
        return []
    return [_DIET_TAG_LABELS.get(str(tag), str(tag)) for tag in value]


_MATCHED_LABELS = {
    "title": "标题",
    "pinyin": "拼音",
    "title_pinyin": "拼音",
    "title_initials": "拼音首字母",
    "ingredients": "原料",
    "category": "分类",
    "content": "正文",
}


def _matched_labels(data: dict[str, Any]) -> list[str]:
    matched = data.get("matched")
    if not isinstance(matched, list):
        return []
    return [_MATCHED_LABELS.get(str(value), str(value)) for value in matched]


def _recipe_choice(
    data: dict[str, Any],
    number: int,
    *,
    badge: str = "菜谱",
    note: str = "",
    extra_metadata: list[tuple[str, str]] | None = None,
) -> RecipeListItem | None:
    identifier = _text(data.get("id"), "")
    if not identifier:
        return None
    item_cover, item_alt = _cover(data)
    metadata = list(extra_metadata or []) + _search_metadata(data)
    return RecipeListItem(
        identifier=identifier,
        title=_text(data.get("title"), "未命名菜谱"),
        number=number,
        kind="recipe",
        badge=badge,
        metadata=metadata,
        cover_url=item_cover,
        cover_alt=item_alt,
        matched=_matched_labels(data),
        note=note,
    )


def _tip_choice(data: dict[str, Any], number: int) -> RecipeListItem | None:
    identifier = _text(data.get("id"), "")
    if not identifier:
        return None
    metadata = [("分组", _text(data.get("group"), "未分组"))]
    if data.get("updated_at"):
        metadata.append(("更新", str(data["updated_at"])[:10]))
    return RecipeListItem(
        identifier=identifier,
        title=_text(data.get("title"), "未命名技巧"),
        number=number,
        kind="tip",
        badge="厨房技巧",
        metadata=metadata,
        matched=_matched_labels(data),
    )


def _choice_sections(choices: list[RecipeListItem]) -> list[Section]:
    sections: list[Section] = []
    for choice in choices:
        details = [" · ".join(f"{key} {value}" for key, value in choice.metadata)]
        if choice.matched:
            details.append(f"命中：{' / '.join(choice.matched)}")
        if choice.note:
            details.append(choice.note)
        sections.append(Section(f"{choice.number}. {choice.title}", "\n".join(details)))
    return sections


def _is_unit_factor(value: Any) -> bool:
    try:
        return float(value) == 1.0
    except (TypeError, ValueError):
        return False


def _ingredient_lines(items: Any, *, per_serving_factor: Any = None) -> str:
    if not isinstance(items, list):
        return "暂无结构化原料信息"
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            lines.append(f"- {_text(item)}")
            continue
        raw = item.get("raw")
        scaled_state = item.get("scaled") if "scaled" in item else None
        name = _text(item.get("name"))
        quantity = _text(item.get("quantity"), "")
        note = _text(item.get("note"), "")
        optional = "（可选）" if item.get("optional") else ""
        suffix = " ".join(part for part in (quantity, note) if part)
        original = _text(item.get("quantity_original"), "")
        annotations: list[str] = []
        is_per_serving = bool(item.get("per_serving"))
        if is_per_serving:
            baseline = original or quantity
            annotations.append(f"每份基准 {baseline}" if baseline else "按每份计量")
            if _is_unit_factor(per_serving_factor):
                annotations.append("本次每份量系数为 1，数量保持不变")
        quantity_note = _text(item.get("quantity_note"), "")
        if quantity_note:
            annotations.append(f"换算说明 {quantity_note}")
        if scaled_state is True and original and original != quantity:
            if not is_per_serving:
                annotations.append(f"原用量 {original}")
        elif scaled_state is False and not (is_per_serving and _is_unit_factor(per_serving_factor)):
            annotations.append("按原文保留，无法自动换算")
        if annotations:
            suffix += f"（{'；'.join(annotations)}）"
        if not suffix and raw:
            suffix = str(raw)
        lines.append(f"- {name}{optional}{f'：{suffix}' if suffix else ''}")
    return "\n".join(lines) or "暂无结构化原料信息"


def _tool_lines(items: Any) -> str:
    if not isinstance(items, list) or not items:
        return "未单独列出工具"
    lines = []
    for item in items:
        if isinstance(item, dict):
            lines.append(f"• {_text(item.get('raw') or item.get('name'))}")
        else:
            lines.append(f"• {_text(item)}")
    return "\n".join(lines)


def _step_lines(items: Any) -> str:
    if isinstance(items, dict):
        items = items.get("flat") or items.get("grouped")
    if not isinstance(items, list) or not items:
        return "暂无结构化步骤"
    lines: list[str] = []
    previous_group: str | None = None
    for position, item in enumerate(items, 1):
        if not isinstance(item, dict):
            lines.append(f"{position}. {_text(item)}")
            continue
        if "steps" in item and isinstance(item["steps"], list):
            group = _text(item.get("group") or item.get("heading"), "步骤")
            lines.append(f"\n▌{group}")
            lines.extend(
                f"{index}. {_text(step.get('text') if isinstance(step, dict) else step)}"
                for index, step in enumerate(item["steps"], 1)
            )
            continue
        group = _text(item.get("group"), "")
        if group and group != previous_group:
            lines.append(f"\n▌{group}")
            previous_group = group
        index = item.get("index") or position
        lines.append(f"{index}. {_text(item.get('text') or item.get('raw'))}")
    return "\n".join(lines).strip()


def _notes_lines(data: dict[str, Any]) -> str:
    notes = data.get("notes")
    lines: list[str] = []
    if isinstance(notes, list):
        for note in notes:
            if isinstance(note, dict):
                lines.append(f"• {_text(note.get('text') or note.get('raw'))}")
            else:
                lines.append(f"• {_text(note)}")
    feedback = data.get("feedback_note")
    if feedback:
        lines.append(f"• {feedback}")
    return "\n".join(lines)


def recipe_document(data: Any, *, asset_base_url: str) -> Document:
    if not isinstance(data, dict):
        return generic_document("菜谱详情", data, asset_base_url=asset_base_url)
    cover_url, cover_alt = _cover(data)
    title = _text(data.get("title"), "菜谱详情")
    sections = [
        Section("原料", _ingredient_lines(data.get("ingredients"))),
        Section("工具", _tool_lines(data.get("tools"))),
        Section("烹饪步骤", _step_lines(data.get("steps"))),
    ]
    notes = _notes_lines(data)
    if notes:
        sections.append(Section("附加说明", notes))
    details = [
        f"菜谱 ID：{_text(data.get('id'))}",
        f"作者：{_author_name(data.get('author'))}",
        f"编写时间：{_text(data.get('created_at'))}",
        f"更新时间：{_text(data.get('updated_at'))}",
    ]
    sections.append(Section("来源信息", "\n".join(details)))
    content = data.get("content")
    markdown = content.get("markdown") if isinstance(content, dict) else None
    return Document(
        title=title,
        kicker="HOW TO COOK · RECIPE",
        description=_compact_description(data.get("description")),
        stats=_recipe_stats(data),
        sections=sections,
        cover_url=cover_url,
        cover_alt=cover_alt,
        article_markdown=str(markdown) if markdown else None,
        asset_base_url=asset_base_url,
        filename_hint=f"HowToCook-{title}",
    )


def recipe_list_document(data: Any, meta: dict[str, Any], *, asset_base_url: str) -> Document:
    items = data if isinstance(data, list) else []
    choices: list[RecipeListItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        choice = _recipe_choice(item, len(choices) + 1)
        if choice:
            choices.append(choice)
    sections = _choice_sections(choices)
    total = int(meta.get("total") or 0)
    page = int(meta.get("page") or 1)
    pages = int(meta.get("pages") or 1)
    query = _text(meta.get("q"), "全部菜谱")
    description = f"“{query}”共找到 {total} 道菜谱；当前第 {page}/{pages} 页。"
    included = _diet_labels(meta.get("tag"))
    excluded = _diet_labels(meta.get("exclude_tags"))
    if included:
        description += f" 仅看：{'、'.join(included)}。"
    if excluded:
        description += f" 已避开：{'、'.join(excluded)}。"
    if not sections:
        sections.append(Section("没有结果", "换个菜名、拼音或原料再试试。"))
    return Document(
        title="菜谱搜索结果",
        kicker="HOW TO COOK · SEARCH",
        description=description,
        stats=[("结果", str(total)), ("页码", f"{page}/{pages}")],
        sections=sections,
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-搜索结果",
        layout="recipe_list",
        recipe_choices=choices,
    )


def random_recipes_document(
    data: Any,
    meta: dict[str, Any],
    *,
    asset_base_url: str,
) -> Document:
    items = data if isinstance(data, list) else []
    choices: list[RecipeListItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        choice = _recipe_choice(item, len(choices) + 1, badge="随机推荐")
        if choice:
            choices.append(choice)
    total_available = int(meta.get("total_available") or 0)
    seed = _text(meta.get("seed"), "随机")
    description = f"从 {total_available} 道候选菜谱中，为你抽到了 {len(choices)} 道。"
    excluded = _diet_labels(meta.get("exclude_tags"))
    if excluded:
        description += f" 已避开：{'、'.join(excluded)}。"
    return Document(
        title="今天吃什么？",
        kicker="HOW TO COOK · RANDOM PICK",
        description=description,
        stats=[("推荐", str(len(choices))), ("候选池", str(total_available)), ("种子", seed)],
        sections=_choice_sections(choices)
        or [Section("没有结果", "当前筛选条件下没有可推荐的菜谱。")],
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-随机推荐",
        layout="recipe_list",
        recipe_choices=choices,
    )


def ingredients_discovery_document(
    data: Any,
    meta: dict[str, Any],
    *,
    asset_base_url: str,
) -> Document:
    items = data if isinstance(data, list) else []
    choices: list[RecipeListItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        match = item.get("ingredients_match")
        match = match if isinstance(match, dict) else {}
        coverage = float(match.get("coverage") or 0)
        hit_count = int(match.get("hit_count") or 0)
        ingredient_total = int(match.get("total") or 0)
        missing = match.get("missing") if isinstance(match.get("missing"), list) else []
        if missing:
            shown = "、".join(str(value) for value in missing[:6])
            more = len(missing) - 6
            note = f"还缺：{shown}{f' 等 {len(missing)} 项' if more > 0 else ''}"
        else:
            note = "手头原料已齐全，可以直接开做。"
        choice = _recipe_choice(
            item,
            len(choices) + 1,
            badge="原料匹配",
            note=note,
            extra_metadata=[
                ("覆盖", f"{coverage * 100:.0f}%"),
                ("已有", f"{hit_count}/{ingredient_total}"),
            ],
        )
        if choice:
            choices.append(choice)
    have = meta.get("have") if isinstance(meta.get("have"), list) else []
    mode = str(meta.get("mode") or "loose")
    mode_label = "严格齐全" if mode == "strict" else "宽松推荐"
    description = (
        f"手头有 {'、'.join(str(value) for value in have) or '这些原料'}；"
        f"按{mode_label}找到 {len(choices)} 道可选菜谱。"
    )
    return Document(
        title="家里有什么，就做什么",
        kicker="HOW TO COOK · PANTRY MATCH",
        description=description,
        stats=[("匹配", str(len(choices))), ("模式", mode_label), ("原料", str(len(have)))],
        sections=_choice_sections(choices)
        or [Section("没有结果", "可以切换宽松模式，或补充更多调味料后再试。")],
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-食材找菜",
        layout="recipe_list",
        recipe_choices=choices,
    )


def related_recipes_document(
    data: Any,
    meta: dict[str, Any],
    *,
    asset_base_url: str,
) -> Document:
    items = data if isinstance(data, list) else []
    choices: list[RecipeListItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        score = item.get("score")
        shared = int(item.get("shared_ingredients") or 0)
        choice = _recipe_choice(
            item,
            len(choices) + 1,
            badge="相似菜谱",
            extra_metadata=[("相似分", _text(score)), ("共同原料", f"{shared} 项")],
        )
        if choice:
            choices.append(choice)
    source_title = _text(meta.get("title"), "这道菜")
    return Document(
        title=f"和「{source_title}」相似的菜",
        kicker="HOW TO COOK · RELATED",
        description="按原料重合度与同分类权重，为你找到这些相近做法。",
        stats=[("推荐", str(len(choices))), ("原菜谱", source_title)],
        sections=_choice_sections(choices) or [Section("没有结果", "暂时没有找到足够相似的菜谱。")],
        asset_base_url=asset_base_url,
        filename_hint=f"HowToCook-{source_title}-相似菜谱",
        layout="recipe_list",
        recipe_choices=choices,
    )


def aggregate_search_document(
    data: Any,
    meta: dict[str, Any],
    *,
    asset_base_url: str,
) -> Document:
    payload = data if isinstance(data, dict) else {}
    recipe_payload = payload.get("recipes") if isinstance(payload.get("recipes"), dict) else {}
    tip_payload = payload.get("tips") if isinstance(payload.get("tips"), dict) else {}
    recipe_items = (
        recipe_payload.get("items") if isinstance(recipe_payload.get("items"), list) else []
    )
    tip_items = tip_payload.get("items") if isinstance(tip_payload.get("items"), list) else []
    choices: list[RecipeListItem] = []
    for item in recipe_items:
        if isinstance(item, dict):
            choice = _recipe_choice(item, len(choices) + 1, badge="菜谱")
            if choice:
                choices.append(choice)
    for item in tip_items:
        if isinstance(item, dict):
            choice = _tip_choice(item, len(choices) + 1)
            if choice:
                choices.append(choice)
    recipe_total = int(recipe_payload.get("total") or 0)
    tip_total = int(tip_payload.get("total") or 0)
    query = _text(meta.get("q"), "关键词")
    return Document(
        title="菜谱与厨房知识",
        kicker="HOW TO COOK · GLOBAL SEARCH",
        description=(
            f"“{query}”共命中 {recipe_total} 道菜谱和 {tip_total} 篇厨房技巧；"
            "当前展示相关度最高的结果。"
        ),
        stats=[("菜谱", str(recipe_total)), ("技巧", str(tip_total)), ("展示", str(len(choices)))],
        sections=_choice_sections(choices)
        or [Section("没有结果", "换个菜名、原料、拼音或知识关键词再试试。")],
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-全局搜索",
        layout="recipe_list",
        recipe_choices=choices,
    )


_PLAN_SLOT_DEFINITIONS = [
    ("meat", "荤菜与水产", "🥩"),
    ("vegetable", "时蔬", "🥬"),
    ("soup", "汤与粥", "🥣"),
    ("breakfast", "早餐", "🌅"),
    ("drink", "饮品", "🥤"),
    ("dessert", "甜品", "🍰"),
]


def _slot_values(value: Any) -> list[int]:
    if isinstance(value, list):
        return [
            int(item)
            for item in value
            if isinstance(item, (int, float, str)) and str(item).isdigit()
        ]
    if isinstance(value, (int, float)):
        return [int(value)]
    if isinstance(value, str):
        return [int(item) for item in re.split(r"[,，]", value) if item.strip().isdigit()]
    return []


def _plan_slot_summary(raw_slots: dict[str, Any], *, daily: bool) -> str:
    parts: list[str] = []
    for key, title, _ in _PLAN_SLOT_DEFINITIONS:
        values = _slot_values(raw_slots.get(key))
        if not values or not any(values):
            continue
        label = "荤菜/水产" if key == "meat" else title
        if daily and len(set(values)) > 1:
            counts = "/".join(str(value) for value in values)
            parts.append(f"{label}按天 {counts} 道")
        elif daily:
            parts.append(f"每天 {values[0]} 道{label}")
        else:
            parts.append(f"{values[0]} 道{label}")
    return " + ".join(parts)


def menu_document(data: Any, meta: dict[str, Any], *, asset_base_url: str) -> Document:
    payload = data if isinstance(data, dict) else {}
    choices: list[RecipeListItem] = []
    groups: list[ChoiceGroup] = []
    sections: list[Section] = []
    for key, title, icon in _PLAN_SLOT_DEFINITIONS:
        raw_items = payload.get(key) if isinstance(payload.get(key), list) else []
        group_items: list[RecipeListItem] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            choice = _recipe_choice(item, len(choices) + 1, badge=title)
            if choice:
                choices.append(choice)
                group_items.append(choice)
        groups.append(ChoiceGroup(key=key, title=title, icon=icon, items=group_items))
        sections.append(
            Section(
                title,
                "\n".join(f"{choice.number}. {choice.title}" for choice in group_items)
                or "本次未安排",
            )
        )
    unfilled = meta.get("unfilled") if isinstance(meta.get("unfilled"), list) else []
    raw_slots = meta.get("slots") if isinstance(meta.get("slots"), dict) else {}
    slot_summary = _plan_slot_summary(raw_slots, daily=False) or f"{len(choices)} 道菜"
    description = f"本次按 {slot_summary} 搭好整桌，也可以调整每类数量和最高难度。"
    if unfilled:
        description += f" 候选池不足：{'、'.join(str(value) for value in unfilled)}。"
    excluded = _diet_labels(meta.get("exclude_tags"))
    if excluded:
        description += f" 已避开：{'、'.join(excluded)}。"
    shopping_ids = [choice.identifier for choice in choices]
    max_difficulty = meta.get("max_difficulty")
    stats = [("共计", f"{len(choices)} 道"), ("种子", _text(meta.get("seed"), "随机"))]
    if max_difficulty is not None:
        stats.insert(1, ("最高难度", f"{max_difficulty} 星"))
    return Document(
        title="七七今日配餐",
        kicker="HOW TO COOK · SMART MENU",
        description=description,
        stats=stats,
        sections=sections,
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-今日配餐",
        layout="menu",
        recipe_choices=choices,
        choice_groups=groups,
        shopping_recipe_ids=shopping_ids,
    )


def week_plan_document(data: Any, meta: dict[str, Any], *, asset_base_url: str) -> Document:
    payload = data if isinstance(data, dict) else {}
    raw_days = payload.get("days") if isinstance(payload.get("days"), list) else []
    choices: list[RecipeListItem] = []
    groups: list[ChoiceGroup] = []
    sections: list[Section] = []
    for fallback_day, raw_day in enumerate(raw_days, 1):
        if not isinstance(raw_day, dict):
            continue
        day_number = int(raw_day.get("day") or fallback_day)
        day_items: list[RecipeListItem] = []
        text_lines: list[str] = []
        for key, badge, icon in _PLAN_SLOT_DEFINITIONS:
            raw_items = raw_day.get(key) if isinstance(raw_day.get(key), list) else []
            titles: list[str] = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                choice = _recipe_choice(item, len(choices) + 1, badge=badge)
                if choice:
                    choices.append(choice)
                    day_items.append(choice)
                    titles.append(f"{choice.number}. {choice.title}")
            text_lines.append(f"{icon} {badge}：{'、'.join(titles) if titles else '未安排'}")
        groups.append(
            ChoiceGroup(
                key=f"day-{day_number}",
                title=f"第 {day_number} 天",
                icon=f"{day_number:02d}",
                items=day_items,
            )
        )
        sections.append(Section(f"第 {day_number} 天", "\n".join(text_lines)))

    repeats = bool(meta.get("repeats"))
    raw_slots = meta.get("slots") if isinstance(meta.get("slots"), dict) else {}
    slot_summary = _plan_slot_summary(raw_slots, daily=True) or "自定义菜谱"
    description = f"当前按 {slot_summary} 生成，计划内菜谱默认不重复。"
    if repeats:
        description = "筛选后的候选池已用尽，计划中包含重复菜谱。"
    unfilled = int(meta.get("unfilled") or 0)
    if unfilled:
        description += f" 候选池不足，仍有 {unfilled} 个槽位未填满。"
    excluded = _diet_labels(meta.get("exclude_tags"))
    if excluded:
        description += f" 已避开：{'、'.join(excluded)}。"
    shopping_ids = [choice.identifier for choice in choices]
    stats = [
        ("计划", f"{len(groups)} 天"),
        ("菜谱", f"{len(choices)} 道"),
        ("种子", _text(meta.get("seed"), "随机")),
    ]
    if meta.get("max_difficulty") is not None:
        stats.append(("最高难度", f"{meta['max_difficulty']} 星"))
    embedded_shopping_list: Document | None = None
    shopping_servings: int | None = None
    raw_shopping = payload.get("shopping_list")
    shopping_meta = meta.get("shopping_list")
    if isinstance(raw_shopping, dict):
        embedded_meta = dict(shopping_meta) if isinstance(shopping_meta, dict) else {}
        embedded_meta.setdefault("requested", len(shopping_ids))
        if meta.get("diet_tags_note") is not None:
            embedded_meta.setdefault("diet_tags_note", meta["diet_tags_note"])
        raw_servings = embedded_meta.get("servings")
        shopping_servings = int(raw_servings) if raw_servings is not None else None
        embedded_shopping_list = shopping_list_document(
            raw_shopping,
            embedded_meta,
            asset_base_url=asset_base_url,
        )
        stats.append(("采购原料", f"{len(embedded_shopping_list.shopping_items)} 项"))
    if len(shopping_ids) > 50:
        if embedded_shopping_list is not None:
            description += " 本计划超过独立清单接口的 50 道上限，已使用上游内嵌整周清单。"
        else:
            description += " 本计划超过独立清单接口的 50 道上限，暂时无法再次汇总。"
    return Document(
        title="七七一周吃什么",
        kicker="HOW TO COOK · WEEKLY PLAN",
        description=description,
        stats=stats,
        sections=sections,
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-一周计划",
        layout="week_plan",
        recipe_choices=choices,
        choice_groups=groups,
        shopping_recipe_ids=shopping_ids if len(shopping_ids) <= 50 else [],
        embedded_shopping_list=embedded_shopping_list,
        shopping_servings=shopping_servings,
    )


def _format_number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _text(value, "0")


def shopping_list_document(data: Any, meta: dict[str, Any], *, asset_base_url: str) -> Document:
    payload = data if isinstance(data, dict) else {}
    raw_items = payload.get("items") if isinstance(payload.get("items"), list) else []
    resolved = payload.get("recipes") if isinstance(payload.get("recipes"), list) else []
    not_found = payload.get("not_found") if isinstance(payload.get("not_found"), list) else []
    items: list[ShoppingListItem] = []
    text_lines: list[str] = []
    section_labels = {"必须配料", "进阶配料", "可选配料", "必须原料", "可选原料"}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        name = _text(raw_item.get("name"), "未命名原料")
        amount_parts: list[str] = []
        amounts = raw_item.get("amounts") if isinstance(raw_item.get("amounts"), list) else []
        for amount in amounts:
            if not isinstance(amount, dict):
                continue
            unit = _text(amount.get("unit"), "")
            amount_parts.append(
                f"{_format_number(amount.get('value'))}{f' {unit}' if unit else ''}"
            )
        unspecified = (
            raw_item.get("unspecified") if isinstance(raw_item.get("unspecified"), list) else []
        )
        if name in section_labels and not amounts and not unspecified:
            continue
        amount_parts.extend(str(value) for value in unspecified if value)
        amount_text = " / ".join(amount_parts) or "按需准备"
        display_names = (
            raw_item.get("display_names") if isinstance(raw_item.get("display_names"), list) else []
        )
        aliases = [str(value) for value in display_names if value and str(value) != name]
        recipes = (
            [str(value) for value in raw_item.get("recipes", []) if value]
            if isinstance(raw_item.get("recipes"), list)
            else []
        )
        items.append(
            ShoppingListItem(
                name=name,
                amount=amount_text,
                aliases=aliases,
                recipes=recipes,
            )
        )
        source = f"（用于 {'、'.join(recipes)}）" if recipes else ""
        text_lines.append(f"□ {name}：{amount_text}{source}")

    recipe_titles = [
        _text(item.get("title"))
        for item in resolved
        if isinstance(item, dict) and item.get("title")
    ]
    sections = [
        Section("包含菜谱", "、".join(recipe_titles) or "没有成功解析的菜谱"),
        Section("采购明细", "\n".join(text_lines) or "没有可汇总的原料"),
    ]
    if not_found:
        sections.append(Section("未找到", "、".join(str(value) for value in not_found)))
    servings = meta.get("servings")
    description = f"已合并 {len(recipe_titles)} 道菜的同名原料与同单位用量。"
    if servings is not None:
        description += (
            f" 数值用量按 {servings} 人份换算：公式型每份用量按人数计算，"
            "其余数值量按菜谱基准比例调整。"
        )
    description += " “适量”等无法计算的写法会原样保留。"
    stats = [
        ("菜谱", str(len(recipe_titles))),
        ("原料", str(len(items))),
        ("未找到", str(len(not_found))),
    ]
    if servings is not None:
        stats.insert(2, ("份数", f"{servings} 人"))
    return Document(
        title="七七采购清单",
        kicker="HOW TO COOK · SHOPPING LIST",
        description=description,
        stats=stats,
        sections=sections,
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-购物清单",
        layout="shopping_list",
        shopping_items=items,
    )


def _chart_group(title: str, values: list[tuple[str, int]], description: str = "") -> ChartGroup:
    maximum = max((value for _, value in values), default=0)
    bars = [
        ChartBar(
            label=label,
            value=str(value),
            percent=round(value / maximum * 100, 1) if maximum else 0,
        )
        for label, value in values
    ]
    return ChartGroup(title=title, description=description, bars=bars)


def stats_document(data: Any, *, asset_base_url: str) -> Document:
    payload = data if isinstance(data, dict) else {}
    categories = payload.get("categories") if isinstance(payload.get("categories"), list) else []
    category_values = [
        (_text(item.get("title")), int(item.get("count") or 0))
        for item in categories
        if isinstance(item, dict)
    ]
    difficulty = payload.get("difficulty") if isinstance(payload.get("difficulty"), dict) else {}
    difficulty_values = [
        (f"难度 {level} 星", int(difficulty.get(str(level)) or 0)) for level in range(1, 6)
    ]
    methods = payload.get("methods") if isinstance(payload.get("methods"), list) else []
    method_values = [
        (_text(item.get("name")), int(item.get("count") or 0))
        for item in methods[:10]
        if isinstance(item, dict)
    ]
    ingredients = (
        payload.get("top_ingredients") if isinstance(payload.get("top_ingredients"), list) else []
    )
    ingredient_values = [
        (_text(item.get("name")), int(item.get("count") or 0))
        for item in ingredients[:12]
        if isinstance(item, dict)
    ]
    charts = [
        _chart_group("分类分布", category_values, "社区菜谱在各类目中的数量"),
        _chart_group("难度分布", difficulty_values, "从一星入门到五星挑战"),
        _chart_group("常见烹饪方式", method_values, "按菜谱中识别到的烹饪方式统计"),
        _chart_group("高频原料", ingredient_values, "同义原料已归一后统计"),
    ]
    avg_calories = payload.get("avg_calories")
    with_time = int(payload.get("recipes_with_time_estimate") or 0)
    sections = [
        Section("分类分布", "\n".join(f"• {name}：{count}" for name, count in category_values)),
        Section("难度分布", "\n".join(f"• {name}：{count}" for name, count in difficulty_values)),
        Section("常见方式", "\n".join(f"• {name}：{count}" for name, count in method_values)),
        Section("高频原料", "\n".join(f"• {name}：{count}" for name, count in ingredient_values)),
    ]
    return Document(
        title="HowToCook 全库一览",
        kicker="HOW TO COOK · DATA INSIGHTS",
        description="从分类、难度、做法与高频原料，快速认识整个社区菜谱库。",
        stats=[
            ("菜谱", str(payload.get("recipes") or 0)),
            ("技巧", str(payload.get("tips") or 0)),
            ("平均热量", f"{_text(avg_calories)} 大卡"),
            ("标注耗时", str(with_time)),
        ],
        sections=sections,
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-全库统计",
        layout="stats",
        charts=charts,
    )


def _short_commit(value: Any) -> str:
    text = _text(value, "未知")
    return text[:10] if len(text) >= 10 else text


def content_info_document(data: Any, *, asset_base_url: str) -> Document:
    payload = data if isinstance(data, dict) else {}
    if not payload.get("tracked"):
        return Document(
            title="菜谱内容版本",
            kicker="HOW TO COOK · CONTENT VERSION",
            description="当前内容目录没有 Git 版本信息。",
            sections=[Section("状态", _text(payload.get("reason"), "无法管理内容版本"))],
            asset_base_url=asset_base_url,
            filename_hint="HowToCook-内容版本",
        )
    last_check = payload.get("last_check")
    last_update = payload.get("last_update")
    details = [
        f"完整提交：{_text(payload.get('commit'))}",
        f"提交时间：{_text(payload.get('committed_at'))}",
        f"分支：{_text(payload.get('branch'))}",
        f"上游：{_text(payload.get('remote'))}",
        f"工作区：{'干净' if payload.get('clean') else '存在本地修改'}",
        f"更新器：{'正在更新' if payload.get('updating') else '空闲'}",
        f"最近检查：{_text(last_check.get('at')) if isinstance(last_check, dict) else '尚未检查'}",
        (
            "最近更新："
            f"{_text(last_update.get('at')) if isinstance(last_update, dict) else '尚未更新'}"
        ),
    ]
    return Document(
        title="菜谱内容版本",
        kicker="HOW TO COOK · CONTENT VERSION",
        description="查看 HowToCook 社区内容快照与更新器状态，不会修改内容。",
        stats=[
            ("提交", _short_commit(payload.get("commit"))),
            ("分支", _text(payload.get("branch"))),
            ("工作区", "干净" if payload.get("clean") else "有修改"),
        ],
        sections=[Section("版本详情", "\n".join(details))],
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-内容版本",
    )


def content_check_document(data: Any, *, asset_base_url: str) -> Document:
    payload = data if isinstance(data, dict) else {}
    up_to_date = bool(payload.get("up_to_date"))
    details = [
        f"本地提交：{_text(payload.get('local'))}",
        f"上游提交：{_text(payload.get('remote'))}",
        f"本地提交时间：{_text(payload.get('local_committed_at'))}",
        f"检查时间：{_text(payload.get('checked_at'))}",
        f"上游地址：{_text(payload.get('remote_url'))}",
    ]
    return Document(
        title="菜谱内容检查",
        kicker="HOW TO COOK · UPDATE CHECK",
        description="当前内容已经是最新版本。" if up_to_date else "检测到上游有新的菜谱内容。",
        stats=[
            ("状态", "已是最新" if up_to_date else "发现更新"),
            ("本地", _short_commit(payload.get("local"))),
            ("上游", _short_commit(payload.get("remote"))),
        ],
        sections=[
            Section("检查结果", "\n".join(details)),
            Section("安全说明", "插件只提供版本检查，不向聊天用户开放内容更新操作。"),
        ],
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-内容检查",
    )


def content_changelog_document(
    data: Any,
    meta: dict[str, Any],
    *,
    asset_base_url: str,
    limit: int,
) -> Document:
    payload = data if isinstance(data, dict) else {}
    definitions = [
        ("added", "新增菜谱", "NEW", "新增", "created_at"),
        ("updated", "近期更新", "UP", "更新", "updated_at"),
    ]
    choices: list[RecipeListItem] = []
    groups: list[ChoiceGroup] = []
    sections: list[Section] = []
    candidates: list[tuple[float, int]] = []
    for key, _title, _icon, _badge, date_key in definitions:
        raw_items = payload.get(key) if isinstance(payload.get(key), list) else []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            value = str(item.get(date_key) or "")
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                timestamp = parsed.timestamp()
            except ValueError:
                timestamp = 0
            candidates.append((timestamp, id(item)))
    selected_ids = {
        identity
        for _timestamp, identity in sorted(
            candidates,
            key=lambda candidate: candidate[0],
            reverse=True,
        )[:limit]
    }
    for key, title, icon, badge, date_key in definitions:
        raw_items = payload.get(key) if isinstance(payload.get(key), list) else []
        group_items: list[RecipeListItem] = []
        for item in raw_items:
            if not isinstance(item, dict) or id(item) not in selected_ids:
                continue
            changed_at = _text(item.get(date_key), "未知时间")[:10]
            choice = _recipe_choice(
                item,
                len(choices) + 1,
                badge=badge,
                extra_metadata=[("日期", changed_at)],
            )
            if choice:
                choices.append(choice)
                group_items.append(choice)
        groups.append(ChoiceGroup(key=key, title=title, icon=icon, items=group_items))
        sections.append(
            Section(
                title,
                "\n".join(
                    f"{choice.number}. {choice.title} · {choice.metadata[0][1]}"
                    for choice in group_items
                )
                or "这个时间段内没有记录",
            )
        )
    added_total = int(meta.get("added") or 0)
    updated_total = int(meta.get("updated") or 0)
    days = int(meta.get("days") or 30)
    description = (
        f"回看最近 {days} 天的内容变化，共新增 {added_total} 道、更新 {updated_total} 道；"
        f"本卡展示最近 {len(choices)} 道。"
    )
    return Document(
        title="HowToCook 内容更新",
        kicker="HOW TO COOK · CHANGELOG",
        description=description,
        stats=[
            ("窗口", f"{days} 天"),
            ("新增", str(added_total)),
            ("更新", str(updated_total)),
            ("展示", str(len(choices))),
        ],
        sections=sections,
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-更新日志",
        layout="changelog",
        recipe_choices=choices,
        choice_groups=groups,
    )


def categories_document(data: Any, meta: dict[str, Any], *, asset_base_url: str) -> Document:
    items = data if isinstance(data, list) else []
    lines = []
    recipe_total = 0
    for item in items:
        if isinstance(item, dict):
            title = _text(item.get("title"))
            identifier = _text(item.get("id"))
            count = _text(item.get("count"), "0")
            if str(count).isdigit():
                recipe_total += int(count)
            lines.append(f"• {title}（{identifier}）：{count} 道")
    return Document(
        title="菜谱分类",
        kicker="HOW TO COOK · CATEGORIES",
        description=f"按分类浏览 {recipe_total} 道社区菜谱。",
        stats=[("分类", str(meta.get("total") or len(items)))],
        sections=[Section("全部分类", "\n".join(lines) or "暂无分类")],
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-分类",
    )


def health_document(data: Any, *, asset_base_url: str) -> Document:
    payload = data if isinstance(data, dict) else {}
    stats = [
        ("菜谱", str(payload.get("recipes") or 0)),
        ("技巧", str(payload.get("tips") or 0)),
        ("分类", str(payload.get("categories") or 0)),
    ]
    details = [
        f"索引状态：{_text(payload.get('status'))}",
        f"构建时间：{_text(payload.get('index_built_at'))}",
        f"Git 元数据：{'可用' if payload.get('git_metadata') else '不可用'}",
        f"默认图片模式：{_text(payload.get('image_mode_default'))}",
    ]
    return Document(
        title="HowToCook API 状态",
        kicker="HOW TO COOK · HEALTH",
        description="只读菜谱索引服务运行正常。",
        stats=stats,
        sections=[Section("服务信息", "\n".join(details))],
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-API状态",
    )


def tips_list_document(data: Any, meta: dict[str, Any], *, asset_base_url: str) -> Document:
    items = data if isinstance(data, list) else []
    choices: list[RecipeListItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        choice = _tip_choice(item, len(choices) + 1)
        if choice:
            choices.append(choice)
    total = int(meta.get("total") or len(choices))
    return Document(
        title="烹饪技巧",
        kicker="HOW TO COOK · TIPS",
        description=f"找到 {total} 篇厨房准备、进阶知识与安全提示。",
        stats=[("文档", str(total)), ("页码", f"{meta.get('page', 1)}/{meta.get('pages', 1)}")],
        sections=_choice_sections(choices) or [Section("没有结果", "换个关键词再试试。")],
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-烹饪技巧",
        layout="recipe_list",
        recipe_choices=choices,
    )


def tip_document(data: Any, *, asset_base_url: str) -> Document:
    if not isinstance(data, dict):
        return generic_document("烹饪技巧", data, asset_base_url=asset_base_url)
    cover_url, cover_alt = _cover(data)
    content = data.get("content")
    markdown = content.get("markdown") if isinstance(content, dict) else None
    sections = [
        Section(
            "来源信息",
            "\n".join(
                [
                    f"文档 ID：{_text(data.get('id'))}",
                    f"分组：{_text(data.get('group'))}",
                    f"作者：{_author_name(data.get('author'))}",
                    f"更新时间：{_text(data.get('updated_at'))}",
                ]
            ),
        )
    ]
    return Document(
        title=_text(data.get("title"), "烹饪技巧"),
        kicker="HOW TO COOK · KITCHEN TIPS",
        description=_compact_description(data.get("description"), 180),
        stats=[("分组", _text(data.get("group"))), ("作者", _author_name(data.get("author")))],
        sections=sections,
        cover_url=cover_url,
        cover_alt=cover_alt,
        article_markdown=str(markdown) if markdown else None,
        asset_base_url=asset_base_url,
        filename_hint=f"HowToCook-{_text(data.get('title'), '技巧')}",
    )


def _json_markdown(data: Any) -> str:
    return f"```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```"


def generic_document(
    title: str,
    data: Any,
    *,
    asset_base_url: str,
    content_type: str = "application/json",
) -> Document:
    if isinstance(data, bytes):
        return Document(
            title=title,
            description=f"二进制资源，共 {len(data)} 字节。",
            sections=[Section("资源信息", f"Content-Type：{content_type}")],
            attachment=data,
            attachment_content_type=content_type,
            asset_base_url=asset_base_url,
        )
    if isinstance(data, str):
        markdown = data if content_type in {"text/markdown", "text/plain"} else None
        html = data if content_type == "text/html" else None
        if markdown is None and html is None:
            markdown = f"```text\n{data}\n```"
        return Document(
            title=title,
            kicker="HOW TO COOK · DOCUMENT",
            article_markdown=markdown,
            article_html=html,
            asset_base_url=asset_base_url,
            filename_hint=f"HowToCook-{title}",
        )
    return Document(
        title=title,
        kicker="HOW TO COOK · API",
        article_markdown=_json_markdown(data),
        asset_base_url=asset_base_url,
        filename_hint=f"HowToCook-{title}",
    )


def result_document(
    title: str,
    result: APIResult,
    *,
    asset_base_url: str,
) -> Document:
    return generic_document(
        title,
        result.data,
        asset_base_url=asset_base_url,
        content_type=result.content_type,
    )


def recipe_resource_document(
    resource: str,
    result: APIResult,
    *,
    asset_base_url: str,
) -> Document:
    data = result.data
    meta = result.meta
    title = _text(meta.get("title"), "菜谱")
    if resource == "meta" and isinstance(data, dict):
        cover_url, cover_alt = _cover(data)
        counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
        details = [
            f"菜谱 ID：{_text(data.get('id'))}",
            f"作者：{_author_name(data.get('author'))}",
            f"编写时间：{_text(data.get('created_at'))}",
            f"更新时间：{_text(data.get('updated_at'))}",
            (
                "内容统计："
                f"原料 {counts.get('ingredients', 0)} · 工具 {counts.get('tools', 0)} · "
                f"步骤 {counts.get('steps', 0)} · 图片 {counts.get('images', 0)}"
            ),
        ]
        return Document(
            title=_text(data.get("title"), "菜谱元信息"),
            kicker="HOW TO COOK · METADATA",
            description=_compact_description(data.get("description")),
            stats=_recipe_stats(data),
            sections=[Section("来源与统计", "\n".join(details))],
            cover_url=cover_url,
            cover_alt=cover_alt,
            asset_base_url=asset_base_url,
            filename_hint=f"HowToCook-{title}-元信息",
        )
    if resource == "ingredients":
        per_serving_factor = meta.get("per_serving_factor")
        sections = [
            Section(
                "完整原料与用量",
                _ingredient_lines(data, per_serving_factor=per_serving_factor),
            )
        ]
        if meta.get("servings") is not None:
            scaling_lines = [
                (
                    f"目标 {meta['servings']} 人份；原菜谱按 "
                    f"{meta.get('base_servings', 2)} 人份计算。"
                ),
                "",
            ]
            if meta.get("factor") is not None:
                scaling_lines.append(
                    f"- 静态数量：×{_text(meta.get('factor'))}（目标份数 ÷ 基准份数）"
                )
            else:
                scaling_lines.append("- 静态数量：按目标份数与菜谱基准份数换算")
            if per_serving_factor is not None:
                unchanged = (
                    "；系数为 1 时数量保持不变" if _is_unit_factor(per_serving_factor) else ""
                )
                scaling_lines.append(
                    f"- 公式型每份量：×{_text(per_serving_factor)}（每份基准 × 目标份数"
                    f"{unchanged}）"
                )
            else:
                scaling_lines.append("- 公式型每份量：直接按目标人数换算（兼容旧版 API）")
            if meta.get("note"):
                scaling_lines.extend(["", "上游 API 说明：", f"> {meta['note']}"])
            scaling_lines.extend(["", "中文数量词会先规范化；“适量”等模糊写法保留原文。"])
            sections.append(
                Section(
                    "份数换算说明",
                    "\n".join(scaling_lines),
                )
            )
    elif resource == "tools":
        sections = [Section("所需工具", _tool_lines(data))]
    elif resource == "steps":
        sections = [Section("烹饪步骤", _step_lines(data))]
    elif resource == "notes" and isinstance(data, dict):
        sections = [Section("附加说明", _notes_lines(data) or "暂无附加说明")]
    elif resource == "sections" and isinstance(data, list):
        sections = []
        markdown_parts = []
        for item in data:
            if not isinstance(item, dict):
                continue
            heading = _text(item.get("heading"), "正文")
            markdown = _text(item.get("markdown"), "")
            sections.append(Section(heading, _plain_markdown(markdown)))
            markdown_parts.append(f"## {heading}\n\n{markdown}")
        return Document(
            title=f"{title} · 原始段落",
            kicker="HOW TO COOK · SECTIONS",
            sections=sections,
            article_markdown="\n\n".join(markdown_parts),
            asset_base_url=asset_base_url,
            filename_hint=f"HowToCook-{title}-段落",
        )
    elif resource == "images" and isinstance(data, list):
        cover_url, cover_alt = _cover({"images": data})
        lines = []
        markdown_parts = []
        for index, item in enumerate(data, 1):
            if not isinstance(item, dict):
                continue
            alt = _text(item.get("alt"), f"图片 {index}")
            url = _text(item.get("url"), "")
            lines.append(f"{index}. {alt}\n   {url}")
            if url:
                markdown_parts.append(f"### {index}. {alt}\n\n![{alt}]({url})")
        return Document(
            title=f"{title} · 图片",
            kicker="HOW TO COOK · IMAGES",
            description=f"共 {len(data)} 张菜谱图片。",
            sections=[Section("图片清单", "\n".join(lines) or "暂无图片")],
            cover_url=cover_url,
            cover_alt=cover_alt,
            article_markdown="\n\n".join(markdown_parts) or None,
            asset_base_url=asset_base_url,
            filename_hint=f"HowToCook-{title}-图片",
        )
    else:
        return result_document(
            f"{title} · {resource}",
            result,
            asset_base_url=asset_base_url,
        )
    stats = [("条目", str(meta.get("total") or 0)), ("菜谱 ID", _text(meta.get("id")))]
    if resource == "ingredients" and meta.get("servings") is not None:
        stats = [("条目", str(meta.get("total") or 0)), ("目标份数", f"{meta['servings']} 人")]
        if meta.get("factor") is not None:
            stats.append(("静态量", f"×{_text(meta.get('factor'))}"))
        if meta.get("per_serving_factor") is not None:
            stats.append(("每份量", f"×{_text(meta.get('per_serving_factor'))}"))
        stats.append(("菜谱 ID", _text(meta.get("id"))))
    return Document(
        title=f"{title} · {sections[0].title}",
        kicker="HOW TO COOK · STRUCTURED DATA",
        stats=stats,
        sections=sections,
        asset_base_url=asset_base_url,
        filename_hint=f"HowToCook-{title}-{resource}",
    )


def split_text(value: str, limit: int) -> list[str]:
    """Split text on natural boundaries without losing any content."""

    text = value.strip()
    if not text:
        return []
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            for offset in range(0, len(line), limit):
                chunks.append(line[offset : offset + limit].rstrip())
            continue
        if current and len(current) + len(line) > limit:
            chunks.append(current.rstrip())
            current = line
        else:
            current += line
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def markdown_sections(sections: Iterable[Section]) -> str:
    return "\n\n".join(f"## {section.title}\n\n{section.text}" for section in sections)


def help_document(*, asset_base_url: str) -> Document:
    sections = [
        Section(
            "智能推荐",
            "\n".join(
                [
                    "• 做饭 随机 [数量] [--分类 soup] [--难度 2]",
                    "• 做饭 配餐 [--荤 1 --素 1 --汤 1 --早餐 1 --饮料 1 --甜品 1] [--人数 4]",
                    "• 做饭 周计划 [天数] [--荤 1,2,1 --素 1 --汤 0 --早餐 1,0] [--人数 4]",
                    "• 六类槽位均支持 0–3；周计划逗号序列会按天循环，如 1,2,1",
                    "• 配餐后回复“合并详情 4人”：完整菜谱卡 + 整桌购物清单",
                    "• 周计划后回复“第1天 4人”或“全部详情 4人”获取合并详情",
                    "• 配餐/周计划卡片后可回复“购物清单”或“购物清单 4”",
                    "• 做饭 购物清单 宫保鸡丁,炒滑蛋 [--份数 4]",
                    "• 做饭 食材 鸡蛋 西红柿 [--严格] [--数量 8]",
                    "• 做饭 相关 <菜谱 ID或路径> [--数量 5]",
                    "• 一个候选会直接打开详情；多个候选回复卡片序号选择",
                ]
            ),
        ),
        Section(
            "搜索与筛选",
            "\n".join(
                [
                    "• 做饭 搜索 红烧肉",
                    "• 做饭 hsr（支持拼音全拼/首字母）",
                    "• 做饭 搜索 土豆 --原料 牛肉 --最高难度 3 --页 1",
                    "• 做饭 搜索 --标签 素食 --忌口 辣,麸质",
                    "• 仅一个结果会直接展示详情；多个结果发送卡片序号选择",
                    "• 做饭 全局搜索 备菜（同时搜索菜谱与厨房技巧）",
                    "• 做饭 分类",
                    "• 做饭 统计",
                ]
            ),
        ),
        Section(
            "完整菜谱",
            "\n".join(
                [
                    "• 通常直接在搜索结果后回复序号，无需手动复制 ID",
                    "• 进阶直达：做饭 详情 <ID或路径>",
                    "• 做饭 原料/工具/步骤/段落/备注/图片 <ID>",
                    "• 做饭 原料 <ID> --份数 4（按人数换算数值用量）",
                    "• 做饭 元信息/Markdown/HTML/原文/JSONLD <ID>",
                ]
            ),
        ),
        Section(
            "烹饪技巧",
            "\n".join(
                [
                    "• 做饭 技巧 [关键词] [--分组 advanced]",
                    "• 做饭 技巧详情 <ID>",
                    "• 做饭 技巧元信息/技巧MD/技巧HTML/技巧原文 <ID>",
                ]
            ),
        ),
        Section(
            "版本、输出与高级入口",
            "\n".join(
                [
                    "• 做饭 内容版本 / 内容检查 / 更新日志 [天数]",
                    "• 任意命令追加 --模式 合并|单条|组合|渲染",
                    "• 渲染命令可追加 --主题 自动|白天|夜间",
                    "• 做饭 接口 plan/week seed=qiqi（受控只读 GET 入口）",
                    "• 做饭 健康",
                ]
            ),
        ),
    ]
    return Document(
        title="今天吃什么？",
        kicker="HOW TO COOK · COMMAND GUIDE",
        description="从一餐到一周计划，自动汇总采购清单，并查看完整做法与厨房技巧。",
        stats=[("新版", "周计划 / 购物清单"), ("模式", "长图 / 合并 / 单条 / 组合")],
        sections=sections,
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-帮助",
    )
