"""命令管理模块

提供命令列表、切换、重命名等功能
"""

import json
import os
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from loguru import logger


class ConflictResolutionStrategy(str, Enum):
    """冲突解决策略"""

    KEEP_FIRST = "keep_first"
    KEEP_SECOND = "keep_second"
    ALIAS_FIRST = "alias_first"
    ALIAS_SECOND = "alias_second"


@dataclass
class CommandConflict:
    """命令冲突记录"""

    conflict_key: str
    resolution_strategy: ConflictResolutionStrategy
    keep_handler_full_name: str
    alias_handler_full_name: str
    alias_name: str
    resolved_at: float


@dataclass
class CommandDescriptor:
    """命令描述符"""

    handler_full_name: str = ""
    handler_name: str = ""
    plugin_name: str = ""
    plugin_display_name: str | None = None
    module_path: str = ""
    description: str = ""
    command_type: str = "command"  # "command" | "group" | "sub_command"
    original_command: str | None = None
    effective_command: str | None = None
    aliases: List[str] = field(default_factory=list)
    permission: str = "everyone"
    enabled: bool = True
    is_group: bool = False
    is_sub_command: bool = False
    reserved: bool = False
    sub_commands: List["CommandDescriptor"] = field(default_factory=list)


# 全局命令注册表
_command_registry: Dict[str, CommandDescriptor] = {}

# 已解决的冲突记录
_resolved_conflicts: List[CommandConflict] = []


def register_command(
    handler_full_name: str,
    handler_name: str,
    plugin_name: str,
    module_path: str,
    description: str = "",
    aliases: List[str] | None = None,
    permission: str = "everyone",
) -> CommandDescriptor:
    """注册命令

    Args:
        handler_full_name: 处理函数完整名称
        handler_name: 处理函数名称
        plugin_name: 插件名称
        module_path: 模块路径
        description: 描述
        aliases: 别名列表
        permission: 权限

    Returns:
        命令描述符
    """
    descriptor = CommandDescriptor(
        handler_full_name=handler_full_name,
        handler_name=handler_name,
        plugin_name=plugin_name,
        module_path=module_path,
        description=description,
        command_type="command",
        original_command=handler_name,
        effective_command=handler_name,
        aliases=aliases or [],
        permission=permission,
        enabled=True,
    )
    _command_registry[handler_full_name] = descriptor
    logger.info(f"注册命令: {handler_full_name}")
    return descriptor


def unregister_plugin_commands(plugin_name: str) -> int:
    """注销插件的所有命令

    Args:
        plugin_name: 插件名称

    Returns:
        注销的命令数量
    """
    count = 0
    to_remove = []
    for handler_full_name, descriptor in _command_registry.items():
        if descriptor.plugin_name == plugin_name:
            to_remove.append(handler_full_name)
    for handler_full_name in to_remove:
        del _command_registry[handler_full_name]
        count += 1
    logger.info(f"已注销插件 {plugin_name} 的 {count} 个命令")
    return count


def get_command(handler_full_name: str) -> Optional[CommandDescriptor]:
    """获取命令描述符

    Args:
        handler_full_name: 处理函数完整名称

    Returns:
        命令描述符
    """
    return _command_registry.get(handler_full_name)


def list_commands() -> List[Dict[str, Any]]:
    """列出所有命令

    Returns:
        命令列表
    """
    result = []
    for desc in _command_registry.values():
        result.append(
            {
                "handler_full_name": desc.handler_full_name,
                "handler_name": desc.handler_name,
                "plugin": desc.plugin_name,
                "plugin_display_name": desc.plugin_display_name,
                "module_path": desc.module_path,
                "description": desc.description,
                "type": desc.command_type,
                "original_command": desc.original_command,
                "effective_command": desc.effective_command,
                "aliases": desc.aliases,
                "permission": desc.permission,
                "enabled": desc.enabled,
                "is_group": desc.is_group,
                "reserved": desc.reserved,
                "sub_commands": [],
            }
        )
    return result


def toggle_command(
    handler_full_name: str, enabled: bool
) -> Optional[CommandDescriptor]:
    """切换命令启用状态

    Args:
        handler_full_name: 处理函数完整名称
        enabled: 是否启用

    Returns:
        命令描述符
    """
    descriptor = _command_registry.get(handler_full_name)
    if not descriptor:
        raise ValueError("指定的处理函数不存在或不是命令。")

    descriptor.enabled = enabled
    return descriptor


def rename_command(
    handler_full_name: str,
    new_name: str,
    aliases: List[str] | None = None,
) -> Optional[CommandDescriptor]:
    """重命名命令

    Args:
        handler_full_name: 处理函数完整名称
        new_name: 新名称
        aliases: 别名列表

    Returns:
        命令描述符
    """
    descriptor = _command_registry.get(handler_full_name)
    if not descriptor:
        raise ValueError("指定的处理函数不存在或不是命令。")

    new_name = new_name.strip()
    if not new_name:
        raise ValueError("指令名不能为空。")

    # 检查命令名是否被占用
    for desc in _command_registry.values():
        if desc.handler_full_name != handler_full_name and (
            desc.effective_command == new_name or new_name in desc.aliases
        ):
            raise ValueError(f"指令名 '{new_name}' 已被其他指令占用。")

    # 检查别名是否被占用
    if aliases:
        for alias in aliases:
            alias = alias.strip()
            if not alias:
                continue
            for desc in _command_registry.values():
                if desc.handler_full_name != handler_full_name and (
                    desc.effective_command == alias or alias in desc.aliases
                ):
                    raise ValueError(f"别名 '{alias}' 已被其他指令占用。")

    descriptor.effective_command = new_name
    descriptor.aliases = aliases or []
    return descriptor


def list_command_conflicts() -> List[Dict[str, Any]]:
    """列出所有冲突的命令

    Returns:
        冲突命令列表
    """
    conflicts: Dict[str, List[CommandDescriptor]] = {}
    for desc in _command_registry.values():
        if desc.effective_command and desc.enabled:
            if desc.effective_command not in conflicts:
                conflicts[desc.effective_command] = []
            conflicts[desc.effective_command].append(desc)

    details = [
        {
            "conflict_key": key,
            "handlers": [
                {
                    "handler_full_name": item.handler_full_name,
                    "plugin": item.plugin_name,
                    "current_name": item.effective_command,
                }
                for item in group
            ],
        }
        for key, group in conflicts.items()
        if len(group) > 1
    ]
    return details


def get_conflicting_handlers(conflict_key: str) -> List[CommandDescriptor]:
    """查找冲突的所有处理器

    Args:
        conflict_key: 冲突的命令名

    Returns:
        冲突的处理器列表
    """
    handlers = []
    for desc in _command_registry.values():
        if desc.effective_command == conflict_key and desc.enabled:
            handlers.append(desc)
    return handlers


async def resolve_command_conflict(
    conflict_key: str,
    resolution_strategy: ConflictResolutionStrategy,
    keep_handler_full_name: str,
) -> Dict[str, Any]:
    """解决命令冲突

    Args:
        conflict_key: 冲突的命令名
        resolution_strategy: 解决策略
        keep_handler_full_name: 保留命令名的处理器完整名称

    Returns:
        解决结果
    """
    handlers = get_conflicting_handlers(conflict_key)

    if len(handlers) != 2:
        raise ValueError(
            f"命令 '{conflict_key}' 的冲突处理器数量不正确，应为2个，当前为{len(handlers)}个"
        )

    handler1, handler2 = handlers[0], handlers[1]

    keep_handler = None
    alias_handler = None

    if handler1.handler_full_name == keep_handler_full_name:
        keep_handler = handler1
        alias_handler = handler2
    elif handler2.handler_full_name == keep_handler_full_name:
        keep_handler = handler2
        alias_handler = handler1
    else:
        raise ValueError(f"找不到指定的处理器: {keep_handler_full_name}")

    if resolution_strategy == ConflictResolutionStrategy.KEEP_FIRST:
        if keep_handler.handler_full_name != handler1.handler_full_name:
            raise ValueError("KEEP_FIRST 策略要求第一个处理器为保留命令")
        alias_name = f"{conflict_key}_alias"
        alias_handler.effective_command = alias_name
        if alias_name not in alias_handler.aliases:
            alias_handler.aliases.append(alias_name)

    elif resolution_strategy == ConflictResolutionStrategy.KEEP_SECOND:
        if keep_handler.handler_full_name != handler2.handler_full_name:
            raise ValueError("KEEP_SECOND 策略要求第二个处理器为保留命令")
        alias_name = f"{conflict_key}_alias"
        alias_handler.effective_command = alias_name
        if alias_name not in alias_handler.aliases:
            alias_handler.aliases.append(alias_name)

    elif resolution_strategy == ConflictResolutionStrategy.ALIAS_FIRST:
        alias_name1 = f"{conflict_key}_alias1"
        alias_name2 = f"{conflict_key}_alias2"
        handler1.effective_command = alias_name1
        if alias_name1 not in handler1.aliases:
            handler1.aliases.append(alias_name1)
        handler2.effective_command = alias_name2
        if alias_name2 not in handler2.aliases:
            handler2.aliases.append(alias_name2)

    elif resolution_strategy == ConflictResolutionStrategy.ALIAS_SECOND:
        alias_name1 = f"{conflict_key}_alias1"
        alias_name2 = f"{conflict_key}_alias2"
        handler1.effective_command = alias_name1
        if alias_name1 not in handler1.aliases:
            handler1.aliases.append(alias_name1)
        handler2.effective_command = alias_name2
        if alias_name2 not in handler2.aliases:
            handler2.aliases.append(alias_name2)

    else:
        raise ValueError(f"未知的解决策略: {resolution_strategy}")

    import time

    if alias_handler.effective_command is None:
        alias_handler.effective_command = f"{conflict_key}_alias"

    conflict = CommandConflict(
        conflict_key=conflict_key,
        resolution_strategy=resolution_strategy,
        keep_handler_full_name=keep_handler.handler_full_name,
        alias_handler_full_name=alias_handler.handler_full_name,
        alias_name=alias_handler.effective_command,
        resolved_at=time.time(),
    )

    _resolved_conflicts.append(conflict)
    save_resolved_conflicts()

    if resolution_strategy in [
        ConflictResolutionStrategy.KEEP_FIRST,
        ConflictResolutionStrategy.KEEP_SECOND,
    ]:
        logger.info(
            f"已解决命令冲突 '{conflict_key}': {keep_handler.plugin_name} 保留 '{conflict_key}', {alias_handler.plugin_name} 使用别名 '{alias_handler.effective_command}'"
        )
    else:
        logger.info(
            f"已解决命令冲突 '{conflict_key}': {handler1.plugin_name} 使用 '{handler1.effective_command}', {handler2.plugin_name} 使用 '{handler2.effective_command}'"
        )

    return {
        "conflict_key": conflict_key,
        "resolution_strategy": resolution_strategy.value,
        "keep_handler": keep_handler.handler_full_name,
        "alias_handler": alias_handler.handler_full_name,
        "alias_name": alias_handler.effective_command,
    }


async def clear_all_conflicts() -> int:
    """清除所有已解决的冲突记录

    Returns:
        清除的记录数量
    """
    count = len(_resolved_conflicts)
    _resolved_conflicts.clear()
    logger.info(f"已清除 {count} 个已解决的冲突记录")
    return count


def get_conflicts_file_path() -> Path:
    """获取冲突记录文件路径

    Returns:
        文件路径
    """
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "command_conflicts.json"


def save_resolved_conflicts() -> bool:
    """保存已解决的冲突记录

    Returns:
        是否成功
    """
    try:
        file_path = get_conflicts_file_path()
        conflicts_data = []
        for conflict in _resolved_conflicts:
            conflict_dict = {
                "conflict_key": conflict.conflict_key,
                "resolution_strategy": conflict.resolution_strategy.value,
                "keep_handler_full_name": conflict.keep_handler_full_name,
                "alias_handler_full_name": conflict.alias_handler_full_name,
                "alias_name": conflict.alias_name,
                "resolved_at": conflict.resolved_at,
            }
            conflicts_data.append(conflict_dict)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(conflicts_data, f, ensure_ascii=False, indent=2)

        logger.info(f"已保存 {len(conflicts_data)} 个已解决的冲突记录")
        return True
    except Exception as e:
        logger.error(f"保存冲突记录失败: {e}")
        return False


def load_resolved_conflicts() -> int:
    """加载已解决的冲突记录

    Returns:
        加载的记录数量
    """
    global _resolved_conflicts

    try:
        file_path = get_conflicts_file_path()
        if not file_path.exists():
            return 0

        with open(file_path, "r", encoding="utf-8") as f:
            conflicts_data = json.load(f)

        _resolved_conflicts = []
        for conflict_dict in conflicts_data:
            conflict = CommandConflict(
                conflict_key=conflict_dict["conflict_key"],
                resolution_strategy=ConflictResolutionStrategy(
                    conflict_dict["resolution_strategy"]
                ),
                keep_handler_full_name=conflict_dict["keep_handler_full_name"],
                alias_handler_full_name=conflict_dict["alias_handler_full_name"],
                alias_name=conflict_dict["alias_name"],
                resolved_at=conflict_dict["resolved_at"],
            )
            _resolved_conflicts.append(conflict)

        logger.info(f"已加载 {len(_resolved_conflicts)} 个已解决的冲突记录")
        return len(_resolved_conflicts)
    except Exception as e:
        logger.error(f"加载冲突记录失败: {e}")
        return 0


def get_resolved_conflicts() -> List[Dict[str, Any]]:
    """获取已解决的冲突记录列表

    Returns:
        冲突记录列表
    """
    return [
        {
            "conflict_key": conflict.conflict_key,
            "resolution_strategy": conflict.resolution_strategy.value,
            "keep_handler_full_name": conflict.keep_handler_full_name,
            "alias_handler_full_name": conflict.alias_handler_full_name,
            "alias_name": conflict.alias_name,
            "resolved_at": conflict.resolved_at,
        }
        for conflict in _resolved_conflicts
    ]


def initialize_conflict_system() -> None:
    """初始化冲突系统，加载已保存的冲突记录"""
    load_resolved_conflicts()


initialize_conflict_system()
