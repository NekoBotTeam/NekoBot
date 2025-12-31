"""Slack 平台适配器

参考 AstrBot 的 Slack 适配器实现
"""

import asyncio
from typing import Any, Optional

from loguru import logger

from ...base import BasePlatform
from ...register import register_platform_adapter
from ...base import PlatformStatus


@register_platform_adapter(
    "slack",
    "Slack 适配器 (基于官方 API)",
    default_config_tmpl={
        "type": "slack",
        "enable": False,
        "id": "slack",
        "name": "NekoBot",
        "bot_token": "",
        "signing_secret": "",
        "app_level_token": "",
    },
    adapter_display_name="Slack",
    support_streaming_message=True,
)
class SlackPlatform(BasePlatform):
    """Slack 平台适配器"""

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: Optional[asyncio.Queue] = None,
    ) -> None:
        super().__init__(platform_config, platform_settings, event_queue)

        self.bot_token = platform_config.get("bot_token", "")
        self.signing_secret = platform_config.get("signing_secret", "")
        self.app_level_token = platform_config.get("app_level_token", "")

        self._client = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """启动 Slack 适配器"""
        if not self.bot_token:
            logger.error("[Slack] Bot Token 未配置")
            self.status = PlatformStatus.ERROR
            self.record_error("Bot Token 未配置")
            return

        logger.info("[Slack] 正在启动 Slack 适配器...")

        try:
            from slack_sdk.web.async_client import AsyncWebClient
            self._client = AsyncWebClient(
                token=self.bot_token,
                signing_secret=self.signing_secret,
            )

            await self._client.connect()
            self.status = PlatformStatus.RUNNING
            logger.info("[Slack] Slack 适配器已启动")

            # 等待关闭信号
            await self._shutdown_event.wait()

        except Exception as e:
            logger.error(f"[Slack] 启动失败: {e}")
            self.status = PlatformStatus.ERROR
            self.record_error(str(e))

    async def stop(self) -> None:
        """停止 Slack 适配器"""
        logger.info("[Slack] 正在停止适配器...")
        self._shutdown_event.set()

        if self._client:
            try:
                await self._client.close()
            except Exception as e:
                logger.warning(f"[Slack] 关闭客户端时出错: {e}")

        self.status = PlatformStatus.STOPPED
        logger.info("[Slack] 适配器已停止")

    async def send_message(
        self,
        message_type: str,
        target_id: str,
        message: str,
        **kwargs,
    ) -> dict[str, Any]:
        """发送消息

        Args:
            message_type: 消息类型（private/group/channel）
            target_id: 目标ID（用户ID/频道ID）
            message: 消息内容
            **kwargs: 其他参数

        Returns:
            发送结果
        """
        try:
            if not self._client:
                logger.error("[Slack] 客户端未初始化")
                return {"status": "failed", "message": "客户端未初始化"}

            # 判断消息类型
            if message_type == "private":
                await self._client.chat_postMessage(
                    channel=target_id,
                    text=message,
                )
            elif message_type == "group":
                await self._client.chat_postMessage(
                    channel=target_id,
                    text=message,
                )
            else:
                # 频道消息
                await self._client.chat_postMessage(
                    channel=target_id,
                    text=message,
                )

            logger.debug(f"[Slack] 消息已发送到 {target_id}")
            return {"status": "success", "message": "消息已发送"}

        except Exception as e:
            logger.error(f"[Slack] 发送消息失败: {e}")
            return {"status": "failed", "message": str(e)}

    async def handle_webhook(self, event_data: dict) -> Any:
        """处理 Webhook 事件

        Args:
            event_data: Webhook 事件数据

        Returns:
            Webhook 响应
        """
        try:
            # 解析 Slack 事件
            event_type = event_data.get("type", "")
            logger.debug(f"[Slack] 收到事件类型: {event_type}")

            if event_type == "url_verification":
                # URL 验证事件
                challenge = event_data.get("challenge", "")
                # 返回响应
                return {"challenge": challenge}

            elif event_type == "event_callback":
                # 事件回调事件
                # 解析事件载荷
                payload = event_data.get("event", {})
                event_id = payload.get("event_id", "")

                # 处理消息事件
                if payload.get("type") == "message":
                    await self._handle_message_event(payload, event_id)

            return {"status": "ok"}

        except Exception as e:
            logger.error(f"[Slack] 处理 Webhook 事件失败: {e}")
            return {"status": "error", "message": str(e)}

    async def _handle_message_event(self, payload: dict, event_id: str) -> None:
        """处理消息事件"""
        try:
            # 构建事件数据
            event_data = {
                "platform_id": self.id,
                "type": "message",
                "message_type": "channel" if payload.get("channel", {}).get("is_im", False) else "private",
                "sender_id": payload.get("user", ""),
                "sender_name": payload.get("user", {}).get("real_name", ""),
                "group_id": payload.get("channel", ""),
                "session_id": payload.get("channel", ""),
                "message_id": event_id,
                "message": self._parse_message_content(payload),
                "timestamp": int(payload.get("ts", 0)) // 1000000,
                "raw_message": payload,
            }

            # 检查是否是机器人自己的消息
            if payload.get("bot_id") == self._client.auth_test().get("user_id"):
                return

            await self.handle_event(event_data)

        except Exception as e:
            logger.error(f"[Slack] 处理消息事件失败: {e}")

    def _parse_message_content(self, payload: dict) -> str:
        """解析消息内容"""
        text = ""

        # 解析文本
        if "text" in payload:
            text += payload.get("text", "")

        # 解析附件（图片、文件等）
        attachments = payload.get("files", [])
        for attachment in attachments:
            if attachment.get("mimetype", "").startswith("image"):
                text += "[图片]"
            elif attachment.get("filetype") == "text":
                text += f"[文件: {attachment.get('filename', '')}]"

        return text

    def get_stats(self) -> dict:
        """获取平台统计信息"""
        stats = super().get_stats()
        return stats
