"""微信企业版平台适配器

参考 AstrBot 的 WeCom 适配器实现
"""

import asyncio
from typing import Any, Optional

from loguru import logger

from ...base import BasePlatform, PlatformStatus
from ...register import register_platform_adapter


@register_platform_adapter(
    "wecom",
    "微信企业版适配器 (基于 WeCom API)",
    default_config_tmpl={
        "type": "wecom",
        "enable": False,
        "id": "wecom",
        "name": "NekoBot",
        "corp_id": "",
        "corp_secret": "",
        "agent_id": "",
        "token": "",
        "encoding_aes_key": "",
        "receive_id": "",
        "receive_url": "",
    },
    adapter_display_name="微信企业版",
    support_streaming_message=True,
)
class WeComPlatform(BasePlatform):
    """微信企业版平台适配器"""

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: Optional[asyncio.Queue] = None,
    ) -> None:
        super().__init__(platform_config, platform_settings, event_queue)

        self.corp_id = platform_config.get("corp_id", "")
        self.corp_secret = platform_config.get("corp_secret", "")
        self.agent_id = platform_config.get("agent_id", "")
        self.token = platform_config.get("token", "")
        self.encoding_aes_key = platform_config.get("encoding_aes_key", "")
        self.receive_id = platform_config.get("receive_id", "")
        self.receive_url = platform_config.get("receive_url", "")

        self._session = None
        self._shutdown_event = asyncio.Event()

    async def _get_session(self):
        """获取或创建会话"""
        if self._session is None:
            from werobot import Robot
            robot = Robot(
                corp_id=self.corp_id,
                corp_secret=self.corp_secret,
                agent_id=self.agent_id,
            )
            robot.config["ACCESS_TOKEN"] = self.token
            self._session = robot
        return self._session

    async def start(self) -> None:
        """启动微信企业版适配器"""
        if not all([self.corp_id, self.corp_secret, self.agent_id, self.token]):
            logger.error("[WeCom] 企业ID、Secret、AgentID 或 Token 未配置")
            self.status = PlatformStatus.ERROR
            self.record_error("企业配置信息不完整")
            return

        logger.info("[WeCom] 正在启动微信企业版适配器...")

        try:
            await self._get_session()

            # 启动消息接收
            if self.receive_id:
                await self._session.MessageHandler.enable(self.receive_id)
                logger.info(f"[WeCom] 已启用接收ID: {self.receive_id}")
            else:
                # 使用回调模式
                await self._session.MessageHandler.enable_corp(
                    self.corp_id,
                    self.corp_secret,
                    self.agent_id,
                )
                logger.info("[WeCom] 已启用回调模式")

            self.status = PlatformStatus.RUNNING
            logger.info("[WeCom] 微信企业版适配器已启动")

            # 等待关闭信号
            await self._shutdown_event.wait()

        except Exception as e:
            logger.error(f"[WeCom] 启动失败: {e}")
            self.status = PlatformStatus.ERROR
            self.record_error(str(e))

    async def stop(self) -> None:
        """停止微信企业版适配器"""
        logger.info("[WeCom] 正在停止适配器...")
        self._shutdown_event.set()

        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                logger.warning(f"[WeCom] 关闭会话失败: {e}")

        self.status = PlatformStatus.STOPPED
        logger.info("[WeCom] 适配器已停止")

    async def send_message(
        self,
        message_type: str,
        target_id: str,
        message: str,
        **kwargs,
    ) -> dict[str, Any]:
        """发送消息

        Args:
            message_type: 消息类型（private/group）
            target_id: 目标ID（用户ID/群ID）
            message: 消息内容
            **kwargs: 其他参数

        Returns:
            发送结果
        """
        try:
            await self._get_session()

            # 构建消息对象
            if message_type == "private":
                # 私聊消息
                msg = self._session.Message(agentid=self.agent_id)
                msg.msgtype = "text"  # WeCom只支持文本消息
                msg.content = {
                    "content": message,
                }
            else:
                # 群聊消息
                msg = self._session.Message()
                msg.msgtype = "text"
                msg.chatid = target_id
                msg.content = {
                    "content": message,
                }

            # 发送消息
            self._session.Message.send(msg)
            logger.debug(f"[WeCom] 消息已发送到 {target_id}")

            return {"status": "success", "message": "消息已发送"}

        except Exception as e:
            logger.error(f"[WeCom] 发送消息失败: {e}")
            return {"status": "failed", "message": str(e)}

    async def handle_webhook(self, event_data: dict) -> Any:
        """处理 Webhook 事件

        Args:
            event_data: Webhook 事件数据

        Returns:
            Webhook 响应
        """
        try:
            await self._get_session()

            # 解析 WeCom 事件
            msg = self._session.Message()
            msg.load(event_data)

            # 构建事件数据
            event = {
                "platform_id": self.id,
                "type": "message",
                "message_type": "group" if msg.chatid else "private",
                "sender_id": msg.source,
                "sender_name": msg.source,
                "group_id": msg.chatid or "",
                "session_id": msg.chatid or msg.source,
                "message_id": msg.msgid,
                "message": self._parse_message(msg),
                "timestamp": int(msg.createtime.timestamp()) if msg.createtime else 0,
                "raw_message": event_data,
            }

            await self.handle_event(event)

            # 返回成功响应
            return {"status": "success"}

        except Exception as e:
            logger.error(f"[WeCom] 处理 Webhook 事件失败: {e}")
            return {"status": "error", "message": str(e)}

    def _parse_message(self, msg) -> str:
        """解析消息内容"""
        content = ""
        for item in msg.body:
            if item["type"] == "text":
                content += item["content"]
            elif item["type"] == "image":
                content += "[图片]"
        return content

    def get_stats(self) -> dict:
        """获取平台统计信息"""
        stats = super().get_stats()
        stats.update({
            "corp_id": self.corp_id,
            "agent_id": self.agent_id,
        })
        return stats
