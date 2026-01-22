"""平台管理器

参考 AstrBot 的 PlatformManager 实现，提供更完善的平台管理功能
"""

import asyncio
from typing import Dict, Any, Optional
from loguru import logger
import traceback

from .base import BasePlatform
from .register import get_platform_adapter, get_all_platforms


class PlatformManager:
    """平台管理器，负责管理多个平台适配器
    
    参考 AstrBot 的 PlatformManager，提供以下增强功能：
    - 平台 ID 验证和清理
    - 统一的任务包装器
    - 完善的错误处理
    - 详细的统计信息
    """

    def __init__(self):
        self.platforms: Dict[str, BasePlatform] = {}
        self.event_queue: Optional[asyncio.Queue] = None
        self.platform_settings: Dict[str, Any] = {}
        self._inst_map: Dict[str, Dict] = {}  # 平台实例映射
        self.running_tasks: list[asyncio.Task] = []  # 运行中的任务

    def set_event_queue(self, event_queue: asyncio.Queue) -> None:
        """设置事件队列"""
        self.event_queue = event_queue

    def set_platform_settings(self, settings: Dict[str, Any]) -> None:
        """设置平台设置"""
        self.platform_settings = settings

    def _is_valid_platform_id(self, platform_id: str | None) -> bool:
        """验证平台 ID 是否有效

        参考 AstrBot 的平台 ID 验证逻辑

        Args:
            platform_id: 平台 ID

        Returns:
            是否有效
        """
        if not platform_id:
            return False
        return ":" not in platform_id and "!" not in platform_id

    def _sanitize_platform_id(self, platform_id: str | None) -> tuple[str | None, bool]:
        """清理平台 ID，移除非法字符

        参考 AstrBot 的平台 ID 清理逻辑

        Args:
            platform_id: 平台 ID

        Returns:
            (清理后的ID, 是否修改过)
        """
        if not platform_id:
            return platform_id, False
        sanitized = platform_id.replace(":", "_").replace("!", "_")
        return sanitized, sanitized != platform_id

    async def _task_wrapper(self, task: asyncio.Task) -> None:
        """异步任务包装器，用于处理异步任务执行中出现的各种异常。

        参考 AstrBot 的 _task_wrapper 实现

        Args:
            task (asyncio.Task): 要执行的异步任务
        """
        try:
            await task
        except asyncio.CancelledError:
            pass  # 任务被取消，静默处理
        except Exception as e:
            # 获取完整的异常堆栈信息，按行分割并记录到日志中
            logger.error(f"------- 任务 {task.get_name()} 发生错误: {e}")
            for line in traceback.format_exc().split("\n"):
                logger.error(f"|    {line}")
            logger.error("-------")

    async def load_platforms(self, platforms_config: Dict[str, Dict[str, Any]]) -> None:
        """加载平台适配器

        Args:
            platforms_config: 平台配置字典
        """
        logger.info("开始加载平台适配器...")

        for platform_id, platform_config in platforms_config.items():
            if not platform_config.get("enable", False):
                logger.debug(f"平台 {platform_id} 未启用，跳过")
                continue

            # 验证和清理平台 ID
            if not self._is_valid_platform_id(platform_id):
                sanitized_id, changed = self._sanitize_platform_id(platform_id)
                if sanitized_id and changed:
                    logger.warning(
                        f"平台 ID {platform_id!r} 包含非法字符 ':' 或 '!'，已替换为 {sanitized_id!r}。",
                    )
                    platform_id = sanitized_id
                    platform_config["id"] = sanitized_id
                else:
                    logger.error(
                        f"平台 ID {platform_id!r} 不能为空或无效，跳过加载该平台适配器。",
                    )
                    continue

            platform_type = platform_config.get("type", platform_id)
            adapter_cls = get_platform_adapter(platform_type)

            if not adapter_cls:
                logger.warning(f"未找到平台适配器: {platform_type}")
                continue

            try:
                platform = adapter_cls(
                    platform_config=platform_config,
                    platform_settings=self.platform_settings,
                    event_queue=self.event_queue,
                )
                self.platforms[platform_id] = platform
                self._inst_map[platform_id] = {
                    "inst": platform,
                    "client_id": getattr(platform, "client_self_id", None),
                }
                logger.info(
                    f"已加载平台适配器: {platform_id} ({platform_config.get('name', 'Unknown')})"
                )
            except Exception as e:
                logger.error(f"加载平台适配器 {platform_id} 失败: {e}")
                logger.error(traceback.format_exc())

        logger.info(f"平台适配器加载完成，共 {len(self.platforms)} 个平台")

    async def start_all(self) -> None:
        """启动所有平台适配器"""
        logger.info("启动所有平台适配器...")
        for platform_id, platform in self.platforms.items():
            try:
                # 使用任务包装器启动平台
                platform_task = asyncio.create_task(
                    platform.start(),
                    name=f"platform_{platform_id}"
                )
                wrapped_task = asyncio.create_task(
                    self._task_wrapper(platform_task),
                    name=f"platform_wrapper_{platform_id}"
                )
                self.running_tasks.append(wrapped_task)
                logger.info(f"平台 {platform_id} 已启动")
            except Exception as e:
                logger.error(f"启动平台 {platform_id} 失败: {e}")
                logger.error(traceback.format_exc())

    async def stop_all(self) -> None:
        """停止所有平台适配器"""
        logger.info("停止所有平台适配器...")

        # 取消所有运行中的任务
        for task in self.running_tasks:
            if not task.done():
                task.cancel()

        # 等待任务结束
        for task in self.running_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"任务 {task.get_name()} 停止时出错: {e}")

        self.running_tasks.clear()

        # 停止所有平台
        for platform_id, platform in self.platforms.items():
            try:
                if hasattr(platform, "stop"):
                    await platform.stop()
                logger.info(f"平台 {platform_id} 已停止")
            except Exception as e:
                logger.error(f"停止平台 {platform_id} 失败: {e}")
                logger.error(traceback.format_exc())

    async def send_message(
        self,
        platform_id: str,
        message_type: str,
        target_id: str,
        message: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """通过指定平台发送消息

        Args:
            platform_id: 平台ID
            message_type: 消息类型（private/group）
            target_id: 目标ID
            message: 消息内容
            **kwargs: 其他参数

        Returns:
            发送结果
        """
        platform = self.platforms.get(platform_id)
        if not platform:
            return {"status": "failed", "message": f"平台 {platform_id} 不存在"}

        return await platform.send_message(message_type, target_id, message, **kwargs)

    def get_platform(self, platform_id: str) -> Optional[BasePlatform]:
        """获取平台适配器"""
        return self.platforms.get(platform_id)

    def get_all_platforms(self) -> Dict[str, BasePlatform]:
        """获取所有平台适配器"""
        return self.platforms

    def get_enabled_platforms(self) -> Dict[str, BasePlatform]:
        """获取所有已启用的平台适配器"""
        return {pid: p for pid, p in self.platforms.items() if p.is_enabled()}

    def get_available_platforms(self) -> list[Dict[str, Any]]:
        """获取所有可用的平台类型"""
        return get_all_platforms()

    def get_all_stats(self) -> list[Dict[str, Any]]:
        """获取所有平台的统计信息

        参考 AstrBot 的 get_all_stats() 实现

        Returns:
            包含所有平台统计信息的列表
        """
        stats_list = []
        total_errors = 0
        running_count = 0
        error_count = 0

        for inst in self.platforms.values():
            try:
                stat = inst.get_stats()
                stats_list.append(stat)
                total_errors += stat.get("error_count", 0)
                if stat.get("status") == "running":
                    running_count += 1
                elif stat.get("status") == "error":
                    error_count += 1
            except Exception as e:
                # 如果获取统计信息失败，记录基本信息
                logger.warning(f"获取平台统计信息失败: {e}")
                stats_list.append(
                    {
                        "id": getattr(inst, "config", {}).get("id", "unknown"),
                        "type": getattr(inst, "__class__.__name__", "unknown"),
                        "status": "unknown",
                        "error_count": 0,
                        "last_error": None,
                    }
                )

        return {
            "platforms": stats_list,
            "summary": {
                "total": len(stats_list),
                "running": running_count,
                "error": error_count,
                "total_errors": total_errors,
            },
        }
