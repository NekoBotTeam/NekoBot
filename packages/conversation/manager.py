"""NekoBot 会话管理

实现会话/对话分离，支持对话切换
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Awaitable, Any
from pathlib import Path
import json
import uuid
from loguru import logger

from ..types import MessageChain


# ============== 会话和对话 ==============

@dataclass
class Conversation:
    """对话

    表示一次完整的对话，包含消息历史
    """
    conversation_id: str
    session_id: str
    title: str
    messages: list[dict[str, str]] = field(default_factory=list)
    persona_id: str | None = None
    kb_ids: list[str] = field(default_factory=list)  # 关联的知识库
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_message(self, role: str, content: str | MessageChain) -> None:
        """添加消息

        Args:
            role: 角色 (user/assistant/system)
            content: 消息内容
        """
        text = content.text_content if isinstance(content, MessageChain) else content
        self.messages.append({
            "role": role,
            "content": text
        })
        self.updated_at = datetime.now()

    def to_llm_messages(self) -> list[dict[str, str]]:
        """转换为 LLM 消息格式"""
        return [
            {
                "role": msg["role"],
                "content": msg["content"]
            }
            for msg in self.messages
        ]

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "title": self.title,
            "messages": self.messages,
            "persona_id": self.persona_id,
            "kb_ids": self.kb_ids,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Conversation":
        """从字典创建"""
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now()
        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now()

        return cls(
            conversation_id=data["conversation_id"],
            session_id=data["session_id"],
            title=data["title"],
            messages=data.get("messages", []),
            persona_id=data.get("persona_id"),
            kb_ids=data.get("kb_ids", []),
            metadata=data.get("metadata", {}),
            created_at=created_at,
            updated_at=updated_at,
        )


@dataclass
class Session:
    """会话

    表示一个对话窗口（如群聊、私聊）
    一个会话可以有多个对话
    """
    session_id: str  # unified_id
    platform_id: str
    channel_id: str
    user_id: str
    current_conversation_id: str | None = None
    conversation_ids: list[str] = field(default_factory=list)  # 会话的所有对话ID列表
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def unified_id(self) -> str:
        """统一 ID"""
        return f"{self.platform_id}:{self.channel_id}:{self.user_id}"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "platform_id": self.platform_id,
            "channel_id": self.channel_id,
            "user_id": self.user_id,
            "current_conversation_id": self.current_conversation_id,
            "conversation_ids": self.conversation_ids,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        """从字典创建"""
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now()

        return cls(
            session_id=data["session_id"],
            platform_id=data["platform_id"],
            channel_id=data["channel_id"],
            user_id=data["user_id"],
            current_conversation_id=data.get("current_conversation_id"),
            conversation_ids=data.get("conversation_ids", []),
            metadata=data.get("metadata", {}),
            created_at=created_at,
        )


# ============== 会话管理器 ==============

SessionDeletedCallback = Callable[[str], Awaitable[None]]


class ConversationManager:
    """会话管理器

    负责管理会话和对话
    """

    def __init__(self, storage_path: str | None = None):
        """初始化会话管理器

        Args:
            storage_path: 存储路径，默认为 data/conversations/
        """
        self._sessions: dict[str, Session] = {}
        self._conversations: dict[str, Conversation] = {}
        self._on_session_deleted_callbacks: list[SessionDeletedCallback] = []
        self._session_services: dict[str, dict] = {}

        # 存储路径
        if storage_path is None:
            storage_path = "data/conversations"
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._sessions_file = self.storage_path / "sessions.json"
        self._conversations_dir = self.storage_path / "conversations"
        self._session_services_dir = self.storage_path / "session_services"
        self._session_services_dir.mkdir(exist_ok=True)

    async def load(self) -> None:
        """加载会话和对话数据"""
        await self._load_sessions()
        await self._load_conversations()
        await self._load_session_services()

    async def save(self) -> None:
        """保存会话和对话数据"""
        await self._save_sessions()
        await self._save_conversations()
        await self._save_session_services()

    # ============== 会话服务管理 ==============

    async def _load_session_services(self) -> None:
        """加载会话服务配置"""
        for file_path in self._session_services_dir.glob("*.json"):
            try:
                content = await self._read_file_async(file_path)
                data = json.loads(content)

                session_id = data.get("session_id")
                if session_id:
                    self._session_services[session_id] = data
            except Exception as e:
                logger.error(f"Failed to load session services {file_path}: {e}")

        logger.info(f"Loaded {len(self._session_services)} session service configs")

    async def _save_session_services(self) -> None:
        """保存会话服务配置"""
        for session_id, services_config in self._session_services.items():
            try:
                content = json.dumps(services_config, indent=2, ensure_ascii=False)
                file_path = self._session_services_dir / f"{session_id}.json"
                await self._write_file_async(file_path, content)
            except Exception as e:
                logger.error(f"Failed to save session services {session_id}: {e}")

    # ============== 会话服务管理方法 ==============

    async def get_session_services(self, session_id: str) -> dict:
        """获取会话服务配置

        Args:
            session_id: 会话 ID

        Returns:
            会话服务配置
        """
        if session_id not in self._session_services:
            # 如果没有配置，返回默认配置
            return {
                "llm_enabled": True,
                "tts_enabled": True,
                "session_enabled": True,
            }

        return self._session_services[session_id]

    async def set_llm_status(self, session_id: str, enabled: bool) -> None:
        """设置会话的 LLM 状态

        Args:
            session_id: 会话 ID
            enabled: True 表示启用，False 表示禁用
        """
        services = await self.get_session_services(session_id)
        services["llm_enabled"] = enabled

        self._session_services[session_id] = services
        await self._save_session_services()

        logger.info(
            f"会话 {session_id} 的 LLM 状态已更新为: {'启用' if enabled else '禁用'}"
        )

    async def set_tts_status(self, session_id: str, enabled: bool) -> None:
        """设置会话的 TTS 状态

        Args:
            session_id: 会话 ID
            enabled: True 表示启用，False 表示禁用
        """
        services = await self.get_session_services(session_id)
        services["tts_enabled"] = enabled

        self._session_services[session_id] = services
        await self._save_session_services()

        logger.info(
            f"会话 {session_id} 的 TTS 状态已更新为: {'启用' if enabled else '禁用'}"
        )

    async def is_llm_enabled(self, session_id: str) -> bool:
        """检查会话的 LLM 是否启用

        Args:
            session_id: 会话 ID

        Returns:
            True 表示启用，False 表示禁用
        """
        services = await self.get_session_services(session_id)
        return services.get("llm_enabled", True)

    async def is_tts_enabled(self, session_id: str) -> bool:
        """检查会话的 TTS 是否启用

        Args:
            session_id: 会话 ID

        Returns:
            True 表示启用，False 表示禁用
        """
        services = await self.get_session_services(session_id)
        return services.get("tts_enabled", True)

    async def is_session_enabled(self, session_id: str) -> bool:
        """检查会话是否整体启用

        Args:
            session_id: 会话 ID

        Returns:
            True 表示启用，False 表示禁用
        """
        services = await self.get_session_services(session_id)
        return services.get("session_enabled", True)

    async def set_session_enabled(self, session_id: str, enabled: bool) -> None:
        """设置会话整体状态

        Args:
            session_id: 会话 ID
            enabled: True 表示启用，False 表示禁用
        """
        services = await self.get_session_services(session_id)
        services["session_enabled"] = enabled

        self._session_services[session_id] = services
        await self._save_session_services()

        logger.info(
            f"会话 {session_id} 的整体状态已更新为: {'启用' if enabled else '禁用'}"
        )

    # ============== 原有方法 ==============

    async def _load_sessions(self) -> None:
        """加载会话数据"""
        if not self._sessions_file.exists():
            return

        try:
            content = await self._read_file_async(self._sessions_file)
            data = json.loads(content)

            for session_data in data:
                session = Session.from_dict(session_data)
                self._sessions[session.session_id] = session

            logger.info(f"Loaded {len(self._sessions)} sessions")

        except Exception as e:
            logger.error(f"Failed to load sessions: {e}")

    async def _save_sessions(self) -> None:
        """保存会话数据"""
        try:
            data = [s.to_dict() for s in self._sessions.values()]
            content = json.dumps(data, indent=2, ensure_ascii=False)
            await self._write_file_async(self._sessions_file, content)
        except Exception as e:
            logger.error(f"Failed to save sessions: {e}")

    async def _load_conversations(self) -> None:
        """加载对话数据"""
        for file_path in self._conversations_dir.glob("*.json"):
            try:
                content = await self._read_file_async(file_path)
                data = json.loads(content)

                conv = Conversation.from_dict(data)
                self._conversations[conv.conversation_id] = conv

            except Exception as e:
                logger.error(f"Failed to load conversation {file_path}: {e}")

        logger.info(f"Loaded {len(self._conversations)} conversations")

    async def _save_conversations(self) -> None:
        """保存对话数据"""
        # 清空现有文件
        for file_path in self._conversations_dir.glob("*.json"):
            try:
                file_path.unlink()
            except Exception:
                pass

        # 保存所有对话
        for conv in self._conversations.values():
            try:
                content = json.dumps(conv.to_dict(), indent=2, ensure_ascii=False)
                file_path = self._conversations_dir / f"{conv.conversation_id}.json"
                await self._write_file_async(file_path, content)
            except Exception as e:
                logger.error(f"Failed to save conversation {conv.conversation_id}: {e}")

    async def _read_file_async(self, file_path: Path) -> str:
        """异步读取文件"""
        import asyncio
        return await asyncio.to_thread(file_path.read_text, encoding="utf-8")

    async def _write_file_async(self, file_path: Path, content: str) -> None:
        """异步写入文件"""
        import asyncio
        await asyncio.to_thread(file_path.write_text, content, encoding="utf-8")

    def register_on_session_deleted(self, callback: SessionDeletedCallback) -> None:
        """注册会话删除回调"""
        self._on_session_deleted_callbacks.append(callback)

    async def _trigger_session_deleted(self, session_id: str) -> None:
        """触发会话删除回调"""
        for callback in self._on_session_deleted_callbacks:
            try:
                await callback(session_id)
            except Exception as e:
                logger.error(f"Session deleted callback error: {e}")

    def get_or_create_session(self, session_id: str, platform_id: str, channel_id: str, user_id: str) -> Session:
        """获取或创建会话"""

        if session_id not in self._sessions:
            self._sessions[session_id] = Session(
                session_id=session_id,
                platform_id=platform_id,
                channel_id=channel_id,
                user_id=user_id
            )

            # 创建默认服务配置
            self._session_services[session_id] = {
                "llm_enabled": True,
                "tts_enabled": True,
                "session_enabled": True,
            }

        return self._sessions[session_id]

    async def new_conversation(
        self,
        session_id: str,
        title: str | None = None,
        persona_id: str | None = None
    ) -> Conversation:
        """创建新对话

        Args:
            session_id: 会话 ID
            title: 对话标题
            persona_id: 人设 ID

        Returns:
            新创建的对话
        """
        conv = Conversation(
            conversation_id=uuid.uuid4().hex[:16],
            session_id=session_id,
            title=title or "新对话",
            persona_id=persona_id
        )

        self._conversations[conv.conversation_id] = conv

        # 确保会话存在，不存在则创建
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(
                session_id=session_id,
                platform_id="",  # 从 session_id 解析
                channel_id="",
                user_id=""
            )

        # 添加到会话的对话列表
        session = self._sessions[session_id]
        if conv.conversation_id not in session.conversation_ids:
            session.conversation_ids.append(conv.conversation_id)

        # 设置为当前对话
        session.current_conversation_id = conv.conversation_id

        # 自动保存
        await self._save_conversations()
        await self._save_sessions()

        logger.info(f"Created new conversation: {conv.conversation_id} for session: {session_id}")
        return conv

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """获取对话"""
        return self._conversations.get(conversation_id)

    def get_session(self, session_id: str) -> Session | None:
        """获取会话"""
        return self._sessions.get(session_id)

    def get_current_conversation(self, session_id: str) -> Conversation | None:
        """获取当前对话"""
        session = self._sessions.get(session_id)
        if not session or not session.current_conversation_id:
            return None
        return self._conversations.get(session.current_conversation_id)

    def list_conversations(self, session_id: str) -> list[Conversation]:
        """列出会话的所有对话"""
        return [
            conv for conv in self._conversations.values()
            if conv.session_id == session_id
        ]

    def create_conversation(
        self,
        session_id: str,
        title: str | None = None,
        persona_id: str | None = None,
        kb_ids: list[str] | None = None,
    ) -> Conversation:
        """创建对话（同步版本，用于兼容）"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果在异步上下文中，创建任务
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(
                        asyncio.run,
                        self.new_conversation(session_id, title, persona_id)
                    ).result()
            else:
                return asyncio.run(self.new_conversation(session_id, title, persona_id))
        except Exception:
            # 降级：同步创建
            conv = Conversation(
                conversation_id=uuid.uuid4().hex[:16],
                session_id=session_id,
                title=title or "新对话",
                persona_id=persona_id,
                kb_ids=kb_ids or []
            )

            self._conversations[conv.conversation_id] = conv
            return conv

    def update_conversation(
        self,
        conversation_id: str,
        title: str | None = None,
        persona_id: str | None = None,
        kb_ids: list[str] | None = None,
    ) -> bool:
        """更新对话"""
        conv = self._conversations.get(conversation_id)
        if not conv:
            return False

        if title is not None:
            conv.title = title
        if persona_id is not None:
            conv.persona_id = persona_id
        if kb_ids is not None:
            conv.kb_ids = kb_ids

        conv.updated_at = datetime.now()

        # 异步保存（不等待）
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._save_conversations())
            else:
                asyncio.run(self._save_conversations())
        except Exception:
            pass

        return True

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> bool:
        """添加消息到对话"""
        conv = self._conversations.get(conversation_id)
        if not conv:
            return False

        conv.add_message(role, content)

        # 异步保存（不等待）
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._save_conversations())
            else:
                asyncio.run(self._save_conversations())
        except Exception:
            pass

        return True

    async def switch_conversation(
        self,
        session_id: str,
        conversation_id: str
    ) -> bool:
        """切换对话

        Args:
            session_id: 会话 ID
            conversation_id: 目标对话 ID

        Returns:
            是否切换成功
        """
        if session_id not in self._sessions:
            return False
        if conversation_id not in self._conversations:
            return False

        self._sessions[session_id].current_conversation_id = conversation_id
        await self._save_sessions()

        logger.info(f"Switched to conversation: {conversation_id} for session: {session_id}")
        return True

    async def delete_conversation(self, conversation_id: str) -> bool:
        """删除对话

        Args:
            conversation_id: 对话 ID

        Returns:
            是否删除成功
        """
        if conversation_id not in self._conversations:
            return False

        conv = self._conversations.pop(conversation_id)
        session_id = conv.session_id

        # 从会话的对话列表中移除
        if session_id in self._sessions:
            session = self._sessions[session_id]
            if conversation_id in session.conversation_ids:
                session.conversation_ids.remove(conversation_id)

        # 如果是当前对话，清除引用或切换到其他对话
        if session.current_conversation_id == conversation_id:
            # 尝试切换到其他对话
            if session.conversation_ids:
                session.current_conversation_id = session.conversation_ids[-1]
            else:
                session.current_conversation_id = None

        # 保存变更
        await self._save_sessions()
        await self._save_conversations()

        logger.info(f"Deleted conversation: {conversation_id}")
        return True

    async def delete_session(self, session_id: str) -> bool:
        """删除会话

        Args:
            session_id: 会话 ID

        Returns:
            是否删除成功
        """
        if session_id not in self._sessions:
            return False

        # 删除会话的所有对话
        conv_ids_to_delete = [
            conv_id for conv_id, conv in self._conversations.items()
            if conv.session_id == session_id
        ]
        for conv_id in conv_ids_to_delete:
            await self.delete_conversation(conv_id)

        # 删除会话
        del self._sessions[session_id]

        # 删除服务配置
        if session_id in self._session_services:
            del self._session_services[session_id]

        # 触发回调
        await self._trigger_session_deleted(session_id)

        # 保存变更
        await self._save_sessions()
        await self._save_session_services()

        logger.info(f"Deleted session: {session_id}")
        return True


# ============== 导出 ==============

__all__ = [
    "Conversation",
    "Session",
    "ConversationManager",
    "SessionDeletedCallback",
]
