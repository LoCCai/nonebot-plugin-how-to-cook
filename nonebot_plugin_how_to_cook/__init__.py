from nonebot import require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_htmlrender")
require("nonebot_plugin_waiter")

from .config import Config  # noqa: E402
from .matcher import how_to_cook as how_to_cook  # noqa: E402

__version__ = "0.2.0"

_MENU_GROUP = {
    "key": "utilities",
    "name": "查询与工具",
    "description": "天气、铁路、域名、账号、百科、菜谱和 API 查询工具。",
    "sort_order": 40,
}

__plugin_meta__ = PluginMetadata(
    name="HowToCook 菜谱",
    description="HowToCook 智能推荐、配餐、原料找菜、全库搜索与完整菜谱客户端",
    usage="做饭 随机｜做饭 配餐｜做饭 食材 鸡蛋 西红柿｜做饭 <关键词>",
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
                "func": "智能推荐、配餐与食材找菜",
                "trigger_method": (
                    "- **命令**：`<命令前缀>做饭 随机 [数量] [--分类 <id>] [--难度 1-5]`\n"
                    "- **命令**：`<命令前缀>做饭 配餐 [--荤 1 --素 1 --汤 1 --最高难度 3]`\n"
                    "- **命令**：`<命令前缀>做饭 食材 <原料...> [--严格] [--数量 8]`\n"
                    "- **命令**：`<命令前缀>做饭 相关 <菜谱ID或路径> [--数量 5]`"
                ),
                "trigger_condition": "群聊与私聊用户；HowToCook API 可访问",
                "brief_des": "随机决定今天吃什么、自动搭配荤素汤，或按家中现有原料推荐菜谱。",
                "detail_des": (
                    "随机推荐支持固定种子、分类和难度；配餐可调整荤菜、素菜、汤的数量及"
                    "最高难度；食材找菜展示覆盖率、已有数量和缺少原料，并支持严格齐全模式。"
                    "所有候选共用序号选择，一个候选会直接打开完整详情。\n\n## 示例\n\n"
                    "- `<命令前缀>做饭 随机 3 --难度 2`\n"
                    "- `<命令前缀>做饭 配餐 --最高难度 3`\n"
                    "- `<命令前缀>做饭 食材 鸡蛋 西红柿 --严格`"
                ),
                "pmn_hidden": False,
                "pmn_triggers": [
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 随机 [数量]"},
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 配餐"},
                    {
                        "type": "command",
                        "label": "命令",
                        "value": "<命令前缀>做饭 食材 <原料...>",
                    },
                ],
                "pmn_group": _MENU_GROUP,
            },
            {
                "func": "菜谱搜索与筛选",
                "trigger_method": (
                    "- **命令**：`<命令前缀>做饭 搜索 <菜名|拼音|原料> [筛选]`\n"
                    "- **命令**：`<命令前缀>做饭 <关键词>`\n"
                    "- **命令**：`<命令前缀>做饭 全局搜索 <关键词>`\n"
                    "- **命令**：`<命令前缀>做饭 分类`"
                ),
                "trigger_condition": "群聊与私聊用户；HowToCook API 可访问",
                "brief_des": "按标题、拼音、原料和正文模糊搜索，并支持分类、难度、排序与分页。",
                "detail_des": (
                    "搜索支持中文标题、拼音全拼、拼音首字母、原料和正文；全局搜索会"
                    "同时检索菜谱与厨房技巧。"
                    "可追加 `--分类`、`--难度`、`--最高难度`、`--原料`、"
                    "`--排序`、`--页` 和 `--每页`。只有一个结果时直接展示完整详情；"
                    "多个结果时发送卡片中的序号即可继续，无需复制菜谱 ID。\n\n## 示例\n\n"
                    "- `<命令前缀>做饭 hsr`\n"
                    "- `<命令前缀>做饭 搜索 土豆 --原料 牛肉 --最高难度 3`\n"
                    "- 搜索卡片出现后回复 `1`、`2` 等序号"
                ),
                "pmn_hidden": False,
                "pmn_triggers": [
                    {
                        "type": "command",
                        "label": "命令",
                        "value": "<命令前缀>做饭 搜索 <关键词> [筛选]",
                    },
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 <关键词>"},
                    {
                        "type": "command",
                        "label": "命令",
                        "value": "<命令前缀>做饭 全局搜索 <关键词>",
                    },
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 分类"},
                ],
                "pmn_group": _MENU_GROUP,
            },
            {
                "func": "完整菜谱与进阶子资源",
                "trigger_method": (
                    "- **命令**：`<命令前缀>做饭 详情 <ID或路径>`\n"
                    "- **命令**：`<命令前缀>做饭 原料|工具|步骤|段落|备注|图片 <ID>`\n"
                    "- **命令**：`<命令前缀>做饭 元信息|Markdown|HTML|原文 <ID>`"
                ),
                "trigger_condition": "一般从搜索列表回复序号；进阶命令可使用稳定 ID 或仓库相对路径",
                "brief_des": "回复搜索序号查看完整菜谱，或按 ID 直达每一类结构化数据。",
                "detail_des": (
                    "详情包含分类、难度、卡路里、用时、烹饪方式、作者、完整原料、"
                    "工具、步骤、备注、正文与成品图。日常使用无需复制 ID；"
                    "所有 recipes 子接口仍保留直接命令入口。"
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
                "func": "统计、内容版本与输出模式",
                "trigger_method": (
                    "- **命令**：`<命令前缀>做饭 统计`\n"
                    "- **命令**：`<命令前缀>做饭 内容版本|内容检查`\n"
                    "- **参数**：`--模式 合并|单条|组合|渲染`\n"
                    "- **参数**：`--主题 自动|白天|夜间`\n"
                    "- **命令**：`<命令前缀>做饭 接口 <路径> [key=value ...]`\n"
                    "- **命令**：`<命令前缀>做饭 健康`"
                ),
                "trigger_condition": (
                    "通用入口仅允许 HowToCook 的只读 GET 路由；内容检查只读，聊天命令不开放更新"
                ),
                "brief_des": "查看全库统计与内容版本，切换输出主题，或调用受控的只读 API。",
                "detail_des": (
                    "统计卡片展示分类、难度、烹饪方式和高频原料；内容版本与检查只读取状态，"
                    "不会执行内容更新。全局支持合并消息、单消息、组合消息与 HTML 长图。"
                    "自动主题时按配置时区和时间段切换昼夜样式；默认 23:00–08:00 "
                    "为夜间。通用入口覆盖 API 已知 GET 路由，但明确拒绝内容更新 POST。"
                ),
                "pmn_hidden": False,
                "pmn_triggers": [
                    {
                        "type": "command",
                        "label": "命令",
                        "value": "<命令前缀>做饭 统计",
                    },
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 内容版本"},
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
