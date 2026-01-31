"""备份导出器

负责将所有数据导出为备份文件
"""

import hashlib
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, TYPE_CHECKING

from loguru import logger

from .path_manager import PathManager
from .constants import (
    BackupManifest,
    BackupMetadata,
    BackupResult,
    BackupStage,
    BACKUP_MANIFEST_VERSION,
)

if TYPE_CHECKING:
    from ..knowledge_base.kb_manager import KnowledgeBaseManager


class BackupExporter:
    """备份导出器

    导出内容：
    - 主数据库（data/data.db）
    - 知识库元数据和文档
    - 配置文件（data/config/*.json）
    - 插件目录（data/plugins）
    - 插件数据目录（data/plugin_data）
    - 对话目录（data/conversations）
    - 临时文件目录（data/temp）
    - 日志目录（data/logs）
    """

    def __init__(
        self,
        path_manager: PathManager,
        db_path: Optional[Path] = None,
        kb_manager: Optional["KnowledgeBaseManager"] = None,
    ):
        """初始化导出器

        Args:
            path_manager: 路径管理器
            db_path: 数据库路径，默认为data/data.db
            kb_manager: 知识库管理器
        """
        self.path_manager = path_manager
        self.db_path = db_path or path_manager.paths.database_path
        self.kb_manager = kb_manager
        self._checksums: dict[str, str] = {}
        self._manifest_files: list[str] = []
        self._manifest_directories: dict[str, dict[str, Any]] = {}

    def _calculate_checksum(self, data: str) -> str:
        """计算字符串的SHA256校验和

        Args:
            data: 要计算校验和的数据

        Returns:
            SHA256校验和（十六进制）
        """
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _add_checksum(self, file_path: str, data: str) -> None:
        """添加文件校验和

        Args:
            file_path: 文件路径（在备份中的相对路径）
            data: 文件内容
        """
        self._checksums[file_path] = self._calculate_checksum(data)
        self._manifest_files.append(file_path)

    async def _export_main_database(self, backup_dir: Path) -> dict[str, Any]:
        """导出主数据库

        Args:
            backup_dir: 备份目录

        Returns:
            表统计信息 {表名: 记录数}
        """
        if not self.db_path.exists():
            logger.warning(f"数据库文件不存在: {self.db_path}")
            return {}

        logger.info("开始导出主数据库...")

        tables_stats = {}

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = cursor.fetchall()

            for table_info in tables:
                table_name = table_info[0]
                if table_name.startswith("sqlite_"):
                    continue

                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]

                if count > 0:
                    cursor.execute(f"SELECT * FROM {table_name}")
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()

                    data = []
                    for row in rows:
                        row_dict = {}
                        for i, col in enumerate(columns):
                            row_dict[col] = row[i]
                        data.append(row_dict)

                    table_json = json.dumps(
                        data, ensure_ascii=False, default=str, indent=2
                    )
                    output_path = backup_dir / "databases" / f"{table_name}.json"
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(table_json)

                    self._add_checksum(f"databases/{table_name}.json", table_json)
                    tables_stats[table_name] = count
                    logger.info(f"导出表 {table_name}: {count} 条记录")

            conn.close()
            logger.info(f"主数据库导出完成，共 {len(tables_stats)} 个表")

        except Exception as e:
            logger.error(f"导出主数据库失败: {e}")
            raise

        return tables_stats

    async def _export_knowledge_base(self, backup_dir: Path) -> dict[str, Any]:
        """导出知识库

        Args:
            backup_dir: 备份目录

        Returns:
            知识库统计信息
        """
        if not self.kb_manager:
            logger.info("知识库管理器未初始化，跳过知识库导出")
            return {}

        logger.info("开始导出知识库...")

        kb_stats = {
            "knowledge_bases": 0,
            "documents": 0,
            "chunks": 0,
        }

        try:
            knowledge_bases = await self.kb_manager.list_knowledge_bases()

            for kb in knowledge_bases:
                kb_dir = backup_dir / "knowledge_base" / kb.id
                kb_dir.mkdir(parents=True, exist_ok=True)

                kb_json = json.dumps(kb.to_dict(), ensure_ascii=False, indent=2)
                with open(kb_dir / "metadata.json", "w", encoding="utf-8") as f:
                    f.write(kb_json)

                self._add_checksum(f"knowledge_base/{kb.id}/metadata.json", kb_json)
                kb_stats["knowledge_bases"] += 1

                logger.info(f"导出知识库: {kb.name} ({kb.id})")

            logger.info(f"知识库导出完成，共 {kb_stats['knowledge_bases']} 个知识库")

        except Exception as e:
            logger.error(f"导出知识库失败: {e}")
            raise

        return kb_stats

    async def _export_config_files(self, backup_dir: Path) -> list[str]:
        """导出配置文件

        Args:
            backup_dir: 备份目录

        Returns:
            导出的文件列表
        """
        logger.info("开始导出配置文件...")

        config_dir = self.path_manager.paths.config_dir
        if not config_dir.exists():
            logger.warning(f"配置目录不存在: {config_dir}")
            return []

        exported_files = []

        try:
            backup_config_dir = backup_dir / "config"
            backup_config_dir.mkdir(parents=True, exist_ok=True)

            for config_file in config_dir.glob("*.json"):
                backup_path = backup_config_dir / config_file.name

                with open(config_file, "r", encoding="utf-8") as f:
                    content = f.read()

                with open(backup_path, "w", encoding="utf-8") as f:
                    f.write(content)

                self._add_checksum(f"config/{config_file.name}", content)
                exported_files.append(f"config/{config_file.name}")

            logger.info(f"配置文件导出完成，共 {len(exported_files)} 个文件")

        except Exception as e:
            logger.error(f"导出配置文件失败: {e}")
            raise

        return exported_files

    async def _export_attachments(self, backup_dir: Path) -> dict[str, Any]:
        """导出附件文件

        Args:
            backup_dir: 备份目录

        Returns:
            附件统计信息
        """
        logger.info("开始导出附件...")

        attachments_dir = self.path_manager.paths.conversations_dir / "attachments"
        if not attachments_dir.exists():
            logger.info("附件目录不存在，跳过附件导出")
            return {"count": 0, "size": 0}

        stats = {
            "count": 0,
            "size": 0,
        }

        try:
            backup_attachments_dir = backup_dir / "attachments"
            backup_attachments_dir.mkdir(parents=True, exist_ok=True)

            for attachment_file in attachments_dir.rglob("*"):
                if attachment_file.is_file():
                    backup_path = backup_attachments_dir / attachment_file.relative_to(
                        attachments_dir
                    )
                    backup_path.parent.mkdir(parents=True, exist_ok=True)

                    import shutil

                    shutil.copy2(attachment_file, backup_path)

                    stats["count"] += 1
                    stats["size"] += attachment_file.stat().st_size

                    logger.debug(f"导出附件: {attachment_file.name}")

            logger.info(f"附件导出完成，共 {stats['count']} 个文件")

        except Exception as e:
            logger.error(f"导出附件失败: {e}")
            raise

        return stats

    async def _export_directory(
        self,
        source_dir: Path,
        backup_dir: Path,
        dir_name: str,
        exclude_patterns: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """导出目录

        Args:
            source_dir: 源目录
            backup_dir: 备份目录
            dir_name: 目录名称
            exclude_patterns: 排除的文件模式列表

        Returns:
            目录统计信息
        """
        if not source_dir.exists():
            logger.info(f"{dir_name} 目录不存在，跳过")
            return {"count": 0, "size": 0}

        logger.info(f"开始导出 {dir_name}...")

        exclude_patterns = exclude_patterns or []
        stats = {
            "count": 0,
            "size": 0,
        }

        try:
            backup_subdir = backup_dir / dir_name
            backup_subdir.mkdir(parents=True, exist_ok=True)

            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(source_dir)

                    if any(
                        pattern in str(relative_path) for pattern in exclude_patterns
                    ):
                        continue

                    backup_path = backup_subdir / relative_path
                    backup_path.parent.mkdir(parents=True, exist_ok=True)

                    import shutil

                    shutil.copy2(file_path, backup_path)

                    stats["count"] += 1
                    stats["size"] += file_path.stat().st_size

            self._manifest_directories[dir_name] = stats
            logger.info(f"{dir_name} 导出完成，共 {stats['count']} 个文件")

        except Exception as e:
            logger.error(f"导出 {dir_name} 失败: {e}")
            raise

        return stats

    async def _generate_manifest(
        self,
        backup_dir: Path,
        neko_version: str,
        tables_stats: dict[str, Any],
    ) -> BackupManifest:
        """生成备份清单

        Args:
            backup_dir: 备份目录
            neko_version: NekoBot版本
            tables_stats: 表统计信息

        Returns:
            备份清单
        """
        logger.info("生成备份清单...")

        backup_size = self.path_manager.get_directory_size(backup_dir)

        manifest = BackupManifest(
            version=BACKUP_MANIFEST_VERSION,
            neko_version=neko_version,
            created_at=datetime.now(timezone.utc).isoformat(),
            size=backup_size,
            checksums=self._checksums,
            tables=tables_stats,
            directories=self._manifest_directories,
            files=self._manifest_files,
        )

        manifest_json = json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2)
        manifest_path = backup_dir / "manifest.json"

        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(manifest_json)

        logger.info("备份清单生成完成")
        return manifest

    async def export(
        self,
        backup_name: str = "",
        backup_description: str = "",
        auto_backup: bool = False,
        progress_callback: Optional[Callable[[str, int, int, str], Any]] = None,
    ) -> BackupResult:
        """导出备份

        Args:
            backup_name: 备份名称
            backup_description: 备份描述
            auto_backup: 是否为自动备份
            progress_callback: 进度回调函数 (stage, current, total, message)

        Returns:
            备份结果
        """
        import time

        start_time = time.time()
        result = BackupResult(success=False)

        try:
            if progress_callback:
                await progress_callback(
                    BackupStage.INITIALIZATION, 0, 100, "初始化备份..."
                )

            backup_id = datetime.now().strftime("backup_%Y%m%d_%H%M%S")
            backup_dir = self.path_manager.get_backup_dir(backup_id)
            backup_dir.mkdir(parents=True, exist_ok=True)

            if progress_callback:
                await progress_callback(
                    BackupStage.MAIN_DATABASE, 0, 100, "导出主数据库..."
                )

            tables_stats = await self._export_main_database(backup_dir)

            if progress_callback:
                await progress_callback(
                    BackupStage.KNOWLEDGE_BASE, 0, 100, "导出知识库..."
                )

            kb_stats = await self._export_knowledge_base(backup_dir)

            if progress_callback:
                await progress_callback(
                    BackupStage.CONFIG_FILES, 0, 100, "导出配置文件..."
                )

            config_files = await self._export_config_files(backup_dir)

            if progress_callback:
                await progress_callback(BackupStage.ATTACHMENTS, 0, 100, "导出附件...")

            attachment_stats = await self._export_attachments(backup_dir)

            if progress_callback:
                await progress_callback(
                    BackupStage.PLUGINS, 0, 100, "导出插件和数据目录..."
                )

            await self._export_directory(
                self.path_manager.paths.plugins_dir,
                backup_dir,
                "plugins",
                exclude_patterns=["__pycache__", "*.pyc", ".DS_Store"],
            )

            await self._export_directory(
                self.path_manager.paths.plugin_data_dir,
                backup_dir,
                "plugin_data",
                exclude_patterns=["__pycache__", "*.pyc", ".DS_Store"],
            )

            await self._export_directory(
                self.path_manager.paths.conversations_dir,
                backup_dir,
                "conversations",
                exclude_patterns=["attachments"],
            )

            if progress_callback:
                await progress_callback(BackupStage.MANIFEST, 0, 100, "生成备份清单...")

            from ..version import get_version_info

            version_info = get_version_info()
            neko_version = version_info.get("version", "1.0.0")

            manifest = await self._generate_manifest(
                backup_dir, neko_version, tables_stats
            )

            backup_size = int(self.path_manager.get_directory_size(backup_dir))

            metadata = BackupMetadata(
                backup_id=backup_id,
                name=backup_name or backup_id,
                description=backup_description,
                created_at=manifest.created_at,
                neko_version=manifest.neko_version,
                auto_backup=auto_backup,
                size=backup_size,
                manifest_version=manifest.version,
                files=manifest.files,
                tables=manifest.tables,
                directories=manifest.directories,
            )

            metadata_path = self.path_manager.get_backup_metadata_file(backup_id)
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata.to_dict(), f, ensure_ascii=False, indent=2)

            if progress_callback:
                await progress_callback(BackupStage.FINALIZATION, 100, 100, "备份完成")

            result.success = True
            result.backup_id = backup_id
            result.message = "备份创建成功"
            result.size = backup_size
            result.files = manifest.files
            result.tables = tables_stats
            result.duration = time.time() - start_time

            logger.info(
                f"备份 {backup_id} 创建成功，大小: {self.path_manager.format_size(backup_size)}"
            )

        except Exception as e:
            logger.error(f"创建备份失败: {e}")
            result.message = f"创建备份失败: {str(e)}"
            result.errors.append(str(e))
            result.duration = time.time() - start_time

        return result


__all__ = ["BackupExporter"]
