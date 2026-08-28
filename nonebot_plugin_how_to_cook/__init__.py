from nonebot import require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_htmlrender")

from .config import Config  # noqa: E402
from .matcher import how_to_cook as how_to_cook  # noqa: E402

__version__ = "0.1.0"

_MENU_GROUP = {
    "key": "utilities",
    "name": "查询与工具",
    "description": "天气、铁路、域名、账号、百科、菜谱和 API 查询工具。",
    "sort_order": 40,
}

__plugin_meta__ = PluginMetadata(
    name="HowToCook 菜谱",
    description="搜索 HowToCook 菜谱并展示完整原料、步骤、成品图和烹饪技巧",
    usage="做饭 帮助｜做饭 搜索 <菜名/拼音/原料>｜做饭 详情 <ID>",
    type="application",
    homepage="https://github.com/LoCCai/nonebot-plugin-how-to-cook",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "Author": "LoCCai",
        "License": "MIT",
        "version": __version__,
        "menu_data": [
            {
                "func": "菜谱搜索与筛选",
                "trigger_method": (
                    "- **命令**：`<命令前缀>做饭 搜索 <菜名|拼音|原料> [筛选]`\n"
                    "- **命令**：`<命令前缀>做饭 <关键词>`\n"
                    "- **命令**：`<命令前缀>做饭 分类`"
                ),
                "trigger_condition": "群聊与私聊用户；HowToCook API 可访问",
                "brief_des": "按标题、拼音、原料和正文模糊搜索，并支持分类、难度、排序与分页。",
                "detail_des": (
                    "搜索支持中文标题、拼音全拼、拼音首字母、原料和正文。"
                    "可追加 `--分类`、`--难度`、`--最高难度`、`--原料`、"
                    "`--排序`、`--页` 和 `--每页`。\n\n## 示例\n\n"
                    "- `<命令前缀>做饭 hsr`\n"
                    "- `<命令前缀>做饭 搜索 土豆 --原料 牛肉 --最高难度 3`"
                ),
                "pmn_hidden": False,
                "pmn_triggers": [
                    {
                        "type": "command",
                        "label": "命令",
                        "value": "<命令前缀>做饭 搜索 <关键词> [筛选]",
                    },
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 <关键词>"},
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 分类"},
                ],
                "pmn_group": _MENU_GROUP,
            },
            {
                "func": "完整菜谱与结构化子资源",
                "trigger_method": (
                    "- **命令**：`<命令前缀>做饭 详情 <ID或路径>`\n"
                    "- **命令**：`<命令前缀>做饭 原料|工具|步骤|段落|备注|图片 <ID>`\n"
                    "- **命令**：`<命令前缀>做饭 元信息|Markdown|HTML|原文 <ID>`"
                ),
                "trigger_condition": "使用搜索结果中的稳定 ID，或 URL 编码后的仓库相对路径",
                "brief_des": "查看菜谱完整字段、正文、图片与每一类结构化数据。",
                "detail_des": (
                    "详情包含分类、难度、卡路里、用时、烹饪方式、作者、完整原料、"
                    "工具、步骤、备注、正文与成品图。所有 recipes 子接口均有直接命令入口。"
                ),
                "pmn_hidden": False,
                "pmn_triggers": [
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 详情 <ID或路径>"},
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 步骤 <ID>"},
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 Markdown <ID>"},
                ],
                "pmn_group": _MENU_GROUP,
            },
            {
                "func": "厨房技巧文档",
                "trigger_method": (
                    "- **命令**：`<命令前缀>做饭 技巧 [关键词] [--分组 <group>]`\n"
                    "- **命令**：`<命令前缀>做饭 技巧详情 <ID>`\n"
                    "- **命令**：`<命令前缀>做饭 技巧元信息|技巧MD|技巧HTML|技巧原文 <ID>`"
                ),
                "trigger_condition": "群聊与私聊用户",
                "brief_des": "搜索并查看 HowToCook 的厨房准备、进阶知识与安全提示。",
                "detail_des": (
                    "覆盖 tips 列表、详情、元信息、Markdown、HTML 与原始文档接口。"
                    "长篇技巧会自动排版成长图，超过阈值时在群聊转为群文件。"
                ),
                "pmn_hidden": False,
                "pmn_triggers": [
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 技巧 [关键词]"},
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 技巧详情 <ID>"},
                ],
                "pmn_group": _MENU_GROUP,
            },
            {
                "func": "输出模式与完整 API 入口",
                "trigger_method": (
                    "- **参数**：`--模式 合并|单条|组合|渲染`\n"
                    "- **参数**：`--主题 自动|白天|夜间`\n"
                    "- **命令**：`<命令前缀>做饭 接口 <路径> [key=value ...]`\n"
                    "- **命令**：`<命令前缀>做饭 健康`"
                ),
                "trigger_condition": "通用入口仅允许 HowToCook 的只读 GET 路由，不接受任意外部 URL",
                "brief_des": "单次覆盖全局输出/主题设置，或调用受控的完整 API 路由。",
                "detail_des": (
                    "全局支持合并消息、单消息、组合消息与 HTML 长图。"
                    "自动主题时按配置时区和时间段切换昼夜样式；默认 23:00–08:00 "
                    "为夜间。通用接口入口只允许 health、categories、recipes、tips 与 assets 路径。"
                ),
                "pmn_hidden": False,
                "pmn_triggers": [
                    {
                        "type": "command",
                        "label": "命令",
                        "value": "<命令前缀>做饭 接口 recipes q=番茄 page_size=5",
                    },
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 健康"},
                ],
                "pmn_group": _MENU_GROUP,
            },
        ],
        "pmn": {
            "markdown": True,
            "sort_order": 115,
            "menu_group": _MENU_GROUP,
        },
    },
)
