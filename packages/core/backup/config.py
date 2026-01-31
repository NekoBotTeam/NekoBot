"""备份配置管理器

使用装饰器定义备份项，提供灵活的备份配置
"""

from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any, Optional
from functools import wraps


@dataclass
class BackupItem:
    """备份项"""

    name: str
    """备份项名称"""

    description: str
    """描述"""

    enabled: bool = True
    """是否启用"""

    priority: int = 0
    """优先级（数字越小优先级越高）"""

    export_func: Optional[Callable] = None
    """导出函数"""

    import_func: Optional[Callable] = None
    """导入函数"""

    metadata: dict = field(default_factory=dict)
    """元数据"""


class BackupRegistry:
    """备份注册表"""

    _items: dict[str, BackupItem] = {}

    @classmethod
    def register(cls, name: str, description: str = "", priority: int = 0):
        """注册备份项装饰器

        Args:
            name: 备份项名称
            description: 描述
            priority: 优先级

        Returns:
            装饰器函数

        Example:
            @BackupRegistry.register("main_database", "主数据库", priority=10)
            async def export_main_db(backup_dir, context):
                pass
        """

        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

            item = BackupItem(
                name=name,
                description=description,
                priority=priority,
            )

            func_name = func.__name__
            if func_name.startswith("export_"):
                item.export_func = wrapper
            elif func_name.startswith("import_"):
                item.import_func = wrapper

            cls._items[name] = item
            return wrapper

        return decorator

    @classmethod
    def get_item(cls, name: str) -> Optional[BackupItem]:
        """获取备份项

        Args:
            name: 备份项名称

        Returns:
            备份项，不存在则返回None
        """
        return cls._items.get(name)

    @classmethod
    def get_all_items(cls) -> list[BackupItem]:
        """获取所有备份项（按优先级排序）

        Returns:
            备份项列表
        """
        return sorted(cls._items.values(), key=lambda x: x.priority)

    @classmethod
    def get_enabled_items(cls) -> list[BackupItem]:
        """获取所有启用的备份项（按优先级排序）

        Returns:
            启用的备份项列表
        """
        return sorted(
            [item for item in cls._items.values() if item.enabled],
            key=lambda x: x.priority,
        )

    @classmethod
    def enable_item(cls, name: str) -> bool:
        """启用备份项

        Args:
            name: 备份项名称

        Returns:
            是否成功启用
        """
        item = cls._items.get(name)
        if item:
            item.enabled = True
            return True
        return False

    @classmethod
    def disable_item(cls, name: str) -> bool:
        """禁用备份项

        Args:
            name: 备份项名称

        Returns:
            是否成功禁用
        """
        item = cls._items.get(name)
        if item:
            item.enabled = False
            return True
        return False

    @classmethod
    def clear(cls) -> None:
        """清空所有备份项"""
        cls._items.clear()


@dataclass
class BackupContext:
    """备份上下文

    传递给导出/导入函数的上下文信息
    """

    backup_dir: Any
    """备份目录"""

    path_manager: Any
    """路径管理器"""

    progress_callback: Optional[Callable] = None
    """进度回调函数"""

    metadata: dict = field(default_factory=dict)
    """元数据"""


class BackupExecutor:
    """备份执行器

    执行注册的备份项
    """

    def __init__(self, context: BackupContext):
        """初始化执行器

        Args:
            context: 备份上下文
        """
        self.context = context

    async def export(self, items: Optional[list[str]] = None) -> dict[str, Any]:
        """执行导出

        Args:
            items: 要导出的备份项列表，None表示导出所有启用的项

        Returns:
            导出结果统计 {item_name: success}
        """
        results = {}

        backup_items = items or [
            item.name for item in BackupRegistry.get_enabled_items()
        ]

        for item_name in backup_items:
            item = BackupRegistry.get_item(item_name)
            if not item or not item.enabled:
                results[item_name] = False
                continue

            try:
                if self.context.progress_callback:
                    await self.context.progress_callback(
                        f"export_{item_name}",
                        0,
                        100,
                        f"开始导出 {item.description}...",
                    )

                if item.export_func:
                    await item.export_func(self.context.backup_dir, self.context)
                    results[item_name] = True

                    if self.context.progress_callback:
                        await self.context.progress_callback(
                            f"export_{item_name}",
                            100,
                            100,
                            f"{item.description} 导出完成",
                        )
                else:
                    results[item_name] = False

            except Exception as e:
                from loguru import logger

                logger.error(f"导出 {item_name} 失败: {e}")
                results[item_name] = False

        return results

    async def import_backup(
        self, items: Optional[list[str]] = None, force: bool = False
    ) -> dict[str, Any]:
        """执行导入

        Args:
            items: 要导入的备份项列表，None表示导入所有启用的项
            force: 是否强制导入

        Returns:
            导入结果统计 {item_name: success}
        """
        results = {}

        backup_items = items or [
            item.name for item in BackupRegistry.get_enabled_items()
        ]

        for item_name in backup_items:
            item = BackupRegistry.get_item(item_name)
            if not item or not item.enabled:
                results[item_name] = False
                continue

            try:
                if self.context.progress_callback:
                    await self.context.progress_callback(
                        f"import_{item_name}",
                        0,
                        100,
                        f"开始导入 {item.description}...",
                    )

                if item.import_func:
                    await item.import_func(self.context.backup_dir, self.context)
                    results[item_name] = True

                    if self.context.progress_callback:
                        await self.context.progress_callback(
                            f"import_{item_name}",
                            100,
                            100,
                            f"{item.description} 导入完成",
                        )
                else:
                    results[item_name] = False

            except Exception as e:
                from loguru import logger

                logger.error(f"导入 {item_name} 失败: {e}")
                results[item_name] = False

        return results


__all__ = [
    "BackupItem",
    "BackupRegistry",
    "BackupContext",
    "BackupExecutor",
]
