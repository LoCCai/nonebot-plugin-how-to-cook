from __future__ import annotations

from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.params import CommandArg

from .api import HowToCookAPIError, HowToCookClient
from .commands import CommandError, parse_command
from .config import ResponseMode, ThemeMode, plugin_config
from .content import Document, RecipeListItem
from .delivery import DeliveryError, DeliveryResultUnknown, MessageDelivery
from .interaction import (
    DetailBundleSelection,
    ShoppingListSelection,
    send_transient_notice,
    wait_for_selection,
)
from .service import (
    execute_command,
    fetch_detail_bundle_documents,
    fetch_selection_document,
    fetch_shopping_list_document,
)

how_to_cook = on_command(
    "做饭",
    aliases={"怎么做"},
    priority=12,
    block=True,
)

_active_selection_sessions: dict[str, object] = {}


def _selection_session_key(bot: Bot, event: MessageEvent) -> str:
    try:
        session_id = event.get_session_id()
    except Exception:
        session_id = f"event:{id(event)}"
    return f"{getattr(bot, 'self_id', 'unknown')}:{session_id}"


def _claim_selection_session(bot: Bot, event: MessageEvent) -> tuple[str, object]:
    key = _selection_session_key(bot, event)
    token = object()
    if key in _active_selection_sessions:
        logger.debug("HowToCook 新请求已替代同一会话中的旧选择等待")
    _active_selection_sessions[key] = token
    return key, token


def _selection_session_is_current(key: str, token: object) -> bool:
    return _active_selection_sessions.get(key) is token


def _release_selection_session(key: str, token: object) -> None:
    if _selection_session_is_current(key, token):
        _active_selection_sessions.pop(key, None)


def _client() -> HowToCookClient:
    return HowToCookClient(
        plugin_config.how_to_cook_api_base_url,
        timeout=plugin_config.how_to_cook_request_timeout,
        direct_first=plugin_config.how_to_cook_direct_first,
        proxy_fallback=plugin_config.how_to_cook_proxy_fallback,
        image_download_limit=plugin_config.how_to_cook_image_download_bytes,
    )


async def _deliver_document(
    delivery: MessageDelivery,
    bot: Bot,
    event: MessageEvent,
    document: Document,
    *,
    mode: ResponseMode,
    theme: ThemeMode | None,
) -> bool:
    try:
        await delivery.deliver(
            bot,
            event,
            document,
            mode=mode,
            theme=theme,
        )
    except DeliveryError as exc:
        await how_to_cook.finish(str(exc))
    except DeliveryResultUnknown:
        logger.exception("HowToCook 群文件投递结果未知；为避免重复不自动补发")
        return False
    except Exception:
        # A transport error may happen after OneBot accepted a message. Do not
        # issue an automatic second message because that can duplicate content.
        logger.exception("HowToCook 消息投递失败或结果未知，未自动重发")
        return False
    return True


async def _deliver_forward_gallery(
    delivery: MessageDelivery,
    bot: Bot,
    event: MessageEvent,
    documents: list[Document],
    *,
    title: str,
    theme: ThemeMode | None,
) -> bool:
    try:
        await delivery.deliver_forward_gallery(
            bot,
            event,
            documents,
            title=title,
            theme=theme,
        )
    except DeliveryError as exc:
        await how_to_cook.finish(str(exc))
    except DeliveryResultUnknown:
        logger.exception("HowToCook 合并详情投递结果未知；为避免重复不自动补发")
        return False
    except Exception:
        logger.exception("HowToCook 合并详情投递失败或结果未知，未自动重发")
        return False
    return True


def _bundle_choices(
    document: Document,
    selection: DetailBundleSelection,
) -> tuple[list[RecipeListItem], str]:
    if selection.group_index is None:
        label = "整桌详情" if document.layout == "menu" else "整周详情"
        return document.recipe_choices, label
    if not 0 <= selection.group_index < len(document.choice_groups):
        raise ValueError("选择的计划分组不存在")
    group = document.choice_groups[selection.group_index]
    return group.items, group.title


async def _build_and_deliver_bundle(
    delivery: MessageDelivery,
    client: HowToCookClient,
    bot: Bot,
    event: MessageEvent,
    document: Document,
    choices: list[RecipeListItem],
    *,
    label: str,
    image_mode: str,
    servings: int | None,
    theme: ThemeMode | None,
    shopping_document: Document | None = None,
) -> bool:
    try:
        await send_transient_notice(
            bot,
            event,
            f"正在生成{label}的完整菜谱卡与购物清单，完成后会作为一条合并消息发送。",
            delay=plugin_config.how_to_cook_reminder_recall_seconds,
        )
    except Exception:
        logger.exception("HowToCook 合并详情生成提醒发送失败，继续生成")
    try:
        documents = await fetch_detail_bundle_documents(
            client,
            choices,
            image_mode=image_mode,
            servings=servings,
            concurrency=plugin_config.how_to_cook_bundle_fetch_concurrency,
            shopping_document=shopping_document,
        )
    except HowToCookAPIError as exc:
        await how_to_cook.finish(exc.user_message())
    except Exception:
        logger.exception("HowToCook 获取合并详情或购物清单失败")
        await how_to_cook.finish("生成合并详情失败了，请稍后再试。")
    servings_label = f" · {servings} 人份" if servings is not None else ""
    return await _deliver_forward_gallery(
        delivery,
        bot,
        event,
        documents,
        title=f"{document.title} · {label}{servings_label}",
        theme=theme,
    )


async def _handle_how_to_cook(
    bot: Bot,
    event: MessageEvent,
    args: Message,
    *,
    selection_key: str,
    selection_token: object,
) -> None:
    try:
        command = parse_command(args.extract_plain_text().strip())
        client = _client()
        document = await execute_command(client, command, plugin_config)
    except CommandError as exc:
        await how_to_cook.finish(f"参数有误：{exc}\n发送“做饭 帮助”查看完整用法。")
    except HowToCookAPIError as exc:
        await how_to_cook.finish(exc.user_message())
    except ValueError as exc:
        await how_to_cook.finish(f"配置或接口参数有误：{exc}")
    except Exception:
        logger.exception("HowToCook 请求或内容处理失败")
        await how_to_cook.finish("读取菜谱失败了，请稍后再试。")

    mode = command.mode or plugin_config.how_to_cook_response_mode
    delivery = MessageDelivery(plugin_config, client)
    image_mode = str(command.params.get("image_mode") or plugin_config.how_to_cook_image_mode)
    is_plan = document.layout in {"menu", "week_plan"} and bool(document.recipe_choices)
    allow_full_bundle = is_plan and len(document.recipe_choices) <= 50
    requested_servings = (
        int(command.params["servings"]) if command.params.get("servings") is not None else None
    )
    if mode == "forward" and allow_full_bundle:
        embedded_shopping = (
            document.embedded_shopping_list
            if document.shopping_servings == requested_servings
            else None
        )
        await _build_and_deliver_bundle(
            delivery,
            client,
            bot,
            event,
            document,
            document.recipe_choices,
            label="整桌详情" if document.layout == "menu" else "整周详情",
            image_mode=image_mode,
            servings=requested_servings,
            theme=command.theme,
            shopping_document=embedded_shopping,
        )
        return

    delivered = await _deliver_document(
        delivery,
        bot,
        event,
        document,
        mode=mode,
        theme=command.theme,
    )
    if not delivered or len(document.recipe_choices) <= 1:
        return

    choice_count = len(document.recipe_choices)
    allow_shopping_list = bool(
        document.shopping_recipe_ids or document.embedded_shopping_list is not None
    )
    allow_detail_bundle = is_plan
    detail_group_count = len(document.choice_groups) if document.layout == "week_plan" else 0
    selection_timeout = plugin_config.how_to_cook_selection_timeout_seconds
    try:
        if allow_shopping_list and requested_servings is not None:
            shopping_hint = f"；发送“购物清单”沿用 {requested_servings} 人份，或在后面写新人数覆盖"
        elif allow_shopping_list:
            shopping_hint = "；发送“购物清单”汇总全部用料，或发送“购物清单 4”按 4 人份换算"
        else:
            shopping_hint = ""
        if document.layout == "menu":
            bundle_hint = "；发送“合并详情”查看整桌完整菜谱卡与购物清单"
        elif document.layout == "week_plan":
            bundle_hint = "；发送“第1天”查看当天合并详情"
            if allow_full_bundle:
                bundle_hint += "，发送“全部详情”查看整周合并详情"
        else:
            bundle_hint = ""
        await send_transient_notice(
            bot,
            event,
            (
                f"请在 {selection_timeout} 秒内发送 1–{choice_count} 的序号查看详情；"
                f"菜谱会打开完整做法，技巧会打开全文{shopping_hint}{bundle_hint}；"
                "发送“取消”结束。"
            ),
            delay=plugin_config.how_to_cook_reminder_recall_seconds,
        )
        selected = await wait_for_selection(
            choice_count,
            timeout=selection_timeout,
            allow_shopping_list=allow_shopping_list,
            allow_detail_bundle=allow_detail_bundle,
            detail_group_count=detail_group_count,
            allow_full_bundle=allow_full_bundle,
        )
    except Exception:
        if _selection_session_is_current(selection_key, selection_token):
            logger.exception("HowToCook 等待菜谱序号失败")
        else:
            logger.debug("HowToCook 被替代的旧选择等待已结束")
        return

    if not _selection_session_is_current(selection_key, selection_token):
        logger.info("HowToCook 已忽略被新请求替代的旧选择回复")
        return

    if selected is None:
        await send_transient_notice(
            bot,
            event,
            "本次菜谱选择已超时，请重新发送“做饭 <关键词>”搜索。",
            delay=plugin_config.how_to_cook_reminder_recall_seconds,
        )
        return
    if isinstance(selected, ShoppingListSelection):
        selected_servings = (
            selected.servings if selected.servings is not None else requested_servings
        )
        if (
            document.embedded_shopping_list is not None
            and document.shopping_servings == selected_servings
        ):
            shopping_document = document.embedded_shopping_list
        elif not document.shopping_recipe_ids:
            await how_to_cook.finish(
                "这份计划超过独立清单接口的 50 道上限；请重新发送周计划并追加“--人数 "
                f"{selected_servings}”以由上游直接生成对应清单。"
                if selected_servings is not None
                else "这份计划超过独立清单接口的 50 道上限；请重新发送不带“--人数”的周计划，"
                "由上游直接生成原始份数清单。"
            )
            return
        else:
            try:
                shopping_document = await fetch_shopping_list_document(
                    client,
                    document.shopping_recipe_ids,
                    servings=selected_servings,
                )
            except HowToCookAPIError as exc:
                await how_to_cook.finish(exc.user_message())
            except Exception:
                logger.exception("HowToCook 汇总购物清单失败")
                await how_to_cook.finish("汇总购物清单失败了，请稍后再试。")
        await _deliver_document(
            delivery,
            bot,
            event,
            shopping_document,
            mode=mode,
            theme=command.theme,
        )
        return
    if isinstance(selected, DetailBundleSelection):
        try:
            choices, label = _bundle_choices(document, selected)
        except ValueError:
            logger.exception("HowToCook 合并详情分组无效")
            return
        selected_servings = (
            selected.servings if selected.servings is not None else requested_servings
        )
        embedded_shopping = (
            document.embedded_shopping_list
            if selected.group_index is None and document.shopping_servings == selected_servings
            else None
        )
        await _build_and_deliver_bundle(
            delivery,
            client,
            bot,
            event,
            document,
            choices,
            label=label,
            image_mode=image_mode,
            servings=selected_servings,
            theme=command.theme,
            shopping_document=embedded_shopping,
        )
        return
    if selected < 0:
        await send_transient_notice(
            bot,
            event,
            "已取消本次菜谱选择。",
            delay=plugin_config.how_to_cook_reminder_recall_seconds,
        )
        return

    choice = document.recipe_choices[selected]
    try:
        selected_document = await fetch_selection_document(
            client,
            choice,
            image_mode=image_mode,
        )
    except HowToCookAPIError as exc:
        await how_to_cook.finish(exc.user_message())
    except Exception:
        logger.exception("HowToCook 获取所选条目详情失败")
        await how_to_cook.finish("读取所选内容失败了，请稍后再试。")

    await _deliver_document(
        delivery,
        bot,
        event,
        selected_document,
        mode=mode,
        theme=command.theme,
    )


@how_to_cook.handle()
async def handle_how_to_cook(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:
    selection_key, selection_token = _claim_selection_session(bot, event)
    try:
        await _handle_how_to_cook(
            bot,
            event,
            args,
            selection_key=selection_key,
            selection_token=selection_token,
        )
    finally:
        _release_selection_session(selection_key, selection_token)
