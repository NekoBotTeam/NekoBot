"""NekoBot 核心类型定义

提供统一的类型系统，支持类型检查和 IDE 补全
"""

from typing import TypeVar, ParamSpec, AsyncIterator, AsyncGenerator, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, field_validator


# ============== 基础类型变量 ==============

T = TypeVar("T")  # 通用类型
T_Context = TypeVar("T_Context")  # 上下文类型
T_Platform = TypeVar("T_Platform")  # 平台类型
T_Response = TypeVar("T_Response", covariant=True)  # 响应类型（协变）

P = ParamSpec("P")  # 参数规格


# ============== 消息类型 ==============

class MessageType(str, Enum):
    """消息类型枚举"""
    TEXT = "text"
    IMAGE = "image"
    AT = "at"
    REPLY = "reply"
    VOICE = "voice"
    VIDEO = "video"
    FILE = "file"
    LOCATION = "location"
    JSON = "json"
    THINK = "think"
    AUDIO_URL = "audio_url"
    UNKNOWN = "unknown"


@dataclass
class MessageSegment:
    """消息段

    表示消息中的一个片段，如文本、图片等
    """
    type: MessageType
    data: dict[str, any]

    def __str__(self) -> str:
        if self.type == MessageType.TEXT:
            return self.data.get("text", "")
        return f"[{self.type.value}]"

    def to_dict(self) -> dict[str, any]:
        """转换为字典"""
        return {
            "type": self.type.value,
            "data": self.data
        }


@dataclass
class MessageChain(list):
    """消息链

    一个完整的消息，由多个消息段组成
    """
    def __init__(self, segments: list | None = None):
        super().__init__(segments or [])

    @classmethod
    def text(cls, text: str) -> "MessageChain":
        """创建纯文本消息"""
        return cls([MessageSegment(MessageType.TEXT, {"text": text})])

    @classmethod
    def at(cls, user_id: str) -> "MessageChain":
        """创建 @ 消息"""
        return cls([MessageSegment(MessageType.AT, {"user_id": user_id})])

    @classmethod
    def image(cls, url: str) -> "MessageChain":
        """创建图片消息"""
        return cls([MessageSegment(MessageType.IMAGE, {"url": url})])

    @classmethod
    def think(cls, think: str, encrypted: bool = False) -> "MessageChain":
        """创建思考内容消息"""
        return cls([MessageSegment(
            MessageType.THINK,
            {"think": think, "encrypted": encrypted}
        )])

    @classmethod
    def audio_url(cls, url: str, audio_id: str | None = None) -> "MessageChain":
        """创建音频 URL 消息"""
        return cls([MessageSegment(
            MessageType.AUDIO_URL,
            {"url": url, "id": audio_id}
        )])

    @classmethod
    def from_dict(cls, data: dict | list) -> "MessageChain":
        """从字典创建消息链"""
        if isinstance(data, dict):
            if data.get("type") == "text":
                return cls.text(data.get("text", ""))
            return cls([MessageSegment(MessageType(data.get("type", "unknown")), data)])
        elif isinstance(data, list):
            segments = []
            for item in data:
                if isinstance(item, dict):
                    segments.append(MessageSegment(
                        MessageType(item.get("type", "unknown")),
                        item
                    ))
            return cls(segments)
        return cls()

    @property
    def text_content(self) -> str:
        """提取纯文本内容"""
        return "".join(str(seg) for seg in self if seg.type == MessageType.TEXT)

    @property
    def plain_text(self) -> str:
        """获取纯文本（同 text_content）"""
        return self.text_content

    @property
    def think_content(self) -> str:
        """提取思考内容"""
        thinks = []
        for seg in self:
            if seg.type == MessageType.THINK and not seg.data.get("encrypted"):
                thinks.append(seg.data.get("think", ""))
        return "".join(thinks)

    def __str__(self) -> str:
        return "".join(str(seg) for seg in self)


# ============== 工具调用类型 ==============

@dataclass
class ToolCall:
    """工具调用"""
    id: str
    function_name: str
    arguments: str
    type: str = "function"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.function_name,
                "arguments": self.arguments,
            }
        }


# ============== 事件类型 ==============

@dataclass
class MessageEvent:
    """消息事件

    表示来自平台的一个消息事件
    """
    platform_id: str  # 平台 ID
    channel_id: str  # 频道/群组 ID
    user_id: str  # 用户 ID
    message: MessageChain  # 消息内容
    message_id: str  # 消息 ID
    reply_to_message_id: str | None = None  # 回复的消息 ID
    sender: dict | None = None  # 发送者信息
    raw_event: dict | None = None  # 原始事件
    timestamp: float = 0.0  # 时间戳
    _stopped: bool = False  # 事件是否被停止

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = datetime.now().timestamp()

    @property
    def unified_id(self) -> str:
        """统一的消息来源标识"""
        return f"{self.platform_id}:{self.channel_id}:{self.user_id}"

    @property
    def session_id(self) -> str:
        """会话 ID（同 unified_id）"""
        return self.unified_id

    def stop_propagation(self) -> None:
        """停止事件传播"""
        self._stopped = True

    def is_stopped(self) -> bool:
        """检查事件是否被停止"""
        return self._stopped


@dataclass
class CommandEvent(MessageEvent):
    """命令事件

    特殊的消息事件，表示用户输入的是命令
    """
    command: str = ""  # 命令名称
    args: list[str] = field(default_factory=list)  # 命令参数


# ============== 消息事件结果 ==============

class EventResultType(str, Enum):
    """事件结果类型"""
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    COMMAND_RESULT = "command_result"


@dataclass
class MessageEventResult:
    """消息事件处理结果

    插件或处理器返回的结果
    """
    type: EventResultType
    message: str | MessageChain
    voice: str | None = None
    image_url: str | None = None
    command_result: dict | None = None

    def __str__(self) -> str:
        if isinstance(self.message, MessageChain):
            return self.message.text_content
        return self.message


# ============== Agent 类型 ==============

@dataclass
class AgentResponse:
    """Agent 响应

    表示 Agent 的响应结果
    """
    content: str
    tool_calls: list[ToolCall] | None = None
    metadata: dict | None = None
    finished: bool = True  # 是否完成（用于流式响应）
    usage: dict | None = None  # Token 使用情况

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "content": self.content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls] if self.tool_calls else None,
            "finished": self.finished,
            "usage": self.usage,
            **(self.metadata or {})
        }


# ============== 流式响应类型 ==============

StreamResponse = AsyncIterator[str] | AsyncGenerator[str, None]


# ============== 上下文基类 ==============

@dataclass
class BaseContext:
    """上下文基类

    所有上下文的基类，提供基础功能
    """
    session_id: str
    platform_id: str
    user_id: str
    channel_id: str | None = None
    metadata: dict | None = None

    @property
    def unified_id(self) -> str:
        return f"{self.platform_id}:{self.user_id}"


@dataclass
class Context(BaseContext):
    """默认上下文实现

    用于大多数场景的上下文
    """
    conversation_id: str | None = None
    persona_id: str | None = None
    extra: dict | None = None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "platform_id": self.platform_id,
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "conversation_id": self.conversation_id,
            "persona_id": self.persona_id,
            "metadata": self.metadata or {},
            "extra": self.extra or {}
        }


# ============== 服务配置类型 ==============

class LLMServicesConfig(BaseModel):
    """LLM 服务配置

    管理会话级别的 LLM 服务状态
    """
    llm_enabled: bool = True
    tts_enabled: bool = True
    session_enabled: bool = True

    @field_validator("llm_enabled", "tts_enabled", "session_enabled", mode="after")
    @classmethod
    def validate_not_none(cls, v):
        """确保布尔值不为 None"""
        if v is None:
            return True
        return v


# ============== 类型导出 ==============

__all__ = [
    # 类型变量
    "T",
    "T_Context",
    "T_Platform",
    "T_Response",
    "P",
    # 消息类型
    "MessageType",
    "MessageSegment",
    "MessageChain",
    # 工具调用
    "ToolCall",
    # 事件类型
    "MessageEvent",
    "CommandEvent",
    "EventResultType",
    "MessageEventResult",
    # Agent 类型
    "AgentResponse",
    "StreamResponse",
    # 上下文类型
    "BaseContext",
    "Context",
    # 服务配置
    "LLMServicesConfig",
]
