"""CRUD 操作混入类

提供通用的 CRUD（增删改查）操作方法。
"""

from typing import Callable, Dict, Any, Optional
from loguru import logger


class CRUDMixin:
    """CRUD 操作混入类"""

    async def generic_add(
        self,
        data: Dict[str, Any],
        required_fields: list[str],
        load_func: Callable,
        save_func: Callable,
        item_factory: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """通用的添加方法

        Args:
            data: 请求数据
            required_fields: 必填字段列表
            load_func: 加载数据的函数
            save_func: 保存数据的函数
            item_factory: 创建数据项的工厂函数

        Returns:
            操作结果
        """
        try:
            from packages.common import generate_uuid, get_current_timestamp

            if not data:
                return self.response.error("缺少请求数据").to_dict()

            is_valid, error_msg = await self.validate_required_fields(
                data, required_fields
            )
            if not is_valid:
                return self.response.error(error_msg).to_dict()

            items = load_func()
            item_id = generate_uuid()

            if item_factory:
                item = item_factory(item_id, data)
            else:
                item = {
                    "id": item_id,
                    **data,
                    "created_at": get_current_timestamp(),
                    "updated_at": get_current_timestamp(),
                }

            items[item_id] = item
            save_func(items)

            return self.response.ok(data={"id": item_id}).to_dict()
        except Exception as e:
            logger.error(f"添加失败: {e}")
            return self.response.error(f"添加失败: {str(e)}").to_dict()

    async def generic_update(
        self,
        item_id: str,
        data: Dict[str, Any],
        load_func: Callable,
        save_func: Callable,
    ) -> Dict[str, Any]:
        """通用的更新方法

        Args:
            item_id: 数据项 ID
            data: 更新数据
            load_func: 加载数据的函数
            save_func: 保存数据的函数

        Returns:
            操作结果
        """
        try:
            from packages.common import get_current_timestamp

            if not item_id:
                return self.response.error("缺少 ID").to_dict()

            if not data:
                return self.response.error("缺少更新数据").to_dict()

            items = load_func()

            if item_id not in items:
                return self.response.error("数据项不存在").to_dict()

            items[item_id].update(data)
            items[item_id]["updated_at"] = get_current_timestamp()

            save_func(items)

            return self.response.ok(message="更新成功").to_dict()
        except Exception as e:
            logger.error(f"更新失败: {e}")
            return self.response.error(f"更新失败: {str(e)}").to_dict()

    async def generic_delete(
        self,
        item_id: str,
        load_func: Callable,
        save_func: Callable,
    ) -> Dict[str, Any]:
        """通用的删除方法

        Args:
            item_id: 数据项 ID
            load_func: 加载数据的函数
            save_func: 保存数据的函数

        Returns:
            操作结果
        """
        try:
            if not item_id:
                return self.response.error("缺少 ID").to_dict()

            items = load_func()

            if item_id not in items:
                return self.response.error("数据项不存在").to_dict()

            del items[item_id]
            save_func(items)

            return self.response.ok(message="删除成功").to_dict()
        except Exception as e:
            logger.error(f"删除失败: {e}")
            return self.response.error(f"删除失败: {str(e)}").to_dict()

    async def generic_get(
        self,
        item_id: str,
        load_func: Callable,
    ) -> Dict[str, Any]:
        """通用的获取单个数据项方法

        Args:
            item_id: 数据项 ID
            load_func: 加载数据的函数

        Returns:
            操作结果
        """
        try:
            if not item_id:
                return self.response.error("缺少 ID").to_dict()

            items = load_func()

            if item_id not in items:
                return self.response.error("数据项不存在").to_dict()

            return self.response.ok(data=items[item_id]).to_dict()
        except Exception as e:
            logger.error(f"获取失败: {e}")
            return self.response.error(f"获取失败: {str(e)}").to_dict()

    async def generic_list(
        self,
        load_func: Callable,
        transform_func: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """通用的列表获取方法

        Args:
            load_func: 加载数据的函数
            transform_func: 转换数据的函数

        Returns:
            操作结果
        """
        try:
            items = load_func()

            if transform_func:
                items = [transform_func(item) for item in items.values()]
            else:
                items = list(items.values())

            return self.response.ok(data=items).to_dict()
        except Exception as e:
            logger.error(f"获取列表失败: {e}")
            return self.response.error(f"获取列表失败: {str(e)}").to_dict()
