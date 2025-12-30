"""插件数据管理器

提供插件数据目录管理和配置 schema 支持
"""

import json
from pathlib import Path
from typing import Any, Optional, Dict
from loguru import logger
from ..core.database import db_manager


class PluginDataManager:
    """插件数据管理器

    管理插件的数据目录和配置文件
    """

    def __init__(self, base_data_dir: str = "data"):
        """初始化插件数据管理器

        Args:
            base_data_dir: 基础数据目录路径
        """
        self.base_data_dir = Path(base_data_dir)
        self.base_data_dir.mkdir(parents=True, exist_ok=True)

        # 插件数据目录（用户指定使用 plugins_data）
        self.plugins_data_dir = self.base_data_dir / "plugins_data"
        self.plugins_data_dir.mkdir(parents=True, exist_ok=True)

    def get_plugin_data_dir(self, plugin_name: str) -> Path:
        """获取插件的数据目录

        Args:
            plugin_name: 插件名称

        Returns:
            插件数据目录路径
        """
        # 使用 plugins_data 目录下的插件子目录
        data_dir = self.plugins_data_dir / plugin_name
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def get_plugin_data_file(self, plugin_name: str, filename: str) -> Path:
        """获取插件的数据文件路径

        Args:
            plugin_name: 插件名称
            filename: 文件名

        Returns:
            数据文件路径
        """
        data_dir = self.get_plugin_data_dir(plugin_name)
        return data_dir / filename

    def get_plugin_config_file(self, plugin_name: str) -> Path:
        """获取插件的配置文件路径

        Args:
            plugin_name: 插件名称

        Returns:
            配置文件路径
        """
        # 配置文件存储在 plugins_data 目录下，命名为 {plugin_name}_data.json
        config_file = self.plugins_data_dir / f"{plugin_name}_data.json"
        return config_file

    def load_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """加载插件配置

        Args:
            plugin_name: 插件名称

        Returns:
            配置字典
        """
        # 优先从数据库加载配置
        db_config = db_manager.get_plugin_config(plugin_name)
        if db_config is not None:
            return db_config

        # 如果数据库中没有配置，尝试从JSON文件加载（兼容性）
        config_file = self.get_plugin_config_file(plugin_name)
        if not config_file.exists():
            return {}

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                # 将配置保存到数据库
                db_manager.set_plugin_config(plugin_name, config)
                return config
        except Exception as e:
            logger.error(f"加载插件 {plugin_name} 配置失败: {e}")
            return {}

    def save_plugin_config(self, plugin_name: str, config: Dict[str, Any]) -> bool:
        """保存插件配置

        Args:
            plugin_name: 插件名称
            config: 配置字典

        Returns:
            是否保存成功
        """
        # 保存到数据库
        try:
            db_manager.set_plugin_config(plugin_name, config)
        except Exception as e:
            logger.error(f"保存插件 {plugin_name} 配置到数据库失败: {e}")
            return False

        # 同时保存到JSON文件（兼容性）
        config_file = self.get_plugin_config_file(plugin_name)
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"保存插件 {plugin_name} 配置到文件失败: {e}")
            return False

    def delete_plugin_data(self, plugin_name: str) -> bool:
        """删除插件数据目录

        Args:
            plugin_name: 插件名称

        Returns:
            是否删除成功
        """
        deleted = False

        # 删除插件数据目录
        data_dir = self.plugins_data_dir / plugin_name
        if data_dir.exists():
            try:
                import shutil

                shutil.rmtree(data_dir)
                logger.info(f"已删除插件 {plugin_name} 的数据目录")
                deleted = True
            except Exception as e:
                logger.warning(f"删除插件数据目录失败: {e}")

        # 删除插件配置文件
        config_file = self.plugins_data_dir / f"{plugin_name}_data.json"
        if config_file.exists():
            try:
                config_file.unlink()
                logger.info(f"已删除插件 {plugin_name} 的配置文件")
                deleted = True
            except Exception as e:
                logger.warning(f"删除插件配置文件失败: {e}")

        # 删除数据库中的插件配置
        try:
            db_manager.delete_plugin_config(plugin_name)
        except Exception as e:
            logger.warning(f"删除插件配置数据库记录失败: {e}")

        return deleted

    def load_conf_schema(self, plugin_path: Path) -> Optional[Dict[str, Any]]:
        """加载插件的配置 schema

        Args:
            plugin_path: 插件目录路径

        Returns:
            配置 schema 字典，如果不存在则返回 None
        """
        schema_file = plugin_path / "_conf_schema.json"
        if not schema_file.exists():
            return None

        try:
            with open(schema_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载插件配置 schema 失败: {e}")
            return None

    def get_all_plugin_data_dirs(self) -> list[Path]:
        """获取所有插件数据目录

        Returns:
            插件数据目录列表
        """
        if not self.plugins_data_dir.exists():
            return []

        return [d for d in self.plugins_data_dir.iterdir() if d.is_dir()]

    def get_plugin_data_size(self, plugin_name: str) -> int:
        """获取插件数据目录大小

        Args:
            plugin_name: 插件名称

        Returns:
            数据目录大小（字节）
        """
        data_dir = self.get_plugin_data_dir(plugin_name)
        if not data_dir.exists():
            return 0

        total_size = 0
        for item in data_dir.rglob("*"):
            if item.is_file():
                total_size += item.stat().st_size
            elif item.is_dir():
                for sub_item in item.rglob("*"):
                    if sub_item.is_file():
                        total_size += sub_item.stat().st_size

        return total_size


# 创建全局插件数据管理器实例
plugin_data_manager = PluginDataManager()
