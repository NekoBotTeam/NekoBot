"""运行时管理模块

提供平台实例的动态管理能力，支持动态添加/移除、配置热更新和生命周期管理。
"""

import asyncio
from typing import Dict, Any, Optional, Callable
from loguru import logger
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..platform.base import BasePlatform, PlatformStatus
from ..platform.manager import PlatformManager
from ..platform.register import get_platform_adapter


class LifecycleEvent(Enum):
    """生命周期事件类型"""

    STARTING = "starting"
    STARTED = "started"
    STOPPING = "stopping"
    STOPPED = "stopped"
    RESTARTING = "restarting"
    ERROR = "error"
    CONFIG_UPDATED = "config_updated"


@dataclass
class LifecycleEventInfo:
    """生命周期事件信息"""

    event_type: LifecycleEvent
    platform_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    message: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


class RuntimeManager:
    """运行时管理器

    提供平台实例的动态管理能力：
    - 动态添加/移除单个平台实例（无需重启整个系统）
    - 配置热更新能力（修改配置后立即生效）
    - 平台实例的生命周期管理（启动、停止、重启）
    """

    def __init__(self, platform_manager: PlatformManager):
        self.platform_manager = platform_manager
        self._lifecycle_handlers: Dict[LifecycleEvent, list[Callable]] = {
            event: [] for event in LifecycleEvent
        }
        self._event_history: list[LifecycleEventInfo] = []
        self._max_history_size = 100

    def register_lifecycle_handler(
        self, event_type: LifecycleEvent, handler: Callable[[LifecycleEventInfo], None]
    ):
        """注册生命周期事件处理器

        Args:
            event_type: 事件类型
            handler: 处理函数
        """
        self._lifecycle_handlers[event_type].append(handler)
        logger.info(f"已注册生命周期处理器: {event_type.value}")

    def _emit_event(self, event_info: LifecycleEventInfo):
        """触发生命周期事件

        Args:
            event_info: 事件信息
        """
        handlers = self._lifecycle_handlers.get(event_info.event_type, [])
        for handler in handlers:
            try:
                handler(event_info)
            except Exception as e:
                logger.error(f"生命周期事件处理器执行失败: {e}")

        # 记录事件历史
        self._event_history.append(event_info)
        if len(self._event_history) > self._max_history_size:
            self._event_history.pop(0)

    def get_event_history(self) -> list[Dict[str, Any]]:
        """获取事件历史

        Returns:
            事件历史列表
        """
        return [
            {
                "event_type": e.event_type.value,
                "platform_id": e.platform_id,
                "timestamp": e.timestamp.isoformat(),
                "message": e.message,
                "extra": e.extra,
            }
            for e in self._event_history
        ]

    async def add_platform(
        self, platform_id: str, platform_config: Dict[str, Any], auto_start: bool = True
    ) -> bool:
        """动态添加平台实例

        Args:
            platform_id: 平台ID
            platform_config: 平台配置
            auto_start: 是否自动启动

        Returns:
            是否添加成功
        """
        if platform_id in self.platform_manager.platforms:
            logger.error(f"平台 {platform_id} 已存在，无法添加")
            return False

        if not platform_config.get("enable", False):
            logger.info(f"平台 {platform_id} 未启用，跳过添加")
            return False

        platform_type = platform_config.get("type", platform_id)
        adapter_cls = get_platform_adapter(platform_type)

        if not adapter_cls:
            logger.error(f"未找到平台适配器: {platform_type}")
            return False

        try:
            self._emit_event(
                LifecycleEventInfo(
                    event_type=LifecycleEvent.STARTING,
                    platform_id=platform_id,
                    message=f"正在添加平台 {platform_id} ({platform_type})",
                )
            )

            platform = adapter_cls(
                platform_config=platform_config,
                platform_settings=self.platform_manager.platform_settings,
                event_queue=self.platform_manager.event_queue,
            )
            self.platform_manager.platforms[platform_id] = platform

            self._emit_event(
                LifecycleEventInfo(
                    event_type=LifecycleEvent.STARTED,
                    platform_id=platform_id,
                    message=f"平台 {platform_id} 已添加",
                    extra={"auto_start": auto_start},
                )
            )

            if auto_start:
                await self.start_platform(platform_id)

            return True
        except Exception as e:
            logger.error(f"添加平台 {platform_id} 失败: {e}")
            self._emit_event(
                LifecycleEventInfo(
                    event_type=LifecycleEvent.ERROR,
                    platform_id=platform_id,
                    message=f"添加平台失败: {str(e)}",
                )
            )
            return False

    async def remove_platform(self, platform_id: str, graceful: bool = True) -> bool:
        """移除平台实例

        Args:
            platform_id: 平台ID
            graceful: 是否优雅关闭

        Returns:
            是否移除成功
        """
        if platform_id not in self.platform_manager.platforms:
            logger.error(f"平台 {platform_id} 不存在")
            return False

        try:
            self._emit_event(
                LifecycleEventInfo(
                    event_type=LifecycleEvent.STOPPING,
                    platform_id=platform_id,
                    message=f"正在移除平台 {platform_id}",
                )
            )

            if graceful:
                await self.stop_platform(platform_id)

            del self.platform_manager.platforms[platform_id]

            self._emit_event(
                LifecycleEventInfo(
                    event_type=LifecycleEvent.STOPPED,
                    platform_id=platform_id,
                    message=f"平台 {platform_id} 已移除",
                )
            )

            logger.info(f"平台 {platform_id} 已移除")
            return True
        except Exception as e:
            logger.error(f"移除平台 {platform_id} 失败: {e}")
            self._emit_event(
                LifecycleEventInfo(
                    event_type=LifecycleEvent.ERROR,
                    platform_id=platform_id,
                    message=f"移除平台失败: {str(e)}",
                )
            )
            return False

    async def start_platform(self, platform_id: str) -> bool:
        """启动平台实例

        Args:
            platform_id: 平台ID

        Returns:
            是否启动成功
        """
        platform = self.platform_manager.platforms.get(platform_id)
        if not platform:
            logger.error(f"平台 {platform_id} 不存在")
            return False

        if platform.status == PlatformStatus.RUNNING:
            logger.warning(f"平台 {platform_id} 已在运行中")
            return True

        try:
            self._emit_event(
                LifecycleEventInfo(
                    event_type=LifecycleEvent.STARTING,
                    platform_id=platform_id,
                    message=f"正在启动平台 {platform_id}",
                )
            )

            await platform.start()
            platform.status = PlatformStatus.RUNNING

            self._emit_event(
                LifecycleEventInfo(
                    event_type=LifecycleEvent.STARTED,
                    platform_id=platform_id,
                    message=f"平台 {platform_id} 已启动",
                )
            )

            logger.info(f"平台 {platform_id} 已启动")
            return True
        except Exception as e:
            logger.error(f"启动平台 {platform_id} 失败: {e}")
            platform.status = PlatformStatus.ERROR
            platform.record_error(str(e))
            self._emit_event(
                LifecycleEventInfo(
                    event_type=LifecycleEvent.ERROR,
                    platform_id=platform_id,
                    message=f"启动平台失败: {str(e)}",
                )
            )
            return False

    async def stop_platform(self, platform_id: str, graceful: bool = True) -> bool:
        """停止平台实例

        Args:
            platform_id: 平台ID
            graceful: 是否优雅关闭

        Returns:
            是否停止成功
        """
        platform = self.platform_manager.platforms.get(platform_id)
        if not platform:
            logger.error(f"平台 {platform_id} 不存在")
            return False

        if platform.status == PlatformStatus.STOPPED:
            logger.warning(f"平台 {platform_id} 已停止")
            return True

        try:
            self._emit_event(
                LifecycleEventInfo(
                    event_type=LifecycleEvent.STOPPING,
                    platform_id=platform_id,
                    message=f"正在停止平台 {platform_id}",
                )
            )

            if graceful and hasattr(platform, "stop"):
                await platform.stop()

            platform.status = PlatformStatus.STOPPED

            self._emit_event(
                LifecycleEventInfo(
                    event_type=LifecycleEvent.STOPPED,
                    platform_id=platform_id,
                    message=f"平台 {platform_id} 已停止",
                )
            )

            logger.info(f"平台 {platform_id} 已停止")
            return True
        except Exception as e:
            logger.error(f"停止平台 {platform_id} 失败: {e}")
            platform.status = PlatformStatus.ERROR
            platform.record_error(str(e))
            self._emit_event(
                LifecycleEventInfo(
                    event_type=LifecycleEvent.ERROR,
                    platform_id=platform_id,
                    message=f"停止平台失败: {str(e)}",
                )
            )
            return False

    async def restart_platform(self, platform_id: str) -> bool:
        """重启平台实例

        Args:
            platform_id: 平台ID

        Returns:
            是否重启成功
        """
        self._emit_event(
            LifecycleEventInfo(
                event_type=LifecycleEvent.RESTARTING,
                platform_id=platform_id,
                message=f"正在重启平台 {platform_id}",
            )
        )

        stop_success = await self.stop_platform(platform_id)
        if not stop_success:
            return False

        await asyncio.sleep(1)
        return await self.start_platform(platform_id)

    async def update_platform_config(
        self,
        platform_id: str,
        config_updates: Dict[str, Any],
        apply_immediately: bool = True,
    ) -> bool:
        """更新平台配置（热更新）

        Args:
            platform_id: 平台ID
            config_updates: 配置更新项
            apply_immediately: 是否立即应用配置

        Returns:
            是否更新成功
        """
        platform = self.platform_manager.platforms.get(platform_id)
        if not platform:
            logger.error(f"平台 {platform_id} 不存在")
            return False

        try:
            old_config = platform.config.copy()
            platform.config.update(config_updates)

            self._emit_event(
                LifecycleEventInfo(
                    event_type=LifecycleEvent.CONFIG_UPDATED,
                    platform_id=platform_id,
                    message=f"平台 {platform_id} 配置已更新",
                    extra={
                        "old_config": old_config,
                        "new_config": platform.config,
                        "apply_immediately": apply_immediately,
                    },
                )
            )

            if apply_immediately:
                if platform.status == PlatformStatus.RUNNING:
                    restart_success = await self.restart_platform(platform_id)
                    if not restart_success:
                        logger.warning(f"配置更新后重启失败，已回滚配置")
                        platform.config = old_config
                        return False

            logger.info(f"平台 {platform_id} 配置已更新并应用")
            return True
        except Exception as e:
            logger.error(f"更新平台 {platform_id} 配置失败: {e}")
            return False

    async def batch_update_platform_configs(
        self, updates: Dict[str, Dict[str, Any]], apply_immediately: bool = True
    ) -> Dict[str, bool]:
        """批量更新平台配置

        Args:
            updates: 平台ID到配置更新项的映射
            apply_immediately: 是否立即应用配置

        Returns:
            平台ID到更新结果的映射
        """
        results = {}
        for platform_id, config_updates in updates.items():
            results[platform_id] = await self.update_platform_config(
                platform_id, config_updates, apply_immediately
            )
        return results

    def get_platform_lifecycle_status(
        self, platform_id: str
    ) -> Optional[Dict[str, Any]]:
        """获取平台生命周期状态

        Args:
            platform_id: 平台ID

        Returns:
            生命周期状态信息
        """
        platform = self.platform_manager.platforms.get(platform_id)
        if not platform:
            return None

        events = [e for e in self._event_history if e.platform_id == platform_id]
        return {
            "platform_id": platform_id,
            "status": platform.status.value,
            "started_at": platform._started_at.isoformat()
            if platform._started_at
            else None,
            "error_count": len(platform.errors),
            "recent_events": [
                {
                    "event_type": e.event_type.value,
                    "timestamp": e.timestamp.isoformat(),
                    "message": e.message,
                }
                for e in events[-10:]
            ],
        }

    def get_all_lifecycle_status(self) -> Dict[str, Any]:
        """获取所有平台的生命周期状态

        Returns:
            所有平台的生命周期状态
        """
        statuses = {}
        for platform_id in self.platform_manager.platforms:
            status = self.get_platform_lifecycle_status(platform_id)
            if status:
                statuses[platform_id] = status
        return statuses
