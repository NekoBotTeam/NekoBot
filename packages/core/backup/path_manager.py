"""路径管理器

统一管理备份系统需要的所有路径，避免硬编码
"""

from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class BackupPaths:
    """备份路径配置"""

    project_root: Path
    """项目根目录"""

    data_dir: Path
    """数据目录"""

    backups_dir: Path
    """备份输出目录"""

    config_dir: Path
    """配置目录"""

    knowledge_base_dir: Path
    """知识库目录"""

    plugins_dir: Path
    """插件目录"""

    plugin_data_dir: Path
    """插件数据目录"""

    conversations_dir: Path
    """对话目录"""

    temp_dir: Path
    """临时文件目录"""

    logs_dir: Path
    """日志目录"""

    database_path: Path
    """数据库文件路径"""

    @property
    def plugin_data_backup_dir(self) -> Path:
        """插件数据备份目录（兼容旧版本）"""
        return self.project_root / "data" / "plugins_data"


class PathManager:
    """路径管理器

    提供统一的路径管理接口，支持环境变量配置
    """

    def __init__(self, project_root: Optional[Path] = None):
        """初始化路径管理器

        Args:
            project_root: 项目根目录，默认为当前文件上3级目录
        """
        if project_root is None:
            project_root = Path(__file__).parent.parent.parent.parent

        self.project_root = project_root
        self.data_dir = project_root / "data"

        self.paths = BackupPaths(
            project_root=project_root,
            data_dir=self.data_dir,
            backups_dir=self.data_dir / "backups",
            config_dir=self.data_dir / "config",
            knowledge_base_dir=self.data_dir / "knowledge_base",
            plugins_dir=self.data_dir / "plugins",
            plugin_data_dir=self.data_dir / "plugin_data",
            conversations_dir=self.data_dir / "conversations",
            temp_dir=self.data_dir / "temp",
            logs_dir=self.data_dir / "logs",
            database_path=self.data_dir / "data.db",
        )

    def ensure_directories(self) -> None:
        """确保所有必要的目录存在"""
        for attr in [
            "data_dir",
            "backups_dir",
            "config_dir",
            "knowledge_base_dir",
            "plugins_dir",
            "plugin_data_dir",
            "conversations_dir",
            "temp_dir",
            "logs_dir",
        ]:
            path = getattr(self.paths, attr)
            if isinstance(path, Path):
                path.mkdir(parents=True, exist_ok=True)

    def get_config_file(self, filename: str) -> Path:
        """获取配置文件路径

        Args:
            filename: 配置文件名

        Returns:
            配置文件完整路径
        """
        return self.paths.config_dir / filename

    def get_backup_dir(self, backup_id: str) -> Path:
        """获取备份目录路径

        Args:
            backup_id: 备份ID

        Returns:
            备份目录路径
        """
        return self.paths.backups_dir / backup_id

    def get_backup_metadata_file(self, backup_id: str) -> Path:
        """获取备份元数据文件路径

        Args:
            backup_id: 备份ID

        Returns:
            元数据文件路径
        """
        return self.get_backup_dir(backup_id) / "backup_metadata.json"

    def get_backup_settings_file(self) -> Path:
        """获取备份设置文件路径

        Returns:
            备份设置文件路径
        """
        return self.paths.backups_dir / "settings.json"

    def get_backup_list(self) -> list[Path]:
        """获取所有备份目录列表

        Returns:
            备份目录路径列表，按创建时间倒序排列
        """
        if not self.paths.backups_dir.exists():
            return []

        backups = []
        for item in self.paths.backups_dir.iterdir():
            if item.is_dir():
                backups.append(item)

        return sorted(backups, key=lambda x: x.stat().st_mtime, reverse=True)

    def get_kb_dir(self, kb_id: str) -> Path:
        """获取知识库目录路径

        Args:
            kb_id: 知识库ID

        Returns:
            知识库目录路径
        """
        return self.paths.knowledge_base_dir / kb_id

    def get_plugin_data_backup_dir(self, plugin_name: str) -> Path:
        """获取插件数据备份目录（兼容旧版本）

        Args:
            plugin_name: 插件名称

        Returns:
            插件数据备份目录路径
        """
        return self.paths.plugin_data_backup_dir / plugin_name

    def get_attachment_file(self, file_id: str) -> Path:
        """获取附件文件路径

        Args:
            file_id: 附件ID

        Returns:
            附件文件路径
        """
        return self.paths.conversations_dir / "attachments" / file_id

    def get_temp_file(self, filename: str) -> Path:
        """获取临时文件路径

        Args:
            filename: 文件名

        Returns:
            临时文件路径
        """
        return self.paths.temp_dir / filename

    def cleanup_old_backups(self, max_backups: int) -> list[str]:
        """清理旧备份

        Args:
            max_backups: 保留的最大备份数量

        Returns:
            被删除的备份ID列表
        """
        backups = self.get_backup_list()

        if len(backups) <= max_backups:
            return []

        backups_to_delete = backups[max_backups:]
        deleted_ids = []

        for backup_dir in backups_to_delete:
            try:
                import shutil

                shutil.rmtree(backup_dir)
                deleted_ids.append(backup_dir.name)
            except Exception as e:
                from loguru import logger

                logger.error(f"删除备份 {backup_dir.name} 失败: {e}")

        return deleted_ids

    def get_directory_size(self, directory: Path) -> float:
        """获取目录大小（字节）

        Args:
            directory: 目录路径

        Returns:
            目录大小（字节）
        """
        if not directory.exists():
            return 0.0

        total_size = 0.0
        for item in directory.rglob("*"):
            if item.is_file():
                try:
                    total_size += item.stat().st_size
                except Exception:
                    pass

        return total_size

    def format_size(self, size: int) -> str:
        """格式化文件大小

        Args:
            size: 字节大小

        Returns:
            格式化后的字符串，如 "1.23 MB"
        """
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"


__all__ = ["PathManager", "BackupPaths"]
