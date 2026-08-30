from __future__ import annotations

import asyncio
import re

from .api import HowToCookClient
from .commands import CommandError, ParsedCommand
from .config import Config
from .content import (
    Document,
    RecipeListItem,
    aggregate_search_document,
    categories_document,
    content_changelog_document,
    content_check_document,
    content_info_document,
    health_document,
    help_document,
    ingredients_discovery_document,
    menu_document,
    random_recipes_document,
    recipe_document,
    recipe_list_document,
    recipe_resource_document,
    related_recipes_document,
    result_document,
    shopping_list_document,
    stats_document,
    tip_document,
    tips_list_document,
    week_plan_document,
)

_RECIPE_RESOURCES = {
    "recipe_meta": ("meta", "菜谱元信息"),
    "ingredients": ("ingredients", "菜谱原料"),
    "tools": ("tools", "菜谱工具"),
    "steps": ("steps", "烹饪步骤"),
    "sections": ("sections", "菜谱原始段落"),
    "notes": ("notes", "菜谱备注"),
    "images": ("images", "菜谱图片"),
    "markdown": ("markdown", "菜谱 Markdown"),
    "html": ("html", "菜谱 HTML"),
    "raw": ("raw", "菜谱原文"),
    "jsonld": ("jsonld", "菜谱 JSON-LD"),
}
_TIP_RESOURCES = {
    "tip_meta": ("meta", "技巧元信息"),
    "tip_markdown": ("markdown", "技巧 Markdown"),
    "tip_html": ("html", "技巧 HTML"),
    "tip_raw": ("raw", "技巧原文"),
}


async def fetch_recipe_document(
    client: HowToCookClient,
    identifier: str,
    *,
    image_mode: str,
) -> Document:
    result = await client.recipe(identifier, image_mode=image_mode)
    return recipe_document(result.data, asset_base_url=client.origin)


async def fetch_tip_document(
    client: HowToCookClient,
    identifier: str,
    *,
    image_mode: str,
) -> Document:
    result = await client.tip(identifier, image_mode=image_mode)
    return tip_document(result.data, asset_base_url=client.origin)


async def fetch_selection_document(
    client: HowToCookClient,
    choice: RecipeListItem,
    *,
    image_mode: str,
) -> Document:
    if choice.kind == "tip":
        return await fetch_tip_document(client, choice.identifier, image_mode=image_mode)
    return await fetch_recipe_document(client, choice.identifier, image_mode=image_mode)


async def fetch_shopping_list_document(
    client: HowToCookClient,
    identifiers: list[str],
    *,
    servings: int | None = None,
) -> Document:
    result = await client.shopping_list(identifiers, servings=servings)
    return shopping_list_document(result.data, result.meta, asset_base_url=client.origin)


async def fetch_detail_bundle_documents(
    client: HowToCookClient,
    choices: list[RecipeListItem],
    *,
    image_mode: str,
    servings: int | None = None,
    concurrency: int = 3,
    shopping_document: Document | None = None,
) -> list[Document]:
    """Fetch full recipe cards and the matching shopping list in stable order."""

    if not choices:
        raise ValueError("合并详情至少需要一道菜")
    if len(choices) > 50:
        raise ValueError("合并详情一次最多处理 50 道菜")

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def fetch_detail(choice: RecipeListItem) -> Document:
        async with semaphore:
            return await fetch_selection_document(
                client,
                choice,
                image_mode=image_mode,
            )

    detail_tasks = [fetch_detail(choice) for choice in choices]
    if shopping_document is not None:
        details = await asyncio.gather(*detail_tasks)
        return [*details, shopping_document]
    shopping_task = fetch_shopping_list_document(
        client,
        [choice.identifier for choice in choices],
        servings=servings,
    )
    resolved = await asyncio.gather(*detail_tasks, shopping_task)
    return list(resolved)


_STABLE_RECIPE_ID = re.compile(r"[0-9a-f]{10}\Z", re.I)


async def _resolve_shopping_recipe_ids(
    client: HowToCookClient,
    recipes: list[str],
    *,
    page_size: int,
) -> list[str]:
    identifiers: list[str] = []
    for recipe in recipes:
        if _STABLE_RECIPE_ID.fullmatch(recipe):
            identifier = recipe.casefold()
        else:
            result = await client.recipes(q=recipe, page_size=page_size, fields="id,title")
            items = (
                [item for item in result.data if isinstance(item, dict)]
                if isinstance(result.data, list)
                else []
            )
            exact = [
                item
                for item in items
                if str(item.get("title") or "").strip().casefold() == recipe.strip().casefold()
            ]
            candidates = exact if exact else items
            if not candidates:
                raise CommandError(f"没有找到购物清单中的菜谱：“{recipe}”")
            if len(candidates) > 1:
                names = "、".join(str(item.get("title") or "未命名") for item in candidates[:4])
                raise CommandError(f"“{recipe}”匹配到多道菜（{names}），请写完整菜名")
            identifier = str(candidates[0].get("id") or "")
            if not identifier:
                raise CommandError(f"菜谱“{recipe}”没有可用 ID")
        identifiers.append(identifier)
    return identifiers


async def _expand_single_choice(
    client: HowToCookClient,
    document: Document,
    *,
    image_mode: str,
) -> Document:
    if len(document.recipe_choices) != 1:
        return document
    return await fetch_selection_document(
        client,
        document.recipe_choices[0],
        image_mode=image_mode,
    )


def _check_display_limit(params: dict[str, object], key: str, config: Config) -> None:
    value = params.get(key)
    if value is not None and int(value) > config.how_to_cook_max_page_size:
        raise CommandError(f"单次最多显示 {config.how_to_cook_max_page_size} 条")


def _diet_filter_meta(meta: dict[str, object], params: dict[str, object]) -> dict[str, object]:
    enriched = dict(meta)
    for key in ("tag", "exclude_tags"):
        if params.get(key) is not None and enriched.get(key) is None:
            enriched[key] = params[key]
    return enriched


async def execute_command(
    client: HowToCookClient,
    command: ParsedCommand,
    config: Config,
) -> Document:
    asset_base = client.origin
    image_mode = str(command.params.get("image_mode") or config.how_to_cook_image_mode)

    if command.action == "help":
        return help_document(asset_base_url=asset_base)
    if command.action == "health":
        result = await client.health()
        return health_document(result.data, asset_base_url=asset_base)
    if command.action == "categories":
        result = await client.categories()
        return categories_document(result.data, result.meta, asset_base_url=asset_base)
    if command.action == "search":
        params = dict(command.params)
        page_size = int(params.get("page_size") or config.how_to_cook_default_page_size)
        if page_size > config.how_to_cook_max_page_size:
            raise CommandError(f"每页最多显示 {config.how_to_cook_max_page_size} 条")
        params.update(q=command.query, page_size=page_size, image_mode=image_mode)
        result = await client.recipes(**params)
        document = recipe_list_document(
            result.data,
            _diet_filter_meta(result.meta, params),
            asset_base_url=asset_base,
        )
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "random":
        params = dict(command.params)
        _check_display_limit(params, "count", config)
        params.setdefault("count", 1)
        params.setdefault("image_mode", image_mode)
        result = await client.random_recipes(**params)
        document = random_recipes_document(
            result.data,
            _diet_filter_meta(result.meta, params),
            asset_base_url=asset_base,
        )
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "menu":
        params = dict(command.params)
        # servings controls the linked shopping list, not GET /api/menu itself.
        params.pop("servings", None)
        params.setdefault("image_mode", image_mode)
        result = await client.menu(**params)
        document = menu_document(result.data, result.meta, asset_base_url=asset_base)
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "week_plan":
        params = dict(command.params)
        params.setdefault("days", 7)
        # The upgraded endpoint can aggregate the whole plan without the
        # standalone shopping-list endpoint's 50-recipe limit.
        params.setdefault("with_shopping_list", 1)
        params.setdefault("image_mode", image_mode)
        result = await client.week_plan(**params)
        document = week_plan_document(result.data, result.meta, asset_base_url=asset_base)
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "shopping_list":
        params = dict(command.params)
        raw_recipes = params.pop("recipes", [])
        recipes = [str(value) for value in raw_recipes] if isinstance(raw_recipes, list) else []
        identifiers = await _resolve_shopping_recipe_ids(
            client,
            recipes,
            page_size=config.how_to_cook_max_page_size,
        )
        return await fetch_shopping_list_document(
            client,
            identifiers,
            servings=int(params["servings"]) if params.get("servings") is not None else None,
        )
    if command.action == "by_ingredients":
        params = dict(command.params)
        params.setdefault("limit", config.how_to_cook_default_page_size)
        _check_display_limit(params, "limit", config)
        params.setdefault("image_mode", image_mode)
        result = await client.recipes_by_ingredients(**params)
        document = ingredients_discovery_document(
            result.data,
            result.meta,
            asset_base_url=asset_base,
        )
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "related":
        assert command.identifier is not None
        params = dict(command.params)
        params.setdefault("limit", 5)
        _check_display_limit(params, "limit", config)
        result = await client.related_recipes(
            command.identifier,
            limit=int(params["limit"]),
            image_mode=str(params.get("image_mode") or image_mode),
        )
        document = related_recipes_document(
            result.data,
            result.meta,
            asset_base_url=asset_base,
        )
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "aggregate_search":
        assert command.query is not None
        result = await client.search_all(command.query, image_mode=image_mode)
        document = aggregate_search_document(
            result.data,
            result.meta,
            asset_base_url=asset_base,
        )
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "stats":
        result = await client.stats()
        return stats_document(result.data, asset_base_url=asset_base)
    if command.action == "content_info":
        result = await client.content_info()
        return content_info_document(result.data, asset_base_url=asset_base)
    if command.action == "content_check":
        result = await client.content_check()
        return content_check_document(result.data, asset_base_url=asset_base)
    if command.action == "content_changelog":
        params = dict(command.params)
        days = int(params.get("days") or 30)
        limit = int(params.get("limit") or config.how_to_cook_default_page_size)
        _check_display_limit({"limit": limit}, "limit", config)
        result = await client.content_changelog(days=days)
        document = content_changelog_document(
            result.data,
            result.meta,
            asset_base_url=asset_base,
            limit=limit,
        )
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "recipe":
        assert command.identifier is not None
        return await fetch_recipe_document(client, command.identifier, image_mode=image_mode)
    if command.action in _RECIPE_RESOURCES:
        assert command.identifier is not None
        resource, title = _RECIPE_RESOURCES[command.action]
        result = await client.recipe(
            command.identifier,
            resource=resource,
            image_mode=image_mode,
            servings=(
                int(command.params["servings"])
                if resource == "ingredients" and command.params.get("servings") is not None
                else None
            ),
        )
        if resource not in {"markdown", "html", "raw"}:
            return recipe_resource_document(
                resource,
                result,
                asset_base_url=asset_base,
            )
        return result_document(title, result, asset_base_url=asset_base)
    if command.action == "tips":
        params = dict(command.params)
        page_size = int(params.get("page_size") or config.how_to_cook_default_page_size)
        if page_size > config.how_to_cook_max_page_size:
            raise CommandError(f"每页最多显示 {config.how_to_cook_max_page_size} 条")
        params.update(q=command.query, page_size=page_size)
        result = await client.tips(**params)
        document = tips_list_document(result.data, result.meta, asset_base_url=asset_base)
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "tip":
        assert command.identifier is not None
        return await fetch_tip_document(client, command.identifier, image_mode=image_mode)
    if command.action in _TIP_RESOURCES:
        assert command.identifier is not None
        resource, title = _TIP_RESOURCES[command.action]
        result = await client.tip(command.identifier, resource=resource, image_mode=image_mode)
        return result_document(title, result, asset_base_url=asset_base)
    if command.action == "api":
        assert command.identifier is not None
        result = await client.generic(command.identifier, command.params)
        return result_document(
            f"API · {command.identifier}",
            result,
            asset_base_url=asset_base,
        )
    raise CommandError(f"未实现的命令：{command.action}")
