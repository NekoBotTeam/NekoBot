"""故障隔离模块

提供平台异常的隔离、捕获、自动恢复和降级运行模式。
"""

import asyncio
import traceback
from typing import Dict, Any, Optional, Callable, List
from loguru import logger
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class IsolationStrategy(Enum):
    """隔离策略"""

    CONTINUE = "continue"
    RESTART_PLATFORM = "restart_platform"
    DISABLE_PLATFORM = "disable_platform"
    DEGRADED_MODE = "degraded_mode"


class DegradationLevel(Enum):
    """降级级别"""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class FaultRecord:
    """故障记录"""

    platform_id: str
    error_type: str
    error_message: str
    traceback_str: str
    timestamp: datetime = field(default_factory=datetime.now)
    isolation_strategy: IsolationStrategy = IsolationStrategy.CONTINUE
    resolved: bool = False
    resolved_at: Optional[datetime] = None


@dataclass
class IsolationConfig:
    """隔离配置"""

    max_errors_threshold: int = 5
    error_window_seconds: int = 300
    auto_restart: bool = True
    max_restart_attempts: int = 3
    auto_disable: bool = True
    degraded_mode_enabled: bool = True
    recovery_check_interval: float = 30.0


class FaultIsolationManager:
    """故障隔离管理器

    提供以下功能：
    - 单个平台异常不应影响其他平台
    - 异常捕获和自动恢复策略
    - 降级运行模式（部分平台故障时继续运行）
    """

    def __init__(
        self,
        runtime_manager,
        config: IsolationConfig = None,
    ):
        self.runtime_manager = runtime_manager
        self.config = config or IsolationConfig()

        self._fault_records: Dict[str, List[FaultRecord]] = {}
        self._platform_errors: Dict[str, List[datetime]] = {}
        self._restart_attempts: Dict[str, int] = {}
        self._degradation_level = DegradationLevel.NONE
        self._disabled_platforms: set[str] = set()

        self._recovery_task: Optional[asyncio.Task] = None
        self._fault_handlers: Dict[str, Callable] = {}

    def register_fault_handler(
        self,
        platform_id: str,
        handler: Callable[[FaultRecord], None],
    ):
        """注册故障处理器

        Args:
            platform_id: 平台ID
            handler: 故障处理函数
        """
        self._fault_handlers[platform_id] = handler
        logger.info(f"已注册故障处理器: {platform_id}")

    async def handle_fault(
        self,
        platform_id: str,
        exception: Exception,
        context: Dict[str, Any] = None,
    ) -> IsolationStrategy:
        """处理平台故障

        Args:
            platform_id: 平台ID
            exception: 异常对象
            context: 上下文信息

        Returns:
            采取的隔离策略
        """
        timestamp = datetime.now()
        error_type = type(exception).__name__
        error_message = str(exception)
        traceback_str = traceback.format_exc()

        logger.error(f"平台 {platform_id} 发生异常: {error_type}: {error_message}")

        # 记录故障
        fault_record = FaultRecord(
            platform_id=platform_id,
            error_type=error_type,
            error_message=error_message,
            traceback_str=traceback_str,
            timestamp=timestamp,
        )

        if platform_id not in self._fault_records:
            self._fault_records[platform_id] = []
        self._fault_records[platform_id].append(fault_record)

        if platform_id not in self._platform_errors:
            self._platform_errors[platform_id] = []
        self._platform_errors[platform_id].append(timestamp)

        # 清理过期错误记录
        self._cleanup_old_errors(platform_id)

        # 计算错误频率
        error_count = len(self._platform_errors.get(platform_id, []))

        # 判断采取的隔离策略
        strategy = self._determine_strategy(platform_id, error_count)
        fault_record.isolation_strategy = strategy

        # 执行策略
        await self._execute_strategy(strategy, platform_id, error_count)

        # 调用故障处理器
        if platform_id in self._fault_handlers:
            try:
                self._fault_handlers[platform_id](fault_record)
            except Exception as e:
                logger.error(f"故障处理器执行失败: {e}")

        # 更新降级级别
        self._update_degradation_level()

        # 启动恢复检查
        if self._recovery_task is None or self._recovery_task.done():
            self._recovery_task = asyncio.create_task(self._recovery_loop())

        return strategy

    def _cleanup_old_errors(self, platform_id: str):
        """清理过期的错误记录"""
        if platform_id not in self._platform_errors:
            return

        now = datetime.now()
        cutoff = now - timedelta(seconds=self.config.error_window_seconds)

        self._platform_errors[platform_id] = [
            t for t in self._platform_errors[platform_id] if t > cutoff
        ]

    def _determine_strategy(
        self, platform_id: str, error_count: int
    ) -> IsolationStrategy:
        """确定隔离策略"""
        if error_count >= self.config.max_errors_threshold:
            if self.config.auto_disable:
                return IsolationStrategy.DISABLE_PLATFORM

        restart_attempts = self._restart_attempts.get(platform_id, 0)
        if (
            error_count >= self.config.max_errors_threshold // 2
            and restart_attempts < self.config.max_restart_attempts
            and self.config.auto_restart
        ):
            return IsolationStrategy.RESTART_PLATFORM

        if self.config.degraded_mode_enabled:
            return IsolationStrategy.DEGRADED_MODE

        return IsolationStrategy.CONTINUE

    async def _execute_strategy(
        self,
        strategy: IsolationStrategy,
        platform_id: str,
        error_count: int,
    ):
        """执行隔离策略"""
        if strategy == IsolationStrategy.RESTART_PLATFORM:
            logger.info(f"执行策略: 重启平台 {platform_id}")
            self._restart_attempts[platform_id] = (
                self._restart_attempts.get(platform_id, 0) + 1
            )
            await self.runtime_manager.restart_platform(platform_id)

        elif strategy == IsolationStrategy.DISABLE_PLATFORM:
            logger.warning(f"执行策略: 禁用平台 {platform_id}")
            await self.runtime_manager.stop_platform(platform_id)
            self._disabled_platforms.add(platform_id)

        elif strategy == IsolationStrategy.DEGRADED_MODE:
            logger.warning(f"执行策略: 平台 {platform_id} 进入降级模式")

    def _update_degradation_level(self):
        """更新系统降级级别"""
        total_platforms = len(self.runtime_manager.platform_manager.platforms)
        if total_platforms == 0:
            self._degradation_level = DegradationLevel.NONE
            return

        disabled_count = len(self._disabled_platforms)
        ratio = disabled_count / total_platforms

        if ratio >= 0.8:
            self._degradation_level = DegradationLevel.CRITICAL
        elif ratio >= 0.6:
            self._degradation_level = DegradationLevel.HIGH
        elif ratio >= 0.4:
            self._degradation_level = DegradationLevel.MEDIUM
        elif ratio >= 0.2:
            self._degradation_level = DegradationLevel.LOW
        else:
            self._degradation_level = DegradationLevel.NONE

        if self._degradation_level != DegradationLevel.NONE:
            logger.warning(
                f"系统进入降级模式: {self._degradation_level.value} "
                f"({disabled_count}/{total_platforms} 平台已禁用)"
            )

    async def _recovery_loop(self):
        """恢复循环"""
        while self._disabled_platforms or any(
            v > 0 for v in self._restart_attempts.values()
        ):
            await asyncio.sleep(self.config.recovery_check_interval)

            # 尝试恢复被禁用的平台
            for platform_id in list(self._disabled_platforms):
                await self._try_recover_platform(platform_id)

            # 重置重启尝试计数
            self._restart_attempts.clear()

        logger.info("所有平台已恢复，停止恢复检查")

    async def _try_recover_platform(self, platform_id: str):
        """尝试恢复平台"""
        logger.info(f"尝试恢复平台 {platform_id}")

        success = await self.runtime_manager.start_platform(platform_id)
        if success:
            self._disabled_platforms.discard(platform_id)
            self._platform_errors[platform_id] = []

            # 标记故障记录为已解决
            for record in self._fault_records.get(platform_id, []):
                if not record.resolved:
                    record.resolved = True
                    record.resolved_at = datetime.now()

            logger.info(f"平台 {platform_id} 已恢复")
        else:
            logger.warning(f"平台 {platform_id} 恢复失败，将稍后重试")

    async def enable_platform(self, platform_id: str) -> bool:
        """手动启用平台

        Args:
            platform_id: 平台ID

        Returns:
            是否启用成功
        """
        if platform_id in self._disabled_platforms:
            self._disabled_platforms.discard(platform_id)

        self._restart_attempts[platform_id] = 0
        if platform_id in self._platform_errors:
            self._platform_errors[platform_id] = []

        return await self.runtime_manager.start_platform(platform_id)

    async def disable_platform(self, platform_id: str) -> bool:
        """手动禁用平台

        Args:
            platform_id: 平台ID

        Returns:
            是否禁用成功
        """
        success = await self.runtime_manager.stop_platform(platform_id)
        if success:
            self._disabled_platforms.add(platform_id)
        return success

    def get_fault_records(self, platform_id: str | None = None) -> List[Dict[str, Any]]:
        """获取故障记录

        Args:
            platform_id: 平台ID，为None时返回所有记录

        Returns:
            故障记录列表
        """
        records = []
        if platform_id:
            for record in self._fault_records.get(platform_id, []):
                records.append(
                    {
                        "platform_id": record.platform_id,
                        "error_type": record.error_type,
                        "error_message": record.error_message,
                        "timestamp": record.timestamp.isoformat(),
                        "isolation_strategy": record.isolation_strategy.value,
                        "resolved": record.resolved,
                        "resolved_at": record.resolved_at.isoformat()
                        if record.resolved_at
                        else None,
                    }
                )
        else:
            for pid, recs in self._fault_records.items():
                for record in recs:
                    records.append(
                        {
                            "platform_id": record.platform_id,
                            "error_type": record.error_type,
                            "error_message": record.error_message,
                            "timestamp": record.timestamp.isoformat(),
                            "isolation_strategy": record.isolation_strategy.value,
                            "resolved": record.resolved,
                            "resolved_at": record.resolved_at.isoformat()
                            if record.resolved_at
                            else None,
                        }
                    )
        return records

    def get_isolation_status(self) -> Dict[str, Any]:
        """获取隔离状态

        Returns:
            隔离状态信息
        """
        return {
            "degradation_level": self._degradation_level.value,
            "disabled_platforms": list(self._disabled_platforms),
            "restart_attempts": self._restart_attempts.copy(),
            "platform_errors": {
                pid: len(errors) for pid, errors in self._platform_errors.items()
            },
            "config": {
                "max_errors_threshold": self.config.max_errors_threshold,
                "error_window_seconds": self.config.error_window_seconds,
                "auto_restart": self.config.auto_restart,
                "max_restart_attempts": self.config.max_restart_attempts,
                "auto_disable": self.config.auto_disable,
                "degraded_mode_enabled": self.config.degraded_mode_enabled,
            },
        }
