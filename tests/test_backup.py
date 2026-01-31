"""备份模块单元测试

测试备份导出、导入和路径管理功能
"""

import json
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from packages.core.backup import (
    BackupExporter,
    BackupImporter,
    PathManager,
    BACKUP_MANIFEST_VERSION,
    BackupMetadata,
    BackupManifest,
)


@pytest.fixture
def temp_project_root():
    """创建临时项目根目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "data").mkdir()
        (root / "data" / "config").mkdir(parents=True)
        (root / "data" / "plugins").mkdir(parents=True)
        (root / "data" / "plugin_data").mkdir(parents=True)
        (root / "data" / "conversations").mkdir(parents=True)
        (root / "data" / "knowledge_base").mkdir(parents=True)
        (root / "data" / "temp").mkdir(parents=True)
        yield root


@pytest.fixture
def path_manager(temp_project_root):
    """创建路径管理器"""
    return PathManager(temp_project_root)


@pytest.fixture
def sample_database(temp_project_root):
    """创建示例数据库"""
    db_path = temp_project_root / "data" / "data.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE users (
            username TEXT PRIMARY KEY,
            hashed_password TEXT NOT NULL
        )
    """)

    cursor.execute(
        "INSERT INTO users VALUES (?, ?)", ("test_user", "hashed_password_123")
    )

    cursor.execute("""
        CREATE TABLE platforms (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT NOT NULL
        )
    """)

    cursor.execute(
        "INSERT INTO platforms VALUES (?, ?, ?)", ("qq_test", "qq", "QQ测试")
    )

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def sample_config(temp_project_root):
    """创建示例配置文件"""
    config_path = temp_project_root / "data" / "config" / "test_config.json"
    config_data = {"test_key": "test_value", "nested": {"key": "value"}}

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f)

    return config_path


class TestPathManager:
    """测试路径管理器"""

    def test_initialization(self, temp_project_root):
        """测试初始化"""
        pm = PathManager(temp_project_root)

        assert pm.project_root == temp_project_root
        assert pm.paths.data_dir == temp_project_root / "data"
        assert pm.paths.backups_dir == temp_project_root / "data" / "backups"
        assert pm.paths.database_path == temp_project_root / "data" / "data.db"

    def test_ensure_directories(self, path_manager):
        """测试确保目录存在"""
        path_manager.ensure_directories()

        assert path_manager.paths.backups_dir.exists()
        assert path_manager.paths.config_dir.exists()

    def test_get_backup_dir(self, path_manager):
        """测试获取备份目录"""
        backup_dir = path_manager.get_backup_dir("test_backup_123")
        expected = path_manager.paths.backups_dir / "test_backup_123"

        assert backup_dir == expected

    def test_get_backup_metadata_file(self, path_manager):
        """测试获取备份元数据文件"""
        metadata_file = path_manager.get_backup_metadata_file("test_backup")
        expected = (
            path_manager.paths.backups_dir / "test_backup" / "backup_metadata.json"
        )

        assert metadata_file == expected

    def test_format_size(self, path_manager):
        """测试格式化大小"""
        assert path_manager.format_size(100) == "100.00 B"
        assert path_manager.format_size(1024) == "1.00 KB"
        assert path_manager.format_size(1024 * 1024) == "1.00 MB"
        assert path_manager.format_size(1024 * 1024 * 1024) == "1.00 GB"

    def test_get_directory_size(self, path_manager):
        """测试获取目录大小"""
        test_file = path_manager.paths.temp_dir / "test.txt"
        test_file.write_text("hello world")

        size = path_manager.get_directory_size(path_manager.paths.temp_dir)
        assert size == len("hello world")

    def test_cleanup_old_backups(self, path_manager):
        """测试清理旧备份"""
        for i in range(5):
            backup_dir = path_manager.get_backup_dir(f"backup_{i}")
            backup_dir.mkdir(parents=True, exist_ok=True)

        deleted = path_manager.cleanup_old_backups(3)

        assert len(deleted) == 2
        assert all("backup_" in d for d in deleted)


class TestBackupMetadata:
    """测试备份元数据"""

    def test_creation(self):
        """测试创建元数据"""
        metadata = BackupMetadata(
            backup_id="test_123",
            name="Test Backup",
            description="Test description",
            created_at=datetime.now().isoformat(),
            neko_version="1.0.0",
            auto_backup=False,
            size=1024,
        )

        assert metadata.backup_id == "test_123"
        assert metadata.name == "Test Backup"
        assert metadata.size == 1024

    def test_to_dict(self):
        """测试转换为字典"""
        metadata = BackupMetadata(
            backup_id="test_123",
            name="Test Backup",
            description="Test description",
            created_at="2024-01-01T00:00:00",
            neko_version="1.0.0",
            auto_backup=False,
            size=1024,
        )

        data = metadata.to_dict()

        assert data["backup_id"] == "test_123"
        assert data["name"] == "Test Backup"
        assert data["size"] == 1024

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "backup_id": "test_123",
            "name": "Test Backup",
            "description": "Test description",
            "created_at": "2024-01-01T00:00:00",
            "neko_version": "1.0.0",
            "auto_backup": False,
            "size": 1024,
            "manifest_version": BACKUP_MANIFEST_VERSION,
            "files": [],
            "tables": {},
            "directories": {},
        }

        metadata = BackupMetadata.from_dict(data)

        assert metadata.backup_id == "test_123"
        assert metadata.name == "Test Backup"


class TestBackupManifest:
    """测试备份清单"""

    def test_creation(self):
        """测试创建清单"""
        manifest = BackupManifest(
            version=BACKUP_MANIFEST_VERSION,
            neko_version="1.0.0",
            created_at=datetime.now().isoformat(),
            size=2048,
            checksums={},
            tables={},
            directories={},
            files=[],
        )

        assert manifest.version == BACKUP_MANIFEST_VERSION
        assert manifest.neko_version == "1.0.0"
        assert manifest.size == 2048

    def test_to_dict_and_from_dict(self):
        """测试序列化和反序列化"""
        manifest = BackupManifest(
            version=BACKUP_MANIFEST_VERSION,
            neko_version="1.0.0",
            created_at="2024-01-01T00:00:00",
            size=2048,
            checksums={"file.json": "abc123"},
            tables={"users": 10},
            directories={"config": {"count": 5}},
            files=["file.json"],
        )

        data = manifest.to_dict()
        restored = BackupManifest.from_dict(data)

        assert restored.version == manifest.version
        assert restored.neko_version == manifest.neko_version
        assert restored.size == manifest.size


class TestBackupExporter:
    """测试备份导出器"""

    @pytest.mark.asyncio
    async def test_export_main_database(self, path_manager, sample_database):
        """测试导出主数据库"""
        exporter = BackupExporter(path_manager)
        backup_dir = path_manager.paths.temp_dir / "test_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        tables_stats = await exporter._export_main_database(backup_dir)

        assert "users" in tables_stats
        assert tables_stats["users"] == 1
        assert "platforms" in tables_stats
        assert tables_stats["platforms"] == 1

        users_json = backup_dir / "databases" / "users.json"
        assert users_json.exists()

    @pytest.mark.asyncio
    async def test_export_config_files(self, path_manager, sample_config):
        """测试导出配置文件"""
        exporter = BackupExporter(path_manager)
        backup_dir = path_manager.paths.temp_dir / "test_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        files = await exporter._export_config_files(backup_dir)

        assert len(files) == 1
        assert "config/test_config.json" in files

        backup_config = backup_dir / "config" / "test_config.json"
        assert backup_config.exists()

    @pytest.mark.asyncio
    async def test_full_export(self, path_manager, sample_database, sample_config):
        """测试完整导出"""
        exporter = BackupExporter(path_manager)

        result = await exporter.export(
            backup_name="Test Backup",
            backup_description="Test backup",
        )

        assert result.success
        assert result.backup_id
        assert result.size > 0
        assert "users" in result.tables

        backup_dir = path_manager.get_backup_dir(result.backup_id)
        assert backup_dir.exists()

        metadata_file = path_manager.get_backup_metadata_file(result.backup_id)
        assert metadata_file.exists()

        with open(metadata_file, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            assert metadata["name"] == "Test Backup"
            assert metadata["neko_version"]


class TestBackupImporter:
    """测试备份导入器"""

    @pytest.mark.asyncio
    async def test_pre_check_valid_backup(self, path_manager, sample_database):
        """测试预检查有效备份"""
        exporter = BackupExporter(path_manager)
        export_result = await exporter.export("Test Backup")

        importer = BackupImporter(path_manager)
        backup_dir = path_manager.get_backup_dir(export_result.backup_id)

        pre_check = await importer.pre_check_backup(backup_dir)

        assert pre_check.valid
        assert pre_check.can_import
        assert pre_check.backup_version
        assert "tables" in pre_check.backup_summary

    @pytest.mark.asyncio
    async def test_pre_check_invalid_backup(self, path_manager):
        """测试预检查无效备份"""
        importer = BackupImporter(path_manager)
        fake_backup = path_manager.paths.temp_dir / "fake_backup"
        fake_backup.mkdir(parents=True, exist_ok=True)

        pre_check = await importer.pre_check_backup(fake_backup)

        assert not pre_check.valid
        assert len(pre_check.errors) > 0

    @pytest.mark.asyncio
    async def test_restore_main_database(self, path_manager, sample_database):
        """测试恢复主数据库"""
        exporter = BackupExporter(path_manager)
        export_result = await exporter.export("Test Backup")

        backup_dir = path_manager.get_backup_dir(export_result.backup_id)

        importer = BackupImporter(path_manager)
        tables_restored = await importer._restore_main_database(backup_dir)

        assert "users" in tables_restored
        assert tables_restored["users"] > 0

    @pytest.mark.asyncio
    async def test_full_restore(self, path_manager, sample_database, sample_config):
        """测试完整恢复"""
        exporter = BackupExporter(path_manager)
        export_result = await exporter.export("Test Backup")

        backup_dir = path_manager.get_backup_dir(export_result.backup_id)

        importer = BackupImporter(path_manager)
        restore_result = await importer.restore(backup_dir)

        assert restore_result.success
        assert restore_result.tables_restored
        assert restore_result.files_restored


class TestBackupIntegration:
    """测试备份集成"""

    @pytest.mark.asyncio
    async def test_export_restore_cycle(
        self, path_manager, sample_database, sample_config
    ):
        """测试导出-恢复循环"""
        original_users_count = 0
        conn = sqlite3.connect(sample_database)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        original_users_count = cursor.fetchone()[0]
        conn.close()

        exporter = BackupExporter(path_manager)
        export_result = await exporter.export("Test Backup")

        assert export_result.success
        assert export_result.backup_id

        backup_dir = path_manager.get_backup_dir(export_result.backup_id)

        importer = BackupImporter(path_manager)
        restore_result = await importer.restore(backup_dir)

        assert restore_result.success
        assert "users" in restore_result.tables_restored
        assert restore_result.tables_restored["users"] == original_users_count

    @pytest.mark.asyncio
    async def test_zip_export_restore(
        self, path_manager, sample_database, sample_config
    ):
        """测试ZIP导出和恢复"""
        exporter = BackupExporter(path_manager)
        export_result = await exporter.export("Test Backup")

        backup_dir = path_manager.get_backup_dir(export_result.backup_id)

        zip_path = path_manager.paths.temp_dir / "backup.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in backup_dir.rglob("*"):
                if item.is_file():
                    arcname = item.relative_to(backup_dir)
                    zf.write(item, arcname)

        importer = BackupImporter(path_manager)
        pre_check = await importer.pre_check_backup(zip_path)

        assert pre_check.valid
        assert pre_check.can_import

        restore_result = await importer.restore(zip_path)

        assert restore_result.success

    @pytest.mark.asyncio
    async def test_progress_callback(self, path_manager, sample_database):
        """测试进度回调"""
        progress_updates = []

        async def progress_callback(stage, current, total, message):
            progress_updates.append(
                {
                    "stage": stage,
                    "current": current,
                    "total": total,
                    "message": message,
                }
            )

        exporter = BackupExporter(path_manager)
        export_result = await exporter.export(
            "Test Backup",
            progress_callback=progress_callback,
        )

        assert export_result.success
        assert len(progress_updates) > 0

        stages = [update["stage"] for update in progress_updates]
        assert "initialization" in stages
        assert "main_database" in stages
        assert "manifest" in stages
        assert "finalization" in stages


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
