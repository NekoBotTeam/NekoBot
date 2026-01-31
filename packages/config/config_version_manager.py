"""配置版本控制模块

提供配置变更历史记录、配置回滚能力、配置比较和差异展示。
"""

import json
import os
from typing import Dict, Any, Optional, List
from loguru import logger
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
from difflib import SequenceMatcher


class ConfigChangeType(Enum):
    """配置变更类型"""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ROLLBACK = "rollback"


@dataclass
class ConfigVersion:
    """配置版本"""

    version_id: str
    config: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    change_type: ConfigChangeType = ConfigChangeType.UPDATE
    description: str = ""
    author: str = "system"
    parent_version: Optional[str] = None
    checksum: str = ""

    def __post_init__(self):
        if not self.checksum:
            self.checksum = self._calculate_checksum()

    def _calculate_checksum(self) -> str:
        """计算配置校验和"""
        config_str = json.dumps(self.config, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()


class ConfigVersionManager:
    """配置版本管理器

    提供以下功能：
    - 配置变更历史记录
    - 配置回滚能力
    - 配置比较和差异展示
    """

    def __init__(
        self,
        max_versions: int = 50,
        storage_path: str = "data/config_versions",
        auto_save: bool = True,
    ):
        self.max_versions = max_versions
        self.storage_path = storage_path
        self.auto_save = auto_save

        self._versions: Dict[str, ConfigVersion] = {}
        self._current_version_id: Optional[str] = None
        self._config_history: List[str] = []

        if self.auto_save:
            self._ensure_storage_dir()
            self._load_from_disk()

    def _ensure_storage_dir(self):
        """确保存储目录存在"""
        os.makedirs(self.storage_path, exist_ok=True)

    def create_version(
        self,
        config: Dict[str, Any],
        change_type: ConfigChangeType = ConfigChangeType.UPDATE,
        description: str = "",
        author: str = "system",
    ) -> ConfigVersion:
        """创建新版本

        Args:
            config: 配置内容
            change_type: 变更类型
            description: 描述
            author: 作者

        Returns:
            新创建的配置版本
        """
        version_id = f"v{datetime.now().strftime('%Y%m%d%H%M%S')}"

        version = ConfigVersion(
            version_id=version_id,
            config=config.copy(),
            change_type=change_type,
            description=description,
            author=author,
            parent_version=self._current_version_id,
        )

        self._versions[version_id] = version
        self._config_history.append(version_id)
        self._current_version_id = version_id

        # 限制版本数量
        if len(self._config_history) > self.max_versions:
            old_version_id = self._config_history.pop(0)
            del self._versions[old_version_id]

        if self.auto_save:
            self._save_to_disk()

        logger.info(f"创建配置版本: {version_id} ({change_type.value}) - {description}")

        return version

    def get_version(self, version_id: str) -> Optional[ConfigVersion]:
        """获取指定版本

        Args:
            version_id: 版本ID

        Returns:
            配置版本
        """
        return self._versions.get(version_id)

    def get_current_version(self) -> Optional[ConfigVersion]:
        """获取当前版本"""
        if self._current_version_id:
            return self._versions.get(self._current_version_id)
        return None

    def list_versions(
        self,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """列出所有版本

        Args:
            limit: 返回数量限制

        Returns:
            版本列表
        """
        versions = []
        for version_id in reversed(self._config_history):
            version = self._versions[version_id]
            versions.append(
                {
                    "version_id": version.version_id,
                    "timestamp": version.timestamp.isoformat(),
                    "change_type": version.change_type.value,
                    "description": version.description,
                    "author": version.author,
                    "checksum": version.checksum,
                    "is_current": version_id == self._current_version_id,
                    "parent_version": version.parent_version,
                }
            )

            if limit and len(versions) >= limit:
                break

        return versions

    def rollback_to_version(
        self,
        version_id: str,
        description: str = "",
        author: str = "system",
    ) -> Optional[ConfigVersion]:
        """回滚到指定版本

        Args:
            version_id: 版本ID
            description: 描述
            author: 作者

        Returns:
            新创建的版本
        """
        target_version = self._versions.get(version_id)
        if not target_version:
            logger.error(f"版本 {version_id} 不存在")
            return None

        new_version = self.create_version(
            config=target_version.config,
            change_type=ConfigChangeType.ROLLBACK,
            description=description or f"回滚到 {version_id}",
            author=author,
        )

        logger.info(f"已回滚到版本 {version_id}")
        return new_version

    def compare_versions(
        self,
        version_id1: str,
        version_id2: str,
    ) -> Dict[str, Any]:
        """比较两个版本的差异

        Args:
            version_id1: 第一个版本ID
            version_id2: 第二个版本ID

        Returns:
            差异信息
        """
        version1 = self._versions.get(version_id1)
        version2 = self._versions.get(version_id2)

        if not version1 or not version2:
            return {
                "error": "一个或两个版本不存在",
            }

        diff = self._diff_configs(version1.config, version2.config)

        similarity = self._calculate_similarity(version1.config, version2.config)

        return {
            "version1": {
                "version_id": version1.version_id,
                "timestamp": version1.timestamp.isoformat(),
                "checksum": version1.checksum,
            },
            "version2": {
                "version_id": version2.version_id,
                "timestamp": version2.timestamp.isoformat(),
                "checksum": version2.checksum,
            },
            "diff": diff,
            "similarity": similarity,
            "is_same": version1.checksum == version2.checksum,
        }

    def _diff_configs(
        self,
        config1: Dict[str, Any],
        config2: Dict[str, Any],
        path: str = "",
    ) -> Dict[str, Any]:
        """计算配置差异"""
        diff = {
            "added": [],
            "removed": [],
            "modified": [],
        }

        all_keys = set(config1.keys()) | set(config2.keys())

        for key in all_keys:
            current_path = f"{path}.{key}" if path else key

            if key not in config1:
                diff["added"].append(
                    {
                        "path": current_path,
                        "value": config2[key],
                    }
                )
            elif key not in config2:
                diff["removed"].append(
                    {
                        "path": current_path,
                        "value": config1[key],
                    }
                )
            elif isinstance(config1[key], dict) and isinstance(config2[key], dict):
                nested_diff = self._diff_configs(
                    config1[key], config2[key], current_path
                )
                diff["added"].extend(nested_diff["added"])
                diff["removed"].extend(nested_diff["removed"])
                diff["modified"].extend(nested_diff["modified"])
            elif config1[key] != config2[key]:
                diff["modified"].append(
                    {
                        "path": current_path,
                        "old_value": config1[key],
                        "new_value": config2[key],
                    }
                )

        return diff

    def _calculate_similarity(
        self,
        config1: Dict[str, Any],
        config2: Dict[str, Any],
    ) -> float:
        """计算配置相似度"""
        str1 = json.dumps(config1, sort_keys=True)
        str2 = json.dumps(config2, sort_keys=True)

        return SequenceMatcher(None, str1, str2).ratio()

    def delete_version(self, version_id: str) -> bool:
        """删除版本

        Args:
            version_id: 版本ID

        Returns:
            是否删除成功
        """
        if version_id == self._current_version_id:
            logger.error("不能删除当前版本")
            return False

        if version_id not in self._versions:
            logger.error(f"版本 {version_id} 不存在")
            return False

        del self._versions[version_id]
        self._config_history.remove(version_id)

        if self.auto_save:
            self._save_to_disk()

        logger.info(f"已删除版本 {version_id}")
        return True

    def export_version(self, version_id: str, file_path: str) -> bool:
        """导出版本到文件

        Args:
            version_id: 版本ID
            file_path: 文件路径

        Returns:
            是否导出成功
        """
        version = self._versions.get(version_id)
        if not version:
            logger.error(f"版本 {version_id} 不存在")
            return False

        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(version.config, f, indent=2, ensure_ascii=False)

            logger.info(f"版本 {version_id} 已导出到 {file_path}")
            return True
        except Exception as e:
            logger.error(f"导出版本失败: {e}")
            return False

    def import_version(
        self,
        file_path: str,
        description: str = "",
        author: str = "system",
    ) -> Optional[ConfigVersion]:
        """从文件导入配置

        Args:
            file_path: 文件路径
            description: 描述
            author: 作者

        Returns:
            新创建的版本
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            version = self.create_version(
                config=config,
                change_type=ConfigChangeType.UPDATE,
                description=description or f"从 {file_path} 导入",
                author=author,
            )

            logger.info(f"配置已从 {file_path} 导入为版本 {version.version_id}")
            return version
        except Exception as e:
            logger.error(f"导入配置失败: {e}")
            return None

    def _save_to_disk(self):
        """保存到磁盘"""
        try:
            self._ensure_storage_dir()

            versions_data = {}
            for version_id, version in self._versions.items():
                versions_data[version_id] = {
                    "version_id": version.version_id,
                    "config": version.config,
                    "timestamp": version.timestamp.isoformat(),
                    "change_type": version.change_type.value,
                    "description": version.description,
                    "author": version.author,
                    "parent_version": version.parent_version,
                    "checksum": version.checksum,
                }

            meta_data = {
                "current_version_id": self._current_version_id,
                "config_history": self._config_history,
                "versions": versions_data,
            }

            meta_file = os.path.join(self.storage_path, "meta.json")
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2, ensure_ascii=False)

            logger.debug("配置版本已保存到磁盘")
        except Exception as e:
            logger.error(f"保存配置版本到磁盘失败: {e}")

    def _load_from_disk(self):
        """从磁盘加载"""
        try:
            meta_file = os.path.join(self.storage_path, "meta.json")

            if not os.path.exists(meta_file):
                return

            with open(meta_file, "r", encoding="utf-8") as f:
                meta_data = json.load(f)

            self._current_version_id = meta_data.get("current_version_id")
            self._config_history = meta_data.get("config_history", [])

            versions_data = meta_data.get("versions", {})
            for version_id, version_data in versions_data.items():
                self._versions[version_id] = ConfigVersion(
                    version_id=version_data["version_id"],
                    config=version_data["config"],
                    timestamp=datetime.fromisoformat(version_data["timestamp"]),
                    change_type=ConfigChangeType(version_data["change_type"]),
                    description=version_data.get("description", ""),
                    author=version_data.get("author", "system"),
                    parent_version=version_data.get("parent_version"),
                    checksum=version_data.get("checksum", ""),
                )

            logger.info(f"从磁盘加载了 {len(self._versions)} 个配置版本")
        except Exception as e:
            logger.error(f"从磁盘加载配置版本失败: {e}")
