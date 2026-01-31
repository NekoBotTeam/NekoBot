"""状态监控模块

提供平台运行状态的实时展示、消息吞吐量和延迟统计、错误率监控。
"""

import asyncio
import time
from typing import Dict, Any, Optional, Callable, List
from loguru import logger
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque, defaultdict
from enum import Enum


class MetricType(Enum):
    """指标类型"""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


class AlertLevel(Enum):
    """告警级别"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Metric:
    """指标数据"""

    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    tags: Dict[str, str] = field(default_factory=dict)
    metric_type: MetricType = MetricType.GAUGE


@dataclass
class Alert:
    """告警信息"""

    alert_id: str
    level: AlertLevel
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    platform_id: Optional[str] = None
    metric_name: Optional[str] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None


class StatusMonitor:
    """状态监控器

    提供以下功能：
    - 平台运行状态实时展示
    - 消息吞吐量和延迟统计
    - 错误率监控
    - 自定义指标和告警
    """

    def __init__(
        self,
        history_size: int = 1000,
        metrics_window_seconds: int = 60,
        alert_check_interval: float = 30.0,
    ):
        self.history_size = history_size
        self.metrics_window_seconds = metrics_window_seconds
        self.alert_check_interval = alert_check_interval

        self._metrics: Dict[str, deque[Metric]] = defaultdict(
            lambda: deque(maxlen=history_size)
        )
        self._alerts: List[Alert] = []
        self._alert_rules: List[Callable] = []

        self._message_throughput: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=300)
        )
        self._message_latency: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=1000)
        )
        self._error_counts: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

        self._stats = {
            "total_metrics": 0,
            "total_alerts": 0,
            "total_errors": 0,
            "avg_latency_ms": 0,
            "throughput_per_minute": 0,
        }

    async def start(self):
        """启动监控器"""
        if self._running:
            logger.warning("监控器已在运行")
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("状态监控器已启动")

    async def stop(self):
        """停止监控器"""
        if not self._running:
            return

        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("状态监控器已停止")

    async def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                await self._cleanup_old_metrics()
                await self._check_alerts()
                await self._update_stats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控循环出错: {e}")
            finally:
                await asyncio.sleep(self.alert_check_interval)

    def record_metric(
        self,
        name: str,
        value: float,
        tags: Dict[str, str] = None,
        metric_type: MetricType = MetricType.GAUGE,
    ):
        """记录指标

        Args:
            name: 指标名称
            value: 指标值
            tags: 标签
            metric_type: 指标类型
        """
        metric = Metric(
            name=name,
            value=value,
            tags=tags or {},
            metric_type=metric_type,
        )

        self._metrics[name].append(metric)
        self._stats["total_metrics"] += 1

    def record_message(
        self,
        platform_id: str,
        message_type: str,
        latency_ms: float,
        success: bool = True,
    ):
        """记录消息

        Args:
            platform_id: 平台ID
            message_type: 消息类型
            latency_ms: 延迟（毫秒）
            success: 是否成功
        """
        timestamp = time.time()

        self._message_throughput[platform_id].append(timestamp)
        self._message_latency[platform_id].append(latency_ms)

        if not success:
            self._error_counts[platform_id][message_type] += 1
            self._stats["total_errors"] += 1

    async def _cleanup_old_metrics(self):
        """清理过期指标"""
        cutoff = datetime.now() - timedelta(seconds=self.metrics_window_seconds)

        for name, metrics in self._metrics.items():
            while metrics and metrics[0].timestamp < cutoff:
                metrics.popleft()

    async def _check_alerts(self):
        """检查告警"""
        for rule in self._alert_rules:
            try:
                alert = await rule(self)
                if alert:
                    self._add_alert(alert)
            except Exception as e:
                logger.error(f"告警规则检查失败: {e}")

    async def _update_stats(self):
        """更新统计信息"""
        all_latency = []
        current_time = time.time()
        window_start = current_time - 60

        for platform_id, latencies in self._message_latency.items():
            all_latency.extend(latencies)

        throughput_count = sum(
            1
            for platform, timestamps in self._message_throughput.items()
            for t in timestamps
            if t > window_start
        )

        self._stats["avg_latency_ms"] = (
            sum(all_latency) / len(all_latency) if all_latency else 0
        )
        self._stats["throughput_per_minute"] = throughput_count

    def _add_alert(self, alert: Alert):
        """添加告警"""
        alert.alert_id = f"alert_{int(time.time() * 1000)}"
        self._alerts.append(alert)
        self._stats["total_alerts"] += 1

        level_logger = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARNING: logger.warning,
            AlertLevel.ERROR: logger.error,
            AlertLevel.CRITICAL: logger.critical,
        }
        level_logger[alert.level](f"告警: {alert.message} (平台: {alert.platform_id})")

    def register_alert_rule(self, rule: Callable):
        """注册告警规则

        Args:
            rule: 告警规则函数，返回 Alert 或 None
        """
        self._alert_rules.append(rule)
        logger.info("已注册告警规则")

    def get_metrics(
        self,
        name: str | None = None,
        tags: Dict[str, str] = None,
        since: datetime | None = None,
    ) -> List[Dict[str, Any]]:
        """获取指标

        Args:
            name: 指标名称
            tags: 标签过滤
            since: 起始时间

        Returns:
            指标列表
        """
        results = []

        for metric_name, metrics in self._metrics.items():
            if name and metric_name != name:
                continue

            for metric in metrics:
                if since and metric.timestamp < since:
                    continue

                if tags:
                    if not all(metric.tags.get(k) == v for k, v in tags.items()):
                        continue

                results.append(
                    {
                        "name": metric.name,
                        "value": metric.value,
                        "timestamp": metric.timestamp.isoformat(),
                        "tags": metric.tags,
                        "type": metric.metric_type.value,
                    }
                )

        return results

    def get_metric_summary(self, name: str) -> Dict[str, Any]:
        """获取指标摘要

        Args:
            name: 指标名称

        Returns:
            摘要信息
        """
        metrics = self._metrics.get(name, [])
        if not metrics:
            return {
                "name": name,
                "count": 0,
                "current": None,
                "min": None,
                "max": None,
                "avg": None,
            }

        values = [m.value for m in metrics]
        return {
            "name": name,
            "count": len(values),
            "current": values[-1],
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
        }

    def get_platform_status(self, platform_id: str) -> Dict[str, Any]:
        """获取平台状态

        Args:
            platform_id: 平台ID

        Returns:
            平台状态信息
        """
        latencies = list(self._message_latency[platform_id])
        current_time = time.time()
        window_start = current_time - 60

        recent_throughput = [
            t for t in self._message_throughput[platform_id] if t > window_start
        ]
        error_count = sum(self._error_counts[platform_id].values())
        total_count = len(latencies) + error_count
        error_rate = error_count / total_count if total_count > 0 else 0

        return {
            "platform_id": platform_id,
            "throughput_last_minute": len(recent_throughput),
            "avg_latency_ms": (sum(latencies) / len(latencies) if latencies else 0),
            "min_latency_ms": min(latencies) if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0,
            "error_count": error_count,
            "error_rate": error_rate,
            "error_breakdown": dict(self._error_counts[platform_id]),
            "healthy": error_rate < 0.05
            and (not latencies or sum(latencies) / len(latencies) < 5000),
        }

    def get_all_platform_status(self) -> Dict[str, Any]:
        """获取所有平台状态"""
        platform_ids = set(self._message_throughput.keys()) | set(
            self._message_latency.keys()
        )

        platforms = {}
        for platform_id in platform_ids:
            platforms[platform_id] = self.get_platform_status(platform_id)

        return platforms

    def get_alerts(
        self,
        level: AlertLevel | None = None,
        resolved: bool | None = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取告警

        Args:
            level: 告警级别
            resolved: 是否已解决
            limit: 返回数量限制

        Returns:
            告警列表
        """
        alerts = []
        for alert in reversed(self._alerts):
            if level and alert.level != level:
                continue
            if resolved is not None and alert.resolved != resolved:
                continue

            alerts.append(
                {
                    "alert_id": alert.alert_id,
                    "level": alert.level.value,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat(),
                    "platform_id": alert.platform_id,
                    "metric_name": alert.metric_name,
                    "resolved": alert.resolved,
                    "resolved_at": (
                        alert.resolved_at.isoformat() if alert.resolved_at else None
                    ),
                }
            )

            if len(alerts) >= limit:
                break

        return alerts

    def resolve_alert(self, alert_id: str) -> bool:
        """解决告警

        Args:
            alert_id: 告警ID

        Returns:
            是否解决成功
        """
        for alert in self._alerts:
            if alert.alert_id == alert_id and not alert.resolved:
                alert.resolved = True
                alert.resolved_at = datetime.now()
                logger.info(f"告警已解决: {alert_id}")
                return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "running": self._running,
            "metrics_count": sum(len(m) for m in self._metrics.values()),
            "alerts_count": len(self._alerts),
            "unresolved_alerts_count": sum(1 for a in self._alerts if not a.resolved),
            "platforms_count": len(self._message_throughput),
            "error_rate": (
                self._stats["total_errors"] / self._stats["total_metrics"]
                if self._stats["total_metrics"] > 0
                else 0
            ),
        }
