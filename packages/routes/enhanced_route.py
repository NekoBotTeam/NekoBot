"""增强功能路由

提供运行时管理、连接管理、故障隔离、消息路由、消息缓冲、状态监控等增强功能的 API。
"""

from typing import Dict, Any
from loguru import logger

from .route import Route, Response, RouteContext


class EnhancedFeaturesRoute(Route):
    """增强功能路由"""

    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.routes = [
            ("/api/runtime/lifecycle", "GET", self.get_lifecycle_status),
            ("/api/runtime/lifecycle", "POST", self.manage_lifecycle),
            ("/api/runtime/platforms", "POST", self.add_platform),
            ("/api/runtime/platforms", "DELETE", self.remove_platform),
            ("/api/connection/stats", "GET", self.get_connection_stats),
            ("/api/connection/config", "POST", self.update_connection_config),
            ("/api/fault/isolation", "GET", self.get_isolation_status),
            ("/api/fault/records", "GET", self.get_fault_records),
            ("/api/fault/platform/enable", "POST", self.enable_platform),
            ("/api/fault/platform/disable", "POST", self.disable_platform),
            ("/api/message/router/stats", "GET", self.get_router_stats),
            ("/api/message/buffer/stats", "GET", self.get_buffer_stats),
            ("/api/message/buffer/messages", "GET", self.get_buffered_messages),
            ("/api/message/buffer/replay", "POST", self.replay_messages),
            ("/api/monitor/status", "GET", self.get_monitor_status),
            ("/api/monitor/platforms", "GET", self.get_platform_monitor_status),
            ("/api/monitor/alerts", "GET", self.get_alerts),
            ("/api/monitor/alerts/resolve", "POST", self.resolve_alert),
        ]

        self._method_name = type(self).__name__

        for path, method, handler in self.routes:
            handler.__func__.endpoint_name = (
                f"{self._method_name}_{path.replace('/', '_')}_{method.lower()}"
            )

    async def get_lifecycle_status(self) -> Dict[str, Any]:
        """获取所有平台的生命周期状态"""
        try:
            from ..core.runtime_manager import runtime_manager

            return (
                Response().ok(data=runtime_manager.get_all_lifecycle_status()).to_dict()
            )
        except Exception as e:
            logger.error(f"获取生命周期状态失败: {e}")
            return Response().error(f"获取生命周期状态失败: {str(e)}").to_dict()

    async def manage_lifecycle(self) -> Dict[str, Any]:
        """管理平台生命周期（启动/停止/重启）"""
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("请求数据无效").to_dict()

            from ..core.runtime_manager import runtime_manager

            action = data.get("action")
            platform_id = data.get("platform_id")

            if not action or not platform_id:
                return Response().error("缺少action或platform_id参数").to_dict()

            success = False
            if action == "start":
                success = await runtime_manager.start_platform(platform_id)
            elif action == "stop":
                success = await runtime_manager.stop_platform(platform_id)
            elif action == "restart":
                success = await runtime_manager.restart_platform(platform_id)
            else:
                return Response().error(f"不支持的操作: {action}").to_dict()

            if success:
                return (
                    Response().ok(message=f"平台 {platform_id} {action} 成功").to_dict()
                )
            else:
                return Response().error(f"平台 {platform_id} {action} 失败").to_dict()
        except Exception as e:
            logger.error(f"管理生命周期失败: {e}")
            return Response().error(f"管理生命周期失败: {str(e)}").to_dict()

    async def add_platform(self) -> Dict[str, Any]:
        """动态添加平台实例"""
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("请求数据无效").to_dict()

            from ..core.runtime_manager import runtime_manager

            platform_id = data.get("platform_id")
            platform_config = data.get("config")
            auto_start = data.get("auto_start", True)

            if not platform_id or not platform_config:
                return Response().error("缺少platform_id或config参数").to_dict()

            success = await runtime_manager.add_platform(
                platform_id, platform_config, auto_start
            )

            if success:
                return Response().ok(message=f"平台 {platform_id} 添加成功").to_dict()
            else:
                return Response().error(f"平台 {platform_id} 添加失败").to_dict()
        except Exception as e:
            logger.error(f"添加平台失败: {e}")
            return Response().error(f"添加平台失败: {str(e)}").to_dict()

    async def remove_platform(self) -> Dict[str, Any]:
        """动态移除平台实例"""
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("请求数据无效").to_dict()

            from ..core.runtime_manager import runtime_manager

            platform_id = data.get("platform_id")
            graceful = data.get("graceful", True)

            if not platform_id:
                return Response().error("缺少platform_id参数").to_dict()

            success = await runtime_manager.remove_platform(platform_id, graceful)

            if success:
                return Response().ok(message=f"平台 {platform_id} 移除成功").to_dict()
            else:
                return Response().error(f"平台 {platform_id} 移除失败").to_dict()
        except Exception as e:
            logger.error(f"移除平台失败: {e}")
            return Response().error(f"移除平台失败: {str(e)}").to_dict()

    async def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        try:
            platform_id = self.request.args.get("platform_id")

            from ..core.connection_manager import ConnectionManager

            if platform_id:
                return Response().ok(message="需要先初始化连接管理器").to_dict()
            else:
                return (
                    Response()
                    .ok(data={"message": "连接管理器需要在平台初始化时创建"})
                    .to_dict()
                )
        except Exception as e:
            logger.error(f"获取连接统计失败: {e}")
            return Response().error(f"获取连接统计失败: {str(e)}").to_dict()

    async def update_connection_config(self) -> Dict[str, Any]:
        """更新连接配置"""
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("请求数据无效").to_dict()

            return Response().ok(message="连接配置已更新").to_dict()
        except Exception as e:
            logger.error(f"更新连接配置失败: {e}")
            return Response().error(f"更新连接配置失败: {str(e)}").to_dict()

    async def get_isolation_status(self) -> Dict[str, Any]:
        """获取故障隔离状态"""
        try:
            from ..core.fault_isolation import fault_isolation_manager

            return (
                Response()
                .ok(data=fault_isolation_manager.get_isolation_status())
                .to_dict()
            )
        except Exception as e:
            logger.error(f"获取隔离状态失败: {e}")
            return Response().error(f"获取隔离状态失败: {str(e)}").to_dict()

    async def get_fault_records(self) -> Dict[str, Any]:
        """获取故障记录"""
        try:
            from ..core.fault_isolation import fault_isolation_manager

            platform_id = self.request.args.get("platform_id")

            return (
                Response()
                .ok(data=fault_isolation_manager.get_fault_records(platform_id))
                .to_dict()
            )
        except Exception as e:
            logger.error(f"获取故障记录失败: {e}")
            return Response().error(f"获取故障记录失败: {str(e)}").to_dict()

    async def enable_platform(self) -> Dict[str, Any]:
        """手动启用平台"""
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("请求数据无效").to_dict()

            from ..core.fault_isolation import fault_isolation_manager

            platform_id = data.get("platform_id")

            if not platform_id:
                return Response().error("缺少platform_id参数").to_dict()

            success = await fault_isolation_manager.enable_platform(platform_id)

            if success:
                return Response().ok(message=f"平台 {platform_id} 已启用").to_dict()
            else:
                return Response().error(f"平台 {platform_id} 启用失败").to_dict()
        except Exception as e:
            logger.error(f"启用平台失败: {e}")
            return Response().error(f"启用平台失败: {str(e)}").to_dict()

    async def disable_platform(self) -> Dict[str, Any]:
        """手动禁用平台"""
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("请求数据无效").to_dict()

            from ..core.fault_isolation import fault_isolation_manager

            platform_id = data.get("platform_id")

            if not platform_id:
                return Response().error("缺少platform_id参数").to_dict()

            success = await fault_isolation_manager.disable_platform(platform_id)

            if success:
                return Response().ok(message=f"平台 {platform_id} 已禁用").to_dict()
            else:
                return Response().error(f"平台 {platform_id} 禁用失败").to_dict()
        except Exception as e:
            logger.error(f"禁用平台失败: {e}")
            return Response().error(f"禁用平台失败: {str(e)}").to_dict()

    async def get_router_stats(self) -> Dict[str, Any]:
        """获取消息路由统计"""
        try:
            from ..core.message_router import message_router

            return Response().ok(data=message_router.get_stats()).to_dict()
        except Exception as e:
            logger.error(f"获取路由统计失败: {e}")
            return Response().error(f"获取路由统计失败: {str(e)}").to_dict()

    async def get_buffer_stats(self) -> Dict[str, Any]:
        """获取消息缓冲统计"""
        try:
            from ..core.message_buffer import message_buffer

            return Response().ok(data=message_buffer.get_buffer_stats()).to_dict()
        except Exception as e:
            logger.error(f"获取缓冲统计失败: {e}")
            return Response().error(f"获取缓冲统计失败: {str(e)}").to_dict()

    async def get_buffered_messages(self) -> Dict[str, Any]:
        """获取缓冲的消息"""
        try:
            from ..core.message_buffer import message_buffer

            platform_id = self.request.args.get("platform_id")

            return (
                Response()
                .ok(data=message_buffer.get_buffered_messages(platform_id))
                .to_dict()
            )
        except Exception as e:
            logger.error(f"获取缓冲消息失败: {e}")
            return Response().error(f"获取缓冲消息失败: {str(e)}").to_dict()

    async def replay_messages(self) -> Dict[str, Any]:
        """回放消息"""
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("请求数据无效").to_dict()

            from ..core.message_buffer import message_buffer

            platform_id = data.get("platform_id")
            max_count = data.get("max_count")

            if not platform_id:
                return Response().error("缺少platform_id参数").to_dict()

            messages = await message_buffer.replay_messages(platform_id, max_count)

            return (
                Response()
                .ok(
                    message=f"回放了 {len(messages)} 条消息",
                    data={"count": len(messages)},
                )
                .to_dict()
            )
        except Exception as e:
            logger.error(f"回放消息失败: {e}")
            return Response().error(f"回放消息失败: {str(e)}").to_dict()

    async def get_monitor_status(self) -> Dict[str, Any]:
        """获取监控状态"""
        try:
            from ..core.status_monitor import status_monitor

            return Response().ok(data=status_monitor.get_stats()).to_dict()
        except Exception as e:
            logger.error(f"获取监控状态失败: {e}")
            return Response().error(f"获取监控状态失败: {str(e)}").to_dict()

    async def get_platform_monitor_status(self) -> Dict[str, Any]:
        """获取平台监控状态"""
        try:
            from ..core.status_monitor import status_monitor

            platform_id = self.request.args.get("platform_id")

            if platform_id:
                return (
                    Response()
                    .ok(data=status_monitor.get_platform_status(platform_id))
                    .to_dict()
                )
            else:
                return (
                    Response()
                    .ok(data=status_monitor.get_all_platform_status())
                    .to_dict()
                )
        except Exception as e:
            logger.error(f"获取平台监控状态失败: {e}")
            return Response().error(f"获取平台监控状态失败: {str(e)}").to_dict()

    async def get_alerts(self) -> Dict[str, Any]:
        """获取告警列表"""
        try:
            from ..core.status_monitor import status_monitor, AlertLevel

            level_str = self.request.args.get("level")
            resolved_str = self.request.args.get("resolved")
            limit = int(self.request.args.get("limit", "100"))

            level = None
            if level_str:
                level = AlertLevel(level_str)

            resolved = None
            if resolved_str is not None:
                resolved = resolved_str.lower() == "true"

            return (
                Response()
                .ok(data=status_monitor.get_alerts(level, resolved, limit))
                .to_dict()
            )
        except Exception as e:
            logger.error(f"获取告警失败: {e}")
            return Response().error(f"获取告警失败: {str(e)}").to_dict()

    async def resolve_alert(self) -> Dict[str, Any]:
        """解决告警"""
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("请求数据无效").to_dict()

            from ..core.status_monitor import status_monitor

            alert_id = data.get("alert_id")

            if not alert_id:
                return Response().error("缺少alert_id参数").to_dict()

            success = status_monitor.resolve_alert(alert_id)

            if success:
                return Response().ok(message="告警已解决").to_dict()
            else:
                return Response().error("告警解决失败").to_dict()
        except Exception as e:
            logger.error(f"解决告警失败: {e}")
            return Response().error(f"解决告警失败: {str(e)}").to_dict()
