"""Lightweight internationalization framework for Kunming Agent.

Provides a simple _T() translation function that reads the language
setting from config.yaml (language key). No external dependencies.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_CURRENT_LANG: str = "zh"

_ZH: dict[str, str] = {
    # Slash command descriptions (commands.py)
    "cmd.new": "开始新会话（全新会话ID和历史记录）",
    "cmd.clear": "清屏并开始新会话",
    "cmd.history": "显示对话历史",
    "cmd.save": "保存当前对话",
    "cmd.retry": "重试上一条消息（重新发送给Agent）",
    "cmd.undo": "撤销最后一轮用户/助手对话",
    "cmd.title": "为当前会话设置标题",
    "cmd.branch": "分支当前会话（探索不同路径）",
    "cmd.compress": "手动压缩对话上下文",
    "cmd.rollback": "列出或恢复文件系统检查点",
    "cmd.stop": "终止所有后台运行进程",
    "cmd.approve": "批准待审批的危险命令",
    "cmd.deny": "拒绝待审批的危险命令",
    "cmd.background": "在后台运行提示词",
    "cmd.btw": "使用会话上下文的临时提问（无工具，不持久化）",
    "cmd.queue": "为下一轮排队提示词（不打断当前操作）",
    "cmd.status": "显示会话信息",
    "cmd.profile": "显示当前配置文件名和主目录",
    "cmd.sethome": "将此聊天设为主频道",
    "cmd.resume": "恢复之前命名的会话",
    "cmd.config": "显示当前配置",
    "cmd.model": "切换当前会话的模型",
    "cmd.provider": "显示可用提供商和当前提供商",
    "cmd.prompt": "查看/设置自定义系统提示词",
    "cmd.personality": "设置预设人格",
    "cmd.statusbar": "切换上下文/模型状态栏",
    "cmd.verbose": "循环切换工具进度显示：关 -> 新 -> 全 -> 详细",
    "cmd.yolo": "切换YOLO模式（跳过所有危险命令审批）",
    "cmd.reasoning": "管理推理力度和显示",
    "cmd.skin": "显示或更换显示皮肤/主题",
    "cmd.voice": "切换语音模式",
    "cmd.tools": "管理工具：/tools [list|disable|enable] [名称...]",
    "cmd.toolsets": "列出可用工具集",
    "cmd.skills": "搜索、安装、查看或管理技能",
    "cmd.cron": "管理定时任务",
    "cmd.distill": "运行记忆蒸馏（将短期信号整合为长期记忆）",
    "cmd.reload-mcp": "从配置重新加载MCP服务器",
    "cmd.browser": "通过CDP连接浏览器工具到你的Chrome",
    "cmd.plugins": "列出已安装插件及其状态",
    "cmd.commands": "浏览所有命令和技能（分页）",
    "cmd.help": "显示可用命令",
    "cmd.usage": "显示当前会话的Token使用量",
    "cmd.insights": "显示使用洞察和分析",
    "cmd.platforms": "显示网关/消息平台状态",
    "cmd.paste": "检查剪贴板中的图片并附加",
    "cmd.update": "更新Kunming Agent到最新版本",
    "cmd.quit": "退出CLI",

    # Command categories
    "cat.Session": "会话",
    "cat.Configuration": "配置",
    "cat.Tools & Skills": "工具与技能",
    "cat.Info": "信息",
    "cat.Exit": "退出",

    # Banner
    "banner.available_tools": "可用工具",
    "banner.session": "会话",
    "banner.commits_behind": "个提交落后",
    "banner.to_update": "以更新",
    "banner.more_toolsets": "（还有 {remaining} 个工具集...）",
    "banner.mcp_servers": "MCP 服务器",
    "banner.tools_count": "{count} 个工具",
    "banner.skills_count": "{count} 个技能",
    "banner.mcp_count": "{count} 个MCP服务器",
    "banner.help_command": "/help 查看命令",
    "banner.failed": "失败",

    # CLI common messages
    "cli.session_not_found": "未找到会话：",
    "cli.session_hint": "使用之前CLI运行的会话ID",
    "cli.no_active_session": "没有活动的Agent会话。",
    "cli.checkpoints_not_enabled": "检查点未启用。",
    "cli.enable_with": "启用方式：km --checkpoints",
    "cli.invalid_checkpoint": "无效的检查点编号。",
    "cli.no_background": "没有运行中的后台进程。",
    "cli.no_clipboard_image": "剪贴板中未找到图片",
    "cli.tools_disabled": "部分工具已禁用（缺少API密钥）：",
    "cli.run_setup": "运行 'km setup' 进行配置",
    "cli.available_commands": "(^_^) 可用命令",
    "cli.tip_chat": "提示：直接输入消息即可与Kunming对话！",
    "cli.tip_multiline": "多行输入：Alt+Enter 换行",
    "cli.no_tools": "(;_;) 没有可用工具",
    "cli.available_tools": "(^_^)/ 可用工具",
    "cli.usage_tools": "(._.) 用法：/tools",
    "cli.session_reset": "会话已重置。新的工具配置已生效。",
    "cli.available_toolsets": "(^_^)b 可用工具集",
    "cli.tip_all_toolsets": "提示：使用 'all' 或 '*' 启用所有工具集",
    "cli.init_failed": "Agent初始化失败：",
    "cli.worktree_requires_git": "--worktree 需要在git仓库内使用。",
    "cli.worktree_failed": "创建worktree失败：",
    "cli.worktree_created": "Worktree已创建：",
    "cli.thinking": "[思考中]",
}

_EN: dict[str, str] = {}

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh": _ZH,
    "en": _EN,
}


def set_language(lang: str) -> None:
    """Set the current UI language."""
    global _CURRENT_LANG
    _CURRENT_LANG = lang or "zh"
    logger.debug("Language set to: %s", _CURRENT_LANG)


def get_language() -> str:
    """Return the current UI language code."""
    return _CURRENT_LANG


def _T(key: str, **kwargs) -> str:
    """Translate a key to the current language.

    Falls back to the key itself when no translation is found.
    Supports ``str.format()`` keyword arguments for interpolation.
    """
    translations = _TRANSLATIONS.get(_CURRENT_LANG, {})
    text = translations.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
