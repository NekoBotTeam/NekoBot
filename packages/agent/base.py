"""智能代理基础模块

提供 Agent 的基础功能，包括工具注册、调用等
"""

import time
from typing import Dict, Any, Callable, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger


class ToolCategory(Enum):
    """工具类别"""
    SYSTEM = "system"
    SEARCH = "search"
    FILE = "file"
    NETWORK = "network"


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    category: ToolCategory
    description: str
    function: Callable
    parameters: Dict[str, Any] = None
    enabled: bool = True
    requires_permission: bool = False
    permission_level: str = "user"


@dataclass
class ToolCall:
    """工具调用"""
    tool_name: str
    parameters: Dict[str, Any] = None
    result: Any = None
    success: bool = False
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None


class ToolRegistry:
    """工具注册表"""

    def __init__(self) -> None:
        self.tools: Dict[str, ToolDefinition] = {}

    def register_tool(self, tool: ToolDefinition) -> None:
        """注册工具

        Args:
            tool: 工具定义
        """
        if tool.name in self.tools:
            logger.warning(f"工具 {tool.name} 已存在，将被覆盖")
        self.tools[tool.name] = tool
        else:
            self.tools[tool.name] = tool
            logger.debug(f"注册工具 {tool.name}")

    def unregister_tool(self, tool_name: str) -> None:
        """注销工具

        Args:
            tool_name: 工具名称
        """
        if tool_name in self.tools:
            del self.tools[tool.name]
            logger.debug(f"注销工具 {tool.name}")
        else:
            logger.warning(f"工具 {tool.name} 不存在")

    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        """获取工具

        Args:
            tool_name: 工具名称

        Returns:
            工具定义，不存在返回 None
        """
        return self.tools.get(tool_name)

    def list_tools(self, category: Optional[ToolCategory] = None) -> List[ToolDefinition]:
        """列出所有工具

        Args:
            category: 工具类别（可选）

        Returns:
            工具列表
        """
        tools = list(self.tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools

    def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolCall:
        """调用工具

        Args:
            tool_name: 工具名称
            parameters: 参数字典

        Returns:
            工具调用结果
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolCall(
                tool_name=tool_name,
                parameters=parameters,
                result=None,
                success=False,
                error=f"工具 {tool_name} 不存在"
            )

        if not tool.enabled:
            return ToolCall(
                tool_name=tool_name,
                parameters=parameters,
                result=None,
                success=False,
                error=f"工具 {tool_name} 未启用"
            )

        if tool.requires_permission and not self._check_permission(tool.permission_level, None):
            return ToolCall(
                tool_name=tool_name,
                parameters=parameters,
                result=None,
                success=False,
                error=f"需要 {tool.permission_level} 权限级别"
            )

        try:
            import time
            start_time = time.time()
            result = tool.function(**parameters)
            end_time = time.time()
            
            return ToolCall(
                tool_name=tool_name,
                parameters=parameters,
                result=result,
                success=True,
                error=None,
                start_time=start_time,
                end_time=end_time
            )
        except Exception as e:
            logger.error(f"调用工具 {tool_name} 失败: {e}")
            return ToolCall(
                tool_name=tool_name,
                parameters=parameters,
                result=None,
                success=False,
                error=str(e),
                start_time=time.time(),
                end_time=time.time()
            )

    def _check_permission(self, required_level: str, user_level: Optional[str] = None) -> bool:
        """检查权限

        Args:
            required_level: 需要的权限级别
            user_level: 用户权限级别

        Returns:
            是否有权限
        """
        # 权限级别从低到高：user < moderator < admin < system
        levels = {
            "user": 0,
            "moderator": 1,
            "admin": 2,
            "system": 3
        }

        if user_level is None:
            # 默认需要 user 级别
            user_level = "user"

        current_level = levels.get(user_level, 0)
        return current_level >= levels.get(required_level, 0)