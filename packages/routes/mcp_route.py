"""MCP配置API

提供MCP组件的添加、更新、删除等功能
"""

from pathlib import Path
from typing import Dict, Any

from .route import Route, Response, RouteContext
from packages.common import (
    JsonFileHandler,
    get_current_timestamp,
    handle_route_errors,
    CRUDMixin,
)

MCP_PATH = Path(__file__).parent.parent.parent.parent / "data" / "mcp.json"


class McpRoute(Route, CRUDMixin):
    """MCP配置路由"""

    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.json_handler = JsonFileHandler(MCP_PATH.parent)
        self.mcp_filename = MCP_PATH.name
        self.routes = [
            ("/api/mcp/list", "GET", self.get_mcp_list),
            ("/api/mcp/add", "POST", self.add_mcp),
            ("/api/mcp/update", "POST", self.update_mcp),
            ("/api/mcp/delete", "POST", self.delete_mcp),
        ]

    @handle_route_errors("获取MCP列表")
    async def get_mcp_list(self) -> Dict[str, Any]:
        """获取MCP列表"""
        mcp_list = self.json_handler.load(self.mcp_filename, default={})
        mcp_items = list(mcp_list.values())
        return Response().ok(data={"mcps": mcp_items}).to_dict()

    @handle_route_errors("添加MCP组件")
    async def add_mcp(self) -> Dict[str, Any]:
        """添加MCP组件"""
        data = await self.get_request_data()
        return await self.generic_add(
            data=data,
            required_fields=["name", "type", "config"],
            load_func=lambda: self.json_handler.load(self.mcp_filename, default={}),
            save_func=lambda items: self.json_handler.save(self.mcp_filename, items),
            item_factory=lambda iid, d: {
                "id": iid,
                "name": d["name"],
                "type": d["type"],
                "config": d["config"],
                "enabled": d.get("enabled", True),
                "created_at": get_current_timestamp(),
            },
        )

    @handle_route_errors("更新MCP组件")
    async def update_mcp(self) -> Dict[str, Any]:
        """更新MCP组件"""
        data = await self.get_request_data()
        mcp_id = data.get("id") if data else None

        result = await self.generic_update(
            item_id=mcp_id,
            data=data,
            load_func=lambda: self.json_handler.load(self.mcp_filename, default={}),
            save_func=lambda items: self.json_handler.save(self.mcp_filename, items),
        )

        if result.get("status") == "success":
            return Response().ok(message="MCP更新成功").to_dict()
        return result

    @handle_route_errors("删除MCP组件")
    async def delete_mcp(self) -> Dict[str, Any]:
        """删除MCP组件"""
        data = await self.get_request_data()
        mcp_id = data.get("id") if data else None

        result = await self.generic_delete(
            item_id=mcp_id,
            load_func=lambda: self.json_handler.load(self.mcp_filename, default={}),
            save_func=lambda items: self.json_handler.save(self.mcp_filename, items),
        )

        if result.get("status") == "success":
            return Response().ok(message="MCP删除成功").to_dict()
        return result
