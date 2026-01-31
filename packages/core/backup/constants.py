"""备份模块常量

定义导出器和导入器共享的常量
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


BACKUP_MANIFEST_VERSION = "1.0"


@dataclass
class BackupManifest:
    """备份清单"""

    version: str
    """备份格式版本"""

    neko_version: str
    """NekoBot版本"""

    created_at: str
    """创建时间（ISO格式）"""

    size: int
    """备份总大小（字节）"""

    checksums: Dict[str, str]
    """文件校验和 {文件路径: sha256}"""

    tables: Dict[str, int]
    """导出的数据库表统计 {表名: 记录数}"""

    directories: Dict[str, Dict[str, Any]]
    """导出的目录统计 {目录名: {文件数, 总大小}}"""

    files: List[str]
    """包含的文件列表"""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "version": self.version,
            "neko_version": self.neko_version,
            "created_at": self.created_at,
            "size": self.size,
            "checksums": self.checksums,
            "tables": self.tables,
            "directories": self.directories,
            "files": self.files,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BackupManifest":
        """从字典创建"""
        return cls(
            version=data.get("version", ""),
            neko_version=data.get("neko_version", ""),
            created_at=data.get("created_at", ""),
            size=data.get("size", 0),
            checksums=data.get("checksums", {}),
            tables=data.get("tables", {}),
            directories=data.get("directories", {}),
            files=data.get("files", []),
        )


@dataclass
class BackupMetadata:
    """备份元数据（存储在backup_metadata.json中）"""

    backup_id: str
    """备份ID"""

    name: str
    """备份名称"""

    description: str
    """备份描述"""

    created_at: str
    """创建时间（ISO格式）"""

    neko_version: str
    """NekoBot版本"""

    auto_backup: bool
    """是否为自动备份"""

    size: int
    """备份大小（字节）"""

    manifest_version: str = BACKUP_MANIFEST_VERSION
    """清单版本"""

    files: List[str] = field(default_factory=list)
    """包含的文件列表"""

    tables: Dict[str, int] = field(default_factory=dict)
    """数据库表统计"""

    directories: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    """目录统计"""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "backup_id": self.backup_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "neko_version": self.neko_version,
            "auto_backup": self.auto_backup,
            "size": self.size,
            "manifest_version": self.manifest_version,
            "files": self.files,
            "tables": self.tables,
            "directories": self.directories,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BackupMetadata":
        """从字典创建"""
        return cls(
            backup_id=data.get("backup_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            neko_version=data.get("neko_version", ""),
            auto_backup=data.get("auto_backup", False),
            size=data.get("size", 0),
            manifest_version=data.get("manifest_version", BACKUP_MANIFEST_VERSION),
            files=data.get("files", []),
            tables=data.get("tables", {}),
            directories=data.get("directories", {}),
        )


@dataclass
class BackupResult:
    """备份操作结果"""

    success: bool
    """是否成功"""

    backup_id: str = ""
    """备份ID"""

    message: str = ""
    """结果消息"""

    size: int = 0
    """备份大小（字节）"""

    files: List[str] = field(default_factory=list)
    """备份的文件列表"""

    tables: Dict[str, int] = field(default_factory=dict)
    """导出的表统计"""

    errors: List[str] = field(default_factory=list)
    """错误列表"""

    warnings: List[str] = field(default_factory=list)
    """警告列表"""

    duration: float = 0.0
    """耗时（秒）"""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "backup_id": self.backup_id,
            "message": self.message,
            "size": self.size,
            "files": self.files,
            "tables": self.tables,
            "errors": self.errors,
            "warnings": self.warnings,
            "duration": self.duration,
        }


@dataclass
class RestoreResult:
    """恢复操作结果"""

    success: bool
    """是否成功"""

    message: str = ""
    """结果消息"""

    tables_restored: Dict[str, int] = field(default_factory=dict)
    """恢复的表统计 {表名: 记录数}"""

    files_restored: List[str] = field(default_factory=list)
    """恢复的文件列表"""

    directories_restored: Dict[str, int] = field(default_factory=dict)
    """恢复的目录统计 {目录名: 文件数}"""

    errors: List[str] = field(default_factory=list)
    """错误列表"""

    warnings: List[str] = field(default_factory=list)
    """警告列表"""

    duration: float = 0.0
    """耗时（秒）"""

    version_check: Dict[str, Any] = field(default_factory=dict)
    """版本检查结果"""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "message": self.message,
            "tables_restored": self.tables_restored,
            "files_restored": self.files_restored,
            "directories_restored": self.directories_restored,
            "errors": self.errors,
            "warnings": self.warnings,
            "duration": self.duration,
            "version_check": self.version_check,
        }


class BackupStage:
    """备份阶段常量"""

    INITIALIZATION = "initialization"
    MAIN_DATABASE = "main_database"
    KNOWLEDGE_BASE = "knowledge_base"
    CONFIG_FILES = "config_files"
    ATTACHMENTS = "attachments"
    PLUGINS = "plugins"
    DIRECTORIES = "directories"
    MANIFEST = "manifest"
    FINALIZATION = "finalization"


class RestoreStage:
    """恢复阶段常量"""

    PRE_CHECK = "pre_check"
    MAIN_DATABASE = "main_database"
    KNOWLEDGE_BASE = "knowledge_base"
    CONFIG_FILES = "config_files"
    ATTACHMENTS = "attachments"
    PLUGINS = "plugins"
    DIRECTORIES = "directories"
    POST_CHECK = "post_check"


__all__ = [
    "BACKUP_MANIFEST_VERSION",
    "BackupManifest",
    "BackupMetadata",
    "BackupResult",
    "RestoreResult",
    "BackupStage",
    "RestoreStage",
]
