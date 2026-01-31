"""连接管理模块

提供平台连接的自动重连、健康检查和心跳检测功能。
"""

import asyncio
import time
from typing import Dict, Any, Optional, Callable
from loguru import logger
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class ConnectionStatus(Enum):
    """连接状态"""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class ConnectionHealth:
    """连接健康状态"""

    is_healthy: bool
    last_check: datetime = field(default_factory=datetime.now)
    latency: Optional[float] = None
    error_message: str = ""


@dataclass
class ConnectionConfig:
    """连接配置"""

    auto_reconnect: bool = True
    max_reconnect_attempts: int = 5
    reconnect_interval: float = 5.0
    reconnect_backoff: float = 2.0
    health_check_interval: float = 60.0
    heartbeat_interval: float = 30.0
    heartbeat_timeout: float = 10.0
    enable_health_check: bool = True
    enable_heartbeat: bool = True


class ConnectionManager:
    """连接管理器

    提供以下功能：
    - 自动重连机制（连接断开后自动尝试重连）
    - 连接健康检查和心跳检测
    - 连接失败通知和告警
    """

    def __init__(self, platform_id: str, config: ConnectionConfig | None = None):
        self.platform_id = platform_id
        self.config = config if config is not None else ConnectionConfig()

        self._status = ConnectionStatus.DISCONNECTED
        self._reconnect_count = 0
        self._last_connected: Optional[datetime] = None
        self._last_heartbeat: Optional[datetime] = None
        self._health_history: list[ConnectionHealth] = []
        self._max_health_history = 100

        self._connect_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

        self._connect_callback: Optional[Callable] = None
        self._disconnect_callback: Optional[Callable] = None
        self._reconnect_callback: Optional[Callable] = None

    @property
    def status(self) -> ConnectionStatus:
        """获取连接状态"""
        return self._status

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._status == ConnectionStatus.CONNECTED

    @property
    def is_reconnecting(self) -> bool:
        """是否正在重连"""
        return self._status == ConnectionStatus.RECONNECTING

    @property
    def reconnect_count(self) -> int:
        """重连次数"""
        return self._reconnect_count

    def set_callbacks(
        self,
        connect_callback: Optional[Callable] = None,
        disconnect_callback: Optional[Callable] = None,
        reconnect_callback: Optional[Callable] = None,
    ):
        """设置连接事件回调

        Args:
            connect_callback: 连接成功回调
            disconnect_callback: 断开连接回调
            reconnect_callback: 重连回调
        """
        self._connect_callback = connect_callback
        self._disconnect_callback = disconnect_callback
        self._reconnect_callback = reconnect_callback

    async def connect(self) -> bool:
        """建立连接

        Returns:
            是否连接成功
        """
        if self.is_connected:
            logger.warning(f"{self.platform_id} 已经连接")
            return True

        self._status = ConnectionStatus.CONNECTING
        logger.info(f"{self.platform_id} 正在连接...")

        try:
            if self._connect_callback:
                await self._connect_callback()

            self._status = ConnectionStatus.CONNECTED
            self._last_connected = datetime.now()
            self._reconnect_count = 0

            logger.info(f"{self.platform_id} 连接成功")

            if self.config.enable_health_check:
                self._health_check_task = asyncio.create_task(self._health_check_loop())

            if self.config.enable_heartbeat:
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            return True
        except Exception as e:
            logger.error(f"{self.platform_id} 连接失败: {e}")
            self._status = ConnectionStatus.ERROR

            if self.config.auto_reconnect:
                await self._start_reconnect()

            return False

    async def disconnect(self) -> None:
        """断开连接"""
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        if self._connect_task:
            self._connect_task.cancel()
            self._connect_task = None

        self._status = ConnectionStatus.DISCONNECTED
        self._last_connected = None

        logger.info(f"{self.platform_id} 已断开连接")

        if self._disconnect_callback:
            await self._disconnect_callback()

    async def _start_reconnect(self):
        """启动重连任务"""
        self._status = ConnectionStatus.RECONNECTING
        self._connect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        """重连循环"""
        backoff = self.config.reconnect_interval

        while (
            self.config.auto_reconnect
            and self._reconnect_count < self.config.max_reconnect_attempts
        ):
            self._reconnect_count += 1

            logger.info(
                f"{self.platform_id} 正在尝试第 {self._reconnect_count} 次重连..."
            )

            if self._reconnect_callback:
                try:
                    await self._reconnect_callback(self._reconnect_count)
                except Exception as e:
                    logger.warning(f"重连回调执行失败: {e}")

            success = await self.connect()
            if success:
                logger.info(f"{self.platform_id} 重连成功")
                return

            if self._reconnect_count < self.config.max_reconnect_attempts:
                logger.warning(f"{self.platform_id} 重连失败，{backoff} 秒后重试...")
                await asyncio.sleep(backoff)
                backoff *= self.config.reconnect_backoff

        logger.error(f"{self.platform_id} 重连失败，已达到最大重连次数")
        self._status = ConnectionStatus.ERROR

    async def _health_check_loop(self):
        """健康检查循环"""
        while self.is_connected:
            try:
                health = await self.check_health()
                self._health_history.append(health)

                if len(self._health_history) > self._max_health_history:
                    self._health_history.pop(0)

                if not health.is_healthy:
                    logger.warning(
                        f"{self.platform_id} 健康检查失败: {health.error_message}"
                    )

                    if self.config.auto_reconnect:
                        await self.disconnect()
                        await self._start_reconnect()

            except Exception as e:
                logger.error(f"{self.platform_id} 健康检查出错: {e}")
            finally:
                await asyncio.sleep(self.config.health_check_interval)

    async def _heartbeat_loop(self):
        """心跳循环"""
        while self.is_connected:
            try:
                await self._send_heartbeat()
                self._last_heartbeat = datetime.now()
            except Exception as e:
                logger.error(f"{self.platform_id} 发送心跳失败: {e}")

                time_since_last_heartbeat = (
                    datetime.now() - self._last_heartbeat
                    if self._last_heartbeat
                    else timedelta(days=1)
                )

                if time_since_last_heartbeat > timedelta(
                    seconds=self.config.heartbeat_timeout
                ):
                    logger.warning(f"{self.platform_id} 心跳超时")
                    if self.config.auto_reconnect:
                        await self.disconnect()
                        await self._start_reconnect()

            await asyncio.sleep(self.config.heartbeat_interval)

    async def check_health(self) -> ConnectionHealth:
        """检查连接健康状态

        Returns:
            健康状态
        """
        start_time = time.time()

        try:
            await self._perform_health_check()
            latency = (time.time() - start_time) * 1000

            return ConnectionHealth(
                is_healthy=True,
                latency=latency,
            )
        except Exception as e:
            return ConnectionHealth(
                is_healthy=False,
                error_message=str(e),
            )

    async def _perform_health_check(self) -> None:
        """执行健康检查（子类可重写）"""
        await asyncio.sleep(0.01)

    async def _send_heartbeat(self) -> None:
        """发送心跳（子类可重写）"""
        pass

    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息

        Returns:
            统计信息
        """
        recent_health = self._health_history[-10:] if self._health_history else []
        avg_latency = (
            sum(h.latency for h in recent_health if h.latency is not None)
            / len(recent_health)
            if recent_health
            else 0
        )

        return {
            "platform_id": self.platform_id,
            "status": self._status.value,
            "is_connected": self.is_connected,
            "reconnect_count": self._reconnect_count,
            "last_connected": self._last_connected.isoformat()
            if self._last_connected
            else None,
            "last_heartbeat": self._last_heartbeat.isoformat()
            if self._last_heartbeat
            else None,
            "uptime": (
                (datetime.now() - self._last_connected).total_seconds()
                if self._last_connected and self.is_connected
                else 0
            ),
            "avg_latency_ms": avg_latency,
            "health_history_length": len(self._health_history),
        }

    def update_config(self, config: ConnectionConfig):
        """更新连接配置

        Args:
            config: 新的连接配置
        """
        old_enable_health_check = self.config.enable_health_check
        old_enable_heartbeat = self.config.enable_heartbeat

        self.config = config

        if self.is_connected:
            if config.enable_health_check and not old_enable_health_check:
                if not self._health_check_task or self._health_check_task.done():
                    self._health_check_task = asyncio.create_task(
                        self._health_check_loop()
                    )
            elif not config.enable_health_check and old_enable_health_check:
                if self._health_check_task:
                    self._health_check_task.cancel()

            if config.enable_heartbeat and not old_enable_heartbeat:
                if not self._heartbeat_task or self._heartbeat_task.done():
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            elif not config.enable_heartbeat and old_enable_heartbeat:
                if self._heartbeat_task:
                    self._heartbeat_task.cancel()

        logger.info(f"{self.platform_id} 连接配置已更新")
