from __future__ import annotations

from typing import Any


class NotimplementedManager:
    """占位管理器：对应功能尚未在 NekoBot 核心实现，所有操作返回 501。"""

    feature_name: str = "this feature"

    def list(self) -> list[dict[str, Any]]:
        return []

    async def unsupported(self) -> None:
        raise NotImplementedError(f"{self.feature_name} is not implemented yet")


class McpManager(NotimplementedManager):
    feature_name = "MCP server management"


class KnowledgeManager(NotimplementedManager):
    feature_name = "knowledge base"
