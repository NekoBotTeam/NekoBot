"""系统提示词API

提供系统提示词的创建、更新、删除等功能
"""

from typing import Dict, Any

from ..common.crud_route import CRUDRoute
from ..core.database import db_manager
from ..core.prompt_manager import prompt_manager


class SystemPromptRoute(CRUDRoute):
    """系统提示词管理路由"""

    def get_item_name(self) -> str:
        """获取项目名称"""
        return "system_prompt"

    def get_create_fields(self) -> list[str]:
        """获取创建时必填字段"""
        return ["name", "prompt"]

    def get_list_func(self):
        """获取列表查询函数"""
        return db_manager.get_all_system_prompts

    def get_create_func(self):
        """获取创建函数"""
        return db_manager.create_system_prompt

    def get_update_func(self):
        """获取更新函数"""
        return db_manager.update_system_prompt

    def get_delete_func(self):
        """获取删除函数"""
        return db_manager.delete_system_prompt

    def get_name_key(self) -> str:
        """获取名称字段键"""
        return "name"

    def get_id_key(self) -> str:
        """获取 ID 字段键"""
        return "name"

    def get_check_exists_func(self):
        """获取检查存在性函数"""
        return db_manager.get_system_prompt

    def can_delete_item(self, item_data: Dict[str, Any]) -> bool:
        """检查是否可以删除项目"""
        name = item_data.get("name", "")
        return name != "default"

    def get_delete_denied_message(self, item_data: Dict[str, Any]) -> str:
        """获取拒绝删除的消息"""
        return "不能删除默认系统提示词"

    def after_operation(self, operation: str, data: Any = None):
        """操作后的回调：重新加载提示词"""
        prompt_manager.load_all_prompts()
