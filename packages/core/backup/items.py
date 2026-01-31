"""备份项定义

使用装饰器定义所有备份项
"""

import json
import sqlite3
import shutil
from pathlib import Path
from loguru import logger

from .config import BackupRegistry, BackupContext


@BackupRegistry.register("main_database", "主数据库", priority=10)
async def export_main_database(backup_dir: Path, context: BackupContext):
    """导出主数据库"""
    db_path = context.path_manager.paths.database_path

    if not db_path.exists():
        logger.warning("数据库文件不存在")
        return

    databases_dir = backup_dir / "databases"
    databases_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
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

            table_json = json.dumps(data, ensure_ascii=False, default=str, indent=2)
            output_path = databases_dir / f"{table_name}.json"

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(table_json)

            logger.info(f"导出表 {table_name}: {count} 条记录")

    conn.close()


@BackupRegistry.register("main_database", "主数据库", priority=10)
async def import_main_database(backup_dir: Path, context: BackupContext):
    """导入主数据库"""
    db_path = context.path_manager.paths.database_path
    databases_dir = backup_dir / "databases"

    if not databases_dir.exists():
        logger.warning("备份数据库目录不存在")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for table_file in databases_dir.glob("*.json"):
        table_name = table_file.stem
        if table_name.startswith("sqlite_"):
            continue

        with open(table_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not data:
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

        logger.info(f"恢复表 {table_name}: {len(data)} 条记录")

    conn.commit()
    conn.close()


@BackupRegistry.register("config_files", "配置文件", priority=20)
async def export_config_files(backup_dir: Path, context: BackupContext):
    """导出配置文件"""
    config_dir = context.path_manager.paths.config_dir

    if not config_dir.exists():
        logger.info("配置目录不存在")
        return

    backup_config_dir = backup_dir / "config"
    backup_config_dir.mkdir(parents=True, exist_ok=True)

    for config_file in config_dir.glob("*.json"):
        backup_path = backup_config_dir / config_file.name

        with open(config_file, "r", encoding="utf-8") as f:
            content = f.read()

        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"导出配置文件: {config_file.name}")


@BackupRegistry.register("config_files", "配置文件", priority=20)
async def import_config_files(backup_dir: Path, context: BackupContext):
    """导入配置文件"""
    backup_config_dir = backup_dir / "config"

    if not backup_config_dir.exists():
        logger.info("备份配置目录不存在")
        return

    config_dir = context.path_manager.paths.config_dir
    config_dir.mkdir(parents=True, exist_ok=True)

    for config_file in backup_config_dir.glob("*.json"):
        dest_path = config_dir / config_file.name

        shutil.copy2(config_file, dest_path)
        logger.info(f"恢复配置文件: {config_file.name}")


@BackupRegistry.register("plugins", "插件目录", priority=30)
async def export_plugins(backup_dir: Path, context: BackupContext):
    """导出插件目录"""
    plugins_dir = context.path_manager.paths.plugins_dir

    if not plugins_dir.exists():
        logger.info("插件目录不存在")
        return

    backup_plugins_dir = backup_dir / "plugins"
    backup_plugins_dir.mkdir(parents=True, exist_ok=True)

    for file_path in plugins_dir.rglob("*"):
        if file_path.is_file():
            if any(
                pattern in str(file_path)
                for pattern in ["__pycache__", "*.pyc", ".DS_Store"]
            ):
                continue

            relative_path = file_path.relative_to(plugins_dir)
            backup_path = backup_plugins_dir / relative_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(file_path, backup_path)

    logger.info("插件目录导出完成")


@BackupRegistry.register("plugins", "插件目录", priority=30)
async def import_plugins(backup_dir: Path, context: BackupContext):
    """导入插件目录"""
    backup_plugins_dir = backup_dir / "plugins"

    if not backup_plugins_dir.exists():
        logger.info("备份插件目录不存在")
        return

    plugins_dir = context.path_manager.paths.plugins_dir
    plugins_dir.mkdir(parents=True, exist_ok=True)

    if plugins_dir.exists():
        shutil.rmtree(plugins_dir)

    shutil.copytree(backup_plugins_dir, plugins_dir)
    logger.info("插件目录导入完成")


@BackupRegistry.register("conversations", "对话目录", priority=40)
async def export_conversations(backup_dir: Path, context: BackupContext):
    """导出对话目录"""
    conversations_dir = context.path_manager.paths.conversations_dir

    if not conversations_dir.exists():
        logger.info("对话目录不存在")
        return

    backup_conversations_dir = backup_dir / "conversations"
    backup_conversations_dir.mkdir(parents=True, exist_ok=True)

    shutil.copytree(conversations_dir, backup_conversations_dir, dirs_exist_ok=True)
    logger.info("对话目录导出完成")


@BackupRegistry.register("conversations", "对话目录", priority=40)
async def import_conversations(backup_dir: Path, context: BackupContext):
    """导入对话目录"""
    backup_conversations_dir = backup_dir / "conversations"

    if not backup_conversations_dir.exists():
        logger.info("备份对话目录不存在")
        return

    conversations_dir = context.path_manager.paths.conversations_dir
    conversations_dir.mkdir(parents=True, exist_ok=True)

    if conversations_dir.exists():
        shutil.rmtree(conversations_dir)

    shutil.copytree(backup_conversations_dir, conversations_dir)
    logger.info("对话目录导入完成")


@BackupRegistry.register("knowledge_base", "知识库", priority=50)
async def export_knowledge_base(backup_dir: Path, context: BackupContext):
    """导出知识库"""
    kb_manager = context.metadata.get("kb_manager")

    if not kb_manager:
        logger.info("知识库管理器未初始化，跳过知识库导出")
        return

    knowledge_bases = await kb_manager.list_knowledge_bases()

    backup_kb_dir = backup_dir / "knowledge_base"
    backup_kb_dir.mkdir(parents=True, exist_ok=True)

    for kb in knowledge_bases:
        kb_dir = backup_kb_dir / kb.id
        kb_dir.mkdir(parents=True, exist_ok=True)

        kb_json = json.dumps(kb.to_dict(), ensure_ascii=False, indent=2)
        with open(kb_dir / "metadata.json", "w", encoding="utf-8") as f:
            f.write(kb_json)

        logger.info(f"导出知识库: {kb.name} ({kb.id})")

    logger.info(f"知识库导出完成，共 {len(knowledge_bases)} 个知识库")


@BackupRegistry.register("knowledge_base", "知识库", priority=50)
async def import_knowledge_base(backup_dir: Path, context: BackupContext):
    """导入知识库"""
    kb_manager = context.metadata.get("kb_manager")

    if not kb_manager:
        logger.info("知识库管理器未初始化，跳过知识库导入")
        return

    backup_kb_dir = backup_dir / "knowledge_base"

    if not backup_kb_dir.exists():
        logger.info("备份知识库目录不存在")
        return

    kb_dirs = [d for d in backup_kb_dir.iterdir() if d.is_dir()]

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

        await kb_manager.create_knowledge_base(
            kb_id=kb.id,
            name=kb.name,
            description=kb.description,
            embedding_model=kb.embedding_model,
        )

        logger.info(f"恢复知识库: {kb.name} ({kb.id})")

    logger.info(f"知识库导入完成")


__all__ = []
