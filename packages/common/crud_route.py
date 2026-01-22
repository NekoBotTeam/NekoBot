"""CRUD 路由基类

提供通用的 CRUD 操作路由实现，参考 AstrBot 的简洁设计
"""

from typing import Dict, Any, Optional, Callable, List
from loguru import logger
from ..routes.route import Route, Response, RouteContext


class CRUDRoute(Route):
    """通用 CRUD 路由基类

    提供标准的列表、创建、更新、删除操作的通用实现
    子类只需配置数据库操作函数和字段映射
    """

    def __init__(self, context: RouteContext):
        super().__init__(context)
        self.setup_crud_routes()

    def setup_crud_routes(self):
        """设置 CRUD 路由

        子类可以重写此方法来自定义路由
        """
        item_name = self.get_item_name()
        self.routes = [
            (f"/api/{item_name}s/list", "GET", self.generic_list),
            (f"/api/{item_name}s/create", "POST", self.generic_create),
            (f"/api/{item_name}s/update", "POST", self.generic_update),
            (f"/api/{item_name}s/delete", "POST", self.generic_delete),
        ]

    def get_item_name(self) -> str:
        """获取项目名称，用于路由和消息

        子类必须重写此方法

        Returns:
            项目名称（如 "system_prompt", "tool_prompt"）
        """
        raise NotImplementedError("子类必须实现 get_item_name 方法")

    def get_create_fields(self) -> List[str]:
        """获取创建时必填字段

        子类可以重写此方法

        Returns:
            必填字段列表
        """
        return ["name"]

    def get_list_func(self) -> Callable:
        """获取列表查询函数

        子类必须重写此方法

        Returns:
            查询函数
        """
        raise NotImplementedError("子类必须实现 get_list_func 方法")

    def get_create_func(self) -> Callable:
        """获取创建函数

        子类必须重写此方法

        Returns:
            创建函数
        """
        raise NotImplementedError("子类必须实现 get_create_func 方法")

    def get_update_func(self) -> Callable:
        """获取更新函数

        子类必须重写此方法

        Returns:
            更新函数
        """
        raise NotImplementedError("子类必须实现 get_update_func 方法")

    def get_delete_func(self) -> Callable:
        """获取删除函数

        子类必须重写此方法

        Returns:
            删除函数
        """
        raise NotImplementedError("子类必须实现 get_delete_func 方法")

    def get_name_key(self) -> str:
        """获取名称字段键

        子类可以重写此方法（默认为 "name"）

        Returns:
            名称字段键
        """
        return "name"

    def get_id_key(self) -> str:
        """获取 ID 字段键

        子类可以重写此方法（默认为 "name"）

        Returns:
            ID 字段键
        """
        return "name"

    def get_check_exists_func(self) -> Optional[Callable]:
        """获取检查存在性函数

        子类可以重写此方法

        Returns:
            检查存在性函数，或 None 表示不检查
        """
        return None

    def can_delete_item(self, item_data: Dict[str, Any]) -> bool:
        """检查是否可以删除项目

        子类可以重写此方法（默认为 True）

        Args:
            item_data: 项目数据

        Returns:
            是否可以删除
        """
        return True

    def get_delete_denied_message(self, item_data: Dict[str, Any]) -> str:
        """获取拒绝删除的消息

        子类可以重写此方法

        Args:
            item_data: 项目数据

        Returns:
            拒绝删除的消息
        """
        return "不允许删除该项目"

    def after_operation(self, operation: str, data: Optional[Dict[str, Any]] = None):
        """操作后的回调

        子类可以重写此方法（如重新加载缓存）

        Args:
            operation: 操作类型（create, update, delete）
            data: 操作数据
        """
        pass

    async def generic_list(self) -> Dict[str, Any]:
        """通用列表获取"""
        try:
            item_name = self.get_item_name()
            list_func = self.get_list_func()
            items = list_func()
            return Response().ok(data={f"{item_name}s": items}).to_dict()
        except Exception as e:
            logger.error(f"获取{self.get_item_name()}列表失败: {e}", exc_info=True)
            return (
                Response()
                .error(f"获取{self.get_item_name()}列表失败: {str(e)}")
                .to_dict()
            )

    async def generic_create(self) -> Dict[str, Any]:
        """通用创建方法"""
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("缺少请求数据").to_dict()

            required_fields = self.get_create_fields()
            if required_fields:
                is_valid, error_msg = await self.validate_required_fields(
                    data, required_fields
                )
                if not is_valid:
                    return Response().error(error_msg).to_dict()

            create_func = self.get_create_func()
            name_key = self.get_name_key()
            name = data[name_key]

            success = create_func(**data)
            if not success:
                return Response().error(f"{self.get_item_name()}已存在").to_dict()

            self.after_operation("create", data)

            return (
                Response()
                .ok(data={name_key: name}, message=f"{self.get_item_name()}创建成功")
                .to_dict()
            )
        except Exception as e:
            logger.error(f"创建{self.get_item_name()}失败: {e}", exc_info=True)
            return (
                Response().error(f"创建{self.get_item_name()}失败: {str(e)}").to_dict()
            )

    async def generic_update(self) -> Dict[str, Any]:
        """通用更新方法"""
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("缺少请求数据").to_dict()

            id_key = self.get_id_key()
            item_id = data.get(id_key)
            if not item_id:
                return Response().error(f"缺少{id_key}").to_dict()

            check_func = self.get_check_exists_func()
            if check_func:
                existing = check_func(item_id)
                if not existing:
                    return Response().error(f"{self.get_item_name()}不存在").to_dict()

            update_func = self.get_update_func()
            success = update_func(**data)
            if not success:
                return Response().error(f"{self.get_item_name()}更新失败").to_dict()

            self.after_operation("update", data)

            return Response().ok(message=f"{self.get_item_name()}更新成功").to_dict()
        except Exception as e:
            logger.error(f"更新{self.get_item_name()}失败: {e}", exc_info=True)
            return (
                Response().error(f"更新{self.get_item_name()}失败: {str(e)}").to_dict()
            )

    async def generic_delete(self) -> Dict[str, Any]:
        """通用删除方法"""
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("缺少请求数据").to_dict()

            id_key = self.get_id_key()
            item_id = data.get(id_key)
            if not item_id:
                return Response().error(f"缺少{id_key}").to_dict()

            check_func = self.get_check_exists_func()
            if check_func:
                existing = check_func(item_id)
                if not existing:
                    return Response().error(f"{self.get_item_name()}不存在").to_dict()

                if not self.can_delete_item(existing):
                    return (
                        Response()
                        .error(self.get_delete_denied_message(existing))
                        .to_dict()
                    )

            delete_func = self.get_delete_func()
            success = delete_func(item_id)
            if not success:
                return Response().error(f"{self.get_item_name()}删除失败").to_dict()

            self.after_operation("delete", {"id": item_id})

            return Response().ok(message=f"{self.get_item_name()}删除成功").to_dict()
        except Exception as e:
            logger.error(f"删除{self.get_item_name()}失败: {e}", exc_info=True)
            return (
                Response().error(f"删除{self.get_item_name()}失败: {str(e)}").to_dict()
            )
