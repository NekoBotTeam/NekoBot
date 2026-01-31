"""命令冲突管理 API

提供命令冲突检测、列出、解决等接口
"""

from typing import Dict, Any, List
from loguru import logger

from .route import Route, Response, RouteContext
from ..core.command_management import (
    _command_registry,
    CommandDescriptor,
    ConflictResolutionStrategy,
    CommandConflict,
)


class CommandConflictRoute(Route):
    """命令冲突路由"""

    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.routes = [
            ("/api/commands/conflicts", "GET", self.list_conflicts),
            ("/api/commands/conflicts/<conflict_key>", "GET", self.get_conflict),
            (
                "/api/commands/conflicts/<conflict_key>/resolve",
                "POST",
                self.resolve_conflict,
            ),
            ("/api/commands/conflicts", "DELETE", self.clear_resolved),
            ("/api/commands/conflicts/resolved", "GET", self.list_resolved),
        ]

    def _find_conflicting_handlers(self, conflict_key: str) -> List[CommandDescriptor]:
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

    async def list_conflicts(self) -> Dict[str, Any]:
        """列出所有命令冲突"""
        try:
            conflicts = []

            # 统计每个有效命令的使用次数
            command_count = {}
            for desc in _command_registry.values():
                if desc.effective_command and desc.enabled:
                    command_count[desc.effective_command] = (
                        command_count.get(desc.effective_command, 0) + 1
                    )

            # 找出冲突（使用次数 > 1 的命令）
            for command, count in command_count.items():
                if count > 1:
                    handlers = self._find_conflicting_handlers(command)

                    if len(handlers) > 1:
                        conflicts.append(
                            {
                                "conflict_key": command,
                                "handlers": [
                                    {
                                        "handler_full_name": h.handler_full_name,
                                        "handler_name": h.handler_name,
                                        "plugin_name": h.plugin_name,
                                        "plugin_display_name": h.plugin_display_name,
                                        "current_name": h.effective_command,
                                        "description": h.description,
                                        "original_command": h.original_command,
                                        "aliases": h.aliases,
                                        "reserved": h.reserved,
                                    }
                                    for h in handlers
                                ],
                                "handler_count": len(handlers),
                            }
                        )

            return Response().ok(data=conflicts).to_dict()
        except Exception as e:
            logger.error(f"列出命令冲突失败: {e}")
            return Response().error(f"列出命令冲突失败: {str(e)}").to_dict()

    async def get_conflict(self, conflict_key: str) -> Dict[str, Any]:
        """获取命令冲突详情"""
        try:
            handlers = self._find_conflicting_handlers(conflict_key)

            if not handlers:
                return Response().error(f"命令 '{conflict_key}' 不存在冲突").to_dict()

            return (
                Response()
                .ok(
                    data={
                        "conflict_key": conflict_key,
                        "handlers": [
                            {
                                "handler_full_name": h.handler_full_name,
                                "handler_name": h.handler_name,
                                "plugin_name": h.plugin_name,
                                "plugin_display_name": h.plugin_display_name,
                                "current_name": h.effective_command,
                                "description": h.description,
                                "original_command": h.original_command,
                                "aliases": h.aliases,
                                "reserved": h.reserved,
                            }
                            for h in handlers
                        ],
                        "available_strategies": [
                            {
                                "strategy": ConflictResolutionStrategy.KEEP_FIRST,
                                "name": "保留第一个命令，第二个命令使用别名",
                                "description": f"第一个插件保留 '{conflict_key}' 命令名，第二个插件使用别名",
                            },
                            {
                                "strategy": ConflictResolutionStrategy.KEEP_SECOND,
                                "name": "保留第二个命令，第一个命令使用别名",
                                "description": f"第二个插件保留 '{conflict_key}' 命令名，第一个插件使用别名",
                            },
                            {
                                "strategy": ConflictResolutionStrategy.ALIAS_FIRST,
                                "name": "两个命令都使用别名（第一个）",
                                "description": f"两个插件都使用别名，第一个插件添加 '{conflict_key}_alias1' 前缀",
                            },
                            {
                                "strategy": ConflictResolutionStrategy.ALIAS_SECOND,
                                "name": "两个命令都使用别名（第二个）",
                                "description": f"两个插件都使用别名，第二个插件添加 '{conflict_key}_alias2' 前缀",
                            },
                        ],
                    }
                )
                .to_dict()
            )
        except Exception as e:
            logger.error(f"获取冲突详情失败: {e}")
            return Response().error(f"获取冲突详情失败: {str(e)}").to_dict()

    async def resolve_conflict(self, conflict_key: str) -> Dict[str, Any]:
        """解决命令冲突"""
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("缺少请求数据").to_dict()

            resolution_strategy = data.get("resolution_strategy")
            keep_handler_full_name = data.get("keep_handler_full_name")

            if not resolution_strategy:
                return Response().error("缺少 resolution_strategy 参数").to_dict()

            if not keep_handler_full_name:
                return Response().error("缺少 keep_handler_full_name 参数").to_dict()

            # 验证策略
            if resolution_strategy not in [
                ConflictResolutionStrategy.KEEP_FIRST.value,
                ConflictResolutionStrategy.KEEP_SECOND.value,
                ConflictResolutionStrategy.ALIAS_FIRST.value,
                ConflictResolutionStrategy.ALIAS_SECOND.value,
            ]:
                return (
                    Response().error(f"无效的解决策略: {resolution_strategy}").to_dict()
                )

            from ..core.command_management import resolve_command_conflict

            # 解决冲突
            result = await resolve_command_conflict(
                conflict_key=conflict_key,
                resolution_strategy=resolution_strategy,
                keep_handler_full_name=keep_handler_full_name,
            )

            if not result:
                return Response().error("解决命令冲突失败").to_dict()

            return Response().ok(data=result).to_dict()
        except ValueError as e:
            logger.warning(f"解决命令冲突参数错误: {e}")
            return Response().error(str(e)).to_dict()
        except Exception as e:
            logger.error(f"解决命令冲突失败: {e}")
            return Response().error(f"解决命令冲突失败: {str(e)}").to_dict()

    async def clear_resolved(self) -> Dict[str, Any]:
        """清除已解决的冲突记录"""
        try:
            from ..core.command_management import clear_all_conflicts

            count = await clear_all_conflicts()

            return Response().ok(message=f"已清除 {count} 个已解决的冲突记录").to_dict()
        except Exception as e:
            logger.error(f"清除冲突记录失败: {e}")
            return Response().error(f"清除冲突记录失败: {str(e)}").to_dict()

    async def list_resolved(self) -> Dict[str, Any]:
        """列出已解决的冲突记录"""
        try:
            from ..core.command_management import get_resolved_conflicts

            conflicts = get_resolved_conflicts()

            return Response().ok(data=conflicts).to_dict()
        except Exception as e:
            logger.error(f"列出已解决的冲突记录失败: {e}")
            return Response().error(f"列出已解决的冲突记录失败: {str(e)}").to_dict()
