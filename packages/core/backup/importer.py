"""备份导入器

负责从备份文件恢复所有数据
"""

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, TYPE_CHECKING

from loguru import logger

from .path_manager import PathManager
from .constants import (
    BackupManifest,
    BackupMetadata,
    RestoreResult,
    RestoreStage,
    BACKUP_MANIFEST_VERSION,
)

if TYPE_CHECKING:
    from ..knowledge_base.kb_manager import KnowledgeBaseManager


def _get_major_version(version_str: str) -> str:
    """提取版本的主版本部分（前两位）

    Args:
        version_str: 版本字符串，如 "1.0.0"

    Returns:
        主版本字符串，如 "1.0"
    """
    if not version_str:
        return "0.0"

    parts = [p for p in version_str.split(".") if p]
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    elif len(parts) == 1 and parts[0]:
        return f"{parts[0]}.0"
    return "0.0"


@dataclass
class PreCheckResult:
    """导入预检查结果"""

    valid: bool = False
    """是否有效"""

    can_import: bool = False
    """是否可以导入"""

    version_status: str = ""
    """版本状态"""

    backup_version: str = ""
    """备份版本"""

    current_version: str = ""
    """当前版本"""

    backup_time: str = ""
    """备份时间"""

    confirm_message: str = ""
    """确认消息"""

    warnings: list[str] = field(default_factory=list)
    """警告列表"""

    errors: list[str] = field(default_factory=list)
    """错误列表"""

    backup_summary: dict = field(default_factory=dict)
    """备份摘要"""

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "valid": self.valid,
            "can_import": self.can_import,
            "version_status": self.version_status,
            "backup_version": self.backup_version,
            "current_version": self.current_version,
            "backup_time": self.backup_time,
            "confirm_message": self.confirm_message,
            "warnings": self.warnings,
            "errors": self.errors,
            "backup_summary": self.backup_summary,
        }


class BackupImporter:
    """备份导入器

    导入备份文件中的所有数据
    """

    def __init__(
        self,
        path_manager: PathManager,
        db_path: Optional[Path] = None,
        kb_manager: Optional["KnowledgeBaseManager"] = None,
    ):
        """初始化导入器

        Args:
            path_manager: 路径管理器
            db_path: 数据库路径，默认为data/data.db
            kb_manager: 知识库管理器
        """
        self.path_manager = path_manager
        self.db_path = db_path or path_manager.paths.database_path
        self.kb_manager = kb_manager

    def _calculate_checksum(self, data: str) -> str:
        """计算字符串的SHA256校验和"""
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    async def pre_check_backup(
        self,
        backup_path: Path,
    ) -> PreCheckResult:
        """预检查备份文件

        Args:
            backup_path: 备份文件路径（ZIP或目录）

        Returns:
            预检查结果
        """
        result = PreCheckResult()

        try:
            logger.info(f"预检查备份: {backup_path}")

            manifest = None

            if backup_path.is_dir():
                manifest_path = backup_path / "manifest.json"
                if not manifest_path.exists():
                    result.errors.append("备份清单文件不存在")
                    return result

                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
                    manifest = BackupManifest.from_dict(manifest_data)

            elif backup_path.suffix == ".zip":
                with zipfile.ZipFile(backup_path, "r") as zf:
                    if "manifest.json" not in zf.namelist():
                        result.errors.append("备份ZIP文件中不包含清单文件")
                        return result

                    manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
                    manifest = BackupManifest.from_dict(manifest_data)
            else:
                result.errors.append("不支持的备份文件格式")
                return result

            result.valid = True
            result.backup_version = manifest.neko_version
            result.backup_time = manifest.created_at
            result.backup_summary = {
                "version": manifest.version,
                "size": manifest.size,
                "tables": manifest.tables,
                "directories": manifest.directories,
                "files_count": len(manifest.files),
            }

            from ..version import get_version_info

            version_info = get_version_info()
            result.current_version = version_info.get("version", "1.0.0")

            backup_major = _get_major_version(result.backup_version)
            current_major = _get_major_version(result.current_version)

            if backup_major != current_major:
                result.version_status = "major_diff"
                result.can_import = False
                result.confirm_message = (
                    f"备份版本 ({result.backup_version}) 与当前版本 ({result.current_version}) 主版本不同，"
                    f"可能存在不兼容问题，建议使用相同主版本的NekoBot进行恢复。"
                )
                result.errors.append("主版本不兼容")
            else:
                result.version_status = "match"
                result.can_import = True
                result.confirm_message = f"备份版本 ({result.backup_version}) 与当前版本 ({result.current_version}) 兼容。"
                if result.backup_version != result.current_version:
                    result.warnings.append(
                        "备份版本与当前版本不完全一致，可能存在细微差异"
                    )

            logger.info(f"预检查完成，版本状态: {result.version_status}")

        except Exception as e:
            logger.error(f"预检查备份失败: {e}")
            result.errors.append(f"预检查失败: {str(e)}")

        return result

    async def _restore_main_database(
        self,
        backup_dir: Path,
        progress_callback: Optional[Callable[[str, int, int, str], Any]] = None,
    ) -> dict[str, int]:
        """恢复主数据库

        Args:
            backup_dir: 备份目录
            progress_callback: 进度回调

        Returns:
            恢复的表统计信息
        """
        logger.info("开始恢复主数据库...")

        tables_stats = {}

        try:
            databases_dir = backup_dir / "databases"
            if not databases_dir.exists():
                logger.warning("备份数据库目录不存在")
                return tables_stats

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            table_files = list(databases_dir.glob("*.json"))
            total_tables = len(table_files)

            for idx, table_file in enumerate(table_files):
                table_name = table_file.stem
                if table_name.startswith("sqlite_"):
                    continue

                if progress_callback:
                    await progress_callback(
                        RestoreStage.MAIN_DATABASE,
                        idx,
                        total_tables,
                        f"恢复表 {table_name}...",
                    )

                with open(table_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if not data:
                    logger.info(f"表 {table_name} 为空，跳过")
                    continue

                columns = list(data[0].keys())
                placeholders = ",".join(["?"] * len(columns))

                cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                cursor.execute(
                    f"CREATE TABLE {table_name} ("
                    + ",".join([f'"{col}" TEXT' for col in columns])
                    + ")"
                )

                for row in data:
                    cursor.execute(
                        f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})",
                        [str(row.get(col, "")) for col in columns],
                    )

                tables_stats[table_name] = len(data)
                logger.info(f"恢复表 {table_name}: {len(data)} 条记录")

            conn.commit()
            conn.close()

            logger.info(f"主数据库恢复完成，共 {len(tables_stats)} 个表")

        except Exception as e:
            logger.error(f"恢复主数据库失败: {e}")
            raise

        return tables_stats

    async def _restore_knowledge_base(
        self,
        backup_dir: Path,
        progress_callback: Optional[Callable[[str, int, int, str], Any]] = None,
    ) -> dict[str, Any]:
        """恢复知识库

        Args:
            backup_dir: 备份目录
            progress_callback: 进度回调

        Returns:
            知识库统计信息
        """
        if not self.kb_manager:
            logger.info("知识库管理器未初始化，跳过知识库恢复")
            return {}

        logger.info("开始恢复知识库...")

        kb_stats = {
            "knowledge_bases": 0,
            "documents": 0,
        }

        try:
            kb_backup_dir = backup_dir / "knowledge_base"
            if not kb_backup_dir.exists():
                logger.info("备份知识库目录不存在")
                return kb_stats

            kb_dirs = [d for d in kb_backup_dir.iterdir() if d.is_dir()]

            for kb_dir in kb_dirs:
                kb_id = kb_dir.name
                metadata_path = kb_dir / "metadata.json"

                if not metadata_path.exists():
                    logger.warning(f"知识库 {kb_id} 元数据文件不存在，跳过")
                    continue

                with open(metadata_path, "r", encoding="utf-8") as f:
                    kb_data = json.load(f)

                from datetime import datetime
                from ..knowledge_base.models import KnowledgeBase

                kb = KnowledgeBase(
                    id=kb_data.get("id", kb_id),
                    name=kb_data.get("name", ""),
                    description=kb_data.get("description", ""),
                    embedding_model=kb_data.get("embedding_model", "openai"),
                    created_at=datetime.fromisoformat(
                        kb_data.get("created_at", datetime.now().isoformat())
                    ),
                    document_count=kb_data.get("document_count", 0),
                )

                await self.kb_manager.create_knowledge_base(
                    kb_id=kb.id,
                    name=kb.name,
                    description=kb.description,
                    embedding_model=kb.embedding_model,
                )

                kb_stats["knowledge_bases"] += 1
                logger.info(f"恢复知识库: {kb.name} ({kb.id})")

            logger.info(f"知识库恢复完成，共 {kb_stats['knowledge_bases']} 个知识库")

        except Exception as e:
            logger.error(f"恢复知识库失败: {e}")
            raise

        return kb_stats

    async def _restore_config_files(
        self,
        backup_dir: Path,
        progress_callback: Optional[Callable[[str, int, int, str], Any]] = None,
    ) -> list[str]:
        """恢复配置文件

        Args:
            backup_dir: 备份目录
            progress_callback: 进度回调

        Returns:
            恢复的文件列表
        """
        logger.info("开始恢复配置文件...")

        backup_config_dir = backup_dir / "config"
        if not backup_config_dir.exists():
            logger.info("备份配置目录不存在")
            return []

        restored_files = []

        try:
            config_dir = self.path_manager.paths.config_dir
            config_dir.mkdir(parents=True, exist_ok=True)

            for config_file in backup_config_dir.glob("*.json"):
                dest_path = config_dir / config_file.name

                shutil.copy2(config_file, dest_path)
                restored_files.append(f"config/{config_file.name}")
                logger.info(f"恢复配置文件: {config_file.name}")

            logger.info(f"配置文件恢复完成，共 {len(restored_files)} 个文件")

        except Exception as e:
            logger.error(f"恢复配置文件失败: {e}")
            raise

        return restored_files

    async def _restore_directory(
        self,
        backup_dir: Path,
        dir_name: str,
        progress_callback: Optional[Callable[[str, int, int, str], Any]] = None,
    ) -> dict[str, int]:
        """恢复目录

        Args:
            backup_dir: 备份目录
            dir_name: 目录名称
            progress_callback: 进度回调

        Returns:
            目录统计信息
        """
        logger.info(f"开始恢复 {dir_name}...")

        backup_subdir = backup_dir / dir_name
        if not backup_subdir.exists():
            logger.info(f"备份 {dir_name} 目录不存在")
            return {"count": 0}

        stats = {"count": 0}

        try:
            if dir_name == "plugins":
                dest_dir = self.path_manager.paths.plugins_dir
            elif dir_name == "plugin_data":
                dest_dir = self.path_manager.paths.plugin_data_dir
            elif dir_name == "conversations":
                dest_dir = self.path_manager.paths.conversations_dir
            elif dir_name == "attachments":
                dest_dir = self.path_manager.paths.conversations_dir / "attachments"
            else:
                dest_dir = self.path_manager.paths.data_dir / dir_name

            dest_dir.mkdir(parents=True, exist_ok=True)

            if dest_dir.exists():
                shutil.rmtree(dest_dir)

            shutil.copytree(backup_subdir, dest_dir)

            file_count = sum(1 for _ in dest_dir.rglob("*") if _.is_file())
            stats["count"] = file_count

            logger.info(f"{dir_name} 恢复完成，共 {file_count} 个文件")

        except Exception as e:
            logger.error(f"恢复 {dir_name} 失败: {e}")
            raise

        return stats

    async def restore(
        self,
        backup_path: Path,
        force: bool = False,
        progress_callback: Optional[Callable[[str, int, int, str], Any]] = None,
    ) -> RestoreResult:
        """恢复备份

        Args:
            backup_path: 备份文件路径（ZIP或目录）
            force: 是否强制恢复（忽略版本检查）
            progress_callback: 进度回调 (stage, current, total, message)

        Returns:
            恢复结果
        """
        import time

        start_time = time.time()
        result = RestoreResult(success=False)

        try:
            if progress_callback:
                await progress_callback(RestoreStage.PRE_CHECK, 0, 100, "预检查备份...")

            pre_check = await self.pre_check_backup(backup_path)
            result.version_check = pre_check.to_dict()

            if not pre_check.valid:
                result.message = "备份文件无效"
                result.errors.extend(pre_check.errors)
                return result

            if not pre_check.can_import and not force:
                result.message = pre_check.confirm_message
                result.warnings.extend(pre_check.warnings)
                return result

            backup_dir = backup_path
            temp_extract_dir = None

            if backup_path.is_file() and backup_path.suffix == ".zip":
                temp_extract_dir = self.path_manager.get_temp_file(
                    f"restore_{int(time.time())}"
                )
                temp_extract_dir.mkdir(parents=True, exist_ok=True)

                with zipfile.ZipFile(backup_path, "r") as zf:
                    zf.extractall(temp_extract_dir)

                backup_dir = temp_extract_dir
                logger.info(f"备份解压到: {backup_dir}")

            try:
                if progress_callback:
                    await progress_callback(
                        RestoreStage.MAIN_DATABASE, 0, 100, "恢复主数据库..."
                    )

                tables_restored = await self._restore_main_database(
                    backup_dir, progress_callback
                )

                if progress_callback:
                    await progress_callback(
                        RestoreStage.KNOWLEDGE_BASE, 0, 100, "恢复知识库..."
                    )

                kb_restored = await self._restore_knowledge_base(
                    backup_dir, progress_callback
                )

                if progress_callback:
                    await progress_callback(
                        RestoreStage.CONFIG_FILES, 0, 100, "恢复配置文件..."
                    )

                config_files_restored = await self._restore_config_files(
                    backup_dir, progress_callback
                )

                if progress_callback:
                    await progress_callback(
                        RestoreStage.ATTACHMENTS, 0, 100, "恢复附件..."
                    )

                await self._restore_directory(
                    backup_dir, "attachments", progress_callback
                )

                if progress_callback:
                    await progress_callback(
                        RestoreStage.PLUGINS, 0, 100, "恢复插件和数据目录..."
                    )

                plugins_restored = await self._restore_directory(
                    backup_dir, "plugins", progress_callback
                )
                plugin_data_restored = await self._restore_directory(
                    backup_dir, "plugin_data", progress_callback
                )
                conversations_restored = await self._restore_directory(
                    backup_dir, "conversations", progress_callback
                )

                result.success = True
                result.message = "备份恢复成功，请重启应用以生效"
                result.tables_restored = tables_restored
                result.files_restored = config_files_restored
                result.directories_restored = {
                    "plugins": int(plugins_restored.get("count", 0)),
                    "plugin_data": int(plugin_data_restored.get("count", 0)),
                    "conversations": int(conversations_restored.get("count", 0)),
                    "knowledge_bases": int(kb_restored.get("knowledge_bases", 0)),
                }
                result.warnings.extend(pre_check.warnings)
                result.duration = time.time() - start_time

                logger.info(f"备份恢复成功，耗时: {result.duration:.2f}秒")

            finally:
                if temp_extract_dir and temp_extract_dir.exists():
                    shutil.rmtree(temp_extract_dir)
                    logger.info("清理临时解压目录")

        except Exception as e:
            logger.error(f"恢复备份失败: {e}")
            result.message = f"恢复备份失败: {str(e)}"
            result.errors.append(str(e))
            result.duration = time.time() - start_time

        return result


__all__ = ["BackupImporter", "PreCheckResult"]
