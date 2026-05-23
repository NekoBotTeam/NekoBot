from __future__ import annotations

from collections.abc import Awaitable, Callable
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, TypeAlias, cast

from loguru import logger

from ...app import NekoBotFramework
from ...conversations.context import ConfigurationContext
from ...plugins.base import BasePlugin
from ...runtime.context import ExecutionContext, PluginContext
from .types import (
    OneBotV11Event,
    OneBotV11MessageSegment,
    OneBotV11OutboundTarget,
    OneBotV11Scene,
)

if TYPE_CHECKING:
    from ...llm.handler import LLMHandler

OutboundSender: TypeAlias = Callable[
    [OneBotV11OutboundTarget, list[dict[str, object]]],
    Awaitable[dict[str, object]],
]
DeleteSender: TypeAlias = Callable[[str], Awaitable[dict[str, object]]]


class MessageCodecLike(Protocol):
    def text(self, text: str) -> OneBotV11MessageSegment: ...

    def encode(
        self, segments: list[OneBotV11MessageSegment]
    ) -> list[dict[str, object]]: ...


class OneBotV11Dispatcher:
    def __init__(
        self,
        framework: NekoBotFramework,
        *,
        send_callable: OutboundSender,
        delete_callable: DeleteSender | None = None,
        message_codec: MessageCodecLike | None = None,
        llm_handler: LLMHandler | None = None,
    ) -> None:
        self.framework: NekoBotFramework = framework
        self.send_callable: OutboundSender = send_callable
        self.delete_callable: DeleteSender | None = delete_callable
        self.llm_handler: LLMHandler | None = llm_handler
        self.message_codec: MessageCodecLike
        if message_codec is None:
            module = import_module("packages.platforms.onebot_v11.message_codec")
            codec_class = cast(
                Callable[[], object], getattr(module, "OneBotV11MessageCodec")
            )
            self.message_codec = cast(MessageCodecLike, codec_class())
        else:
            self.message_codec = message_codec

    def build_execution_context(self, event: OneBotV11Event) -> ExecutionContext:
        roles, group_roles = self._resolve_roles(event)
        return self.framework.build_execution_context(
            event_name=event.event_name,
            actor_id=event.user_id,
            platform=event.platform,
            platform_instance_uuid=event.platform_instance_uuid,
            conversation_id=None,
            chat_id=event.chat_id,
            group_id=event.group_id,
            thread_id=None,
            message_id=event.message_id,
            scope=self._resolve_scope(event),
            roles=roles,
            group_roles=group_roles,
            is_authenticated=bool(event.user_id),
            metadata={
                **event.metadata,
                "onebot_event_type": event.event_type,
                "onebot_scene": event.scene,
                "onebot_self_id": event.self_id,
                "onebot_segments": [
                    {"type": seg.type, "data": dict(seg.data)}
                    for seg in event.segments
                ],
                "onebot_raw_event": event.raw_event,
            },
        )

    def _resolve_roles(
        self, event: OneBotV11Event
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Returns (roles, group_roles) for the event actor."""
        roles: list[str] = []
        group_roles: list[str] = []

        if event.user_id and event.user_id in self.framework.owner_ids:
            roles.append("owner")

        if event.sender is not None:
            sender_role = event.sender.role
            if sender_role == "owner":
                group_roles.append("group_owner")
            elif sender_role == "admin":
                group_roles.append("group_admin")
            elif sender_role == "member":
                group_roles.append("member")

        return tuple(roles), tuple(group_roles)

    def build_reply_target(
        self, event: OneBotV11Event
    ) -> OneBotV11OutboundTarget | None:
        if event.scene == OneBotV11Scene.GROUP and event.group_id is not None:
            return OneBotV11OutboundTarget(
                scene=OneBotV11Scene.GROUP,
                chat_id=event.group_id,
                group_id=event.group_id,
                user_id=event.user_id,
                message_id=event.message_id,
                reply_to_message_id=event.message_id,
            )

        chat_id = event.chat_id or event.user_id
        if chat_id is None:
            return None

        return OneBotV11OutboundTarget(
            scene=OneBotV11Scene.PRIVATE,
            chat_id=chat_id,
            user_id=event.user_id or chat_id,
            message_id=event.message_id,
            reply_to_message_id=event.message_id,
        )

    async def dispatch_event(
        self,
        event: OneBotV11Event,
        configuration: ConfigurationContext | None = None,
    ) -> list[PluginContext]:
        execution = self.build_execution_context(event)
        configuration = configuration or self.framework.build_configuration_context()
        conversation = self.framework.build_conversation_context(
            execution, configuration
        )
        bindings = self.framework.resolve_effective_plugin_bindings(
            configuration,
            execution=execution,
        )
        logger.debug(
            "Dispatching OneBot event: event_name={} scope={} bindings={}",
            event.event_name,
            execution.scope,
            len(bindings),
        )
        contexts: list[PluginContext] = []
        for binding in bindings:
            logger.debug("Dispatch matched plugin: {}", binding.plugin_name)
            plugin_context = self.framework.build_plugin_context(
                plugin_name=binding.plugin_name,
                execution=execution,
                configuration=configuration,
                conversation=conversation,
                binding=binding,
                reply_callable=self._build_reply_callable(event),
            )
            contexts.append(plugin_context)
            await self._dispatch_to_plugin(binding.plugin_name, event, plugin_context)

        # LLM 处理：仅限消息事件，在所有插件命令之后作为兜底响应
        if self.llm_handler is not None and event.post_type == "message":
            await self.llm_handler.handle(
                payload=self._build_payload(event),
                execution=execution,
                configuration=configuration,
                conversation=conversation,
                reply=self._build_reply_callable(event),
                recall=self._build_recall_callable(event),
            )

        return contexts

    async def _dispatch_to_plugin(
        self,
        plugin_name: str,
        event: OneBotV11Event,
        plugin_context: PluginContext,
    ) -> None:
        registered = self.framework.runtime_registry.plugins.get(plugin_name)
        if registered is None:
            return

        plugin_class = cast(type[BasePlugin], registered.plugin_class)
        plugin = plugin_class(
            plugin_context, schema_registry=self.framework.schema_registry
        )

        for handler_name, handler_spec in registered.event_handlers:
            if not self._matches_event(handler_spec.event, event.event_name):
                continue
            handler = getattr(plugin, handler_name, None)
            if callable(handler):
                logger.info(
                    "[OneBot] 分发至插件: {} -> {} (event={})",
                    plugin_name,
                    handler_name,
                    event.event_name,
                )
                await cast(Callable[[dict[str, object]], Awaitable[None]], handler)(
                    self._build_payload(event)
                )

        await plugin.on_event(event.event_name, self._build_payload(event))

    def _matches_event(self, registered_event: str, actual_event: str) -> bool:
        if registered_event == actual_event:
            return True
        return actual_event.startswith(f"{registered_event}.")

    def _build_payload(self, event: OneBotV11Event) -> dict[str, object]:
        sender = (
            {
                "user_id": event.sender.user_id,
                "nickname": event.sender.nickname,
                "card": event.sender.card,
                "role": event.sender.role,
                "level": event.sender.metadata.get("level"),
                "title": event.sender.metadata.get("title"),
            }
            if event.sender is not None
            else None
        )
        return {
            "event_type": event.event_type,
            "event_name": event.event_name,
            "scene": event.scene,
            "user_id": event.user_id,
            "group_id": event.group_id,
            "chat_id": event.chat_id,
            "message_id": event.message_id,
            "plain_text": event.plain_text,
            "effective_text": self._build_effective_text(event),
            "segments": [
                {"type": seg.type, "data": dict(seg.data)}
                for seg in event.segments
            ],
            "sender": sender,
            "metadata": event.metadata,
            "raw_event": event.raw_event,
        }

    def _build_effective_text(self, event: OneBotV11Event) -> str:
        """将消息 segments 展开为可读文本。

        - 艾特机器人自身跳过（唤醒信号）
        - 艾特其他用户转为 [@QQ号]
        - 非文本媒体标注类型标签
        """
        self_id = event.self_id
        parts: list[str] = []
        for seg in event.segments:
            if seg.type == "text":
                t = seg.data.get("text", "")
                if isinstance(t, str):
                    parts.append(t)
            elif seg.type == "at":
                qq = str(seg.data.get("qq", ""))
                if qq == "all":
                    parts.append("[@全体成员]")
                elif self_id and qq == self_id:
                    pass  # 艾特机器人本身，跳过
                elif qq:
                    parts.append(f"[@{qq}]")
            elif seg.type == "image":
                parts.append("[图片]")
            elif seg.type == "record":
                parts.append("[语音]")
            elif seg.type == "video":
                parts.append("[视频]")
        return "".join(parts).strip()

    def _build_reply_callable(
        self,
        event: OneBotV11Event,
    ) -> Callable[[str], Awaitable[str | None]]:
        async def reply(message: str) -> str | None:
            target = self.build_reply_target(event)
            if target is None:
                logger.warning(
                    "Cannot reply to event with no reply target: {}", event.event_name
                )
                return None
            outbound_segments: list[OneBotV11MessageSegment] = [
                self.message_codec.text(message)
            ]
            segments = self.message_codec.encode(outbound_segments)
            logger.info(
                "[OneBot] 发送回复 | scene={} chat_id={} | 内容: {}",
                target.scene,
                target.chat_id,
                message[:100] + "..." if len(message) > 100 else message,
            )
            resp = await self.send_callable(target, segments)
            data = resp.get("data")
            if isinstance(data, dict):
                msg_id = data.get("message_id")
                if msg_id is not None:
                    return str(msg_id)
            return None

        return reply

    def _build_recall_callable(
        self,
        event: OneBotV11Event,
    ) -> Callable[[str], Awaitable[None]]:
        async def recall(message_id: str) -> None:
            if self.delete_callable is None:
                logger.warning("[OneBot] delete_callable 未配置，无法撤回消息")
                return
            try:
                await self.delete_callable(message_id)
                logger.info("[OneBot] 已撤回消息 message_id={}", message_id)
            except Exception as exc:
                logger.warning("[OneBot] 撤回消息失败 message_id={}: {}", message_id, exc)

        return recall

    def _resolve_scope(self, event: OneBotV11Event) -> str:
        if event.scene == OneBotV11Scene.GROUP:
            return "group"
        if event.scene == OneBotV11Scene.PRIVATE:
            return "private"
        return "platform"
