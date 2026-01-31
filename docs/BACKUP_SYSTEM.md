# 备份系统文档

## 概述

NekoBot 的备份系统提供灵活的数据备份和恢复功能。系统使用装饰器来定义备份项，使配置更加灵活和可扩展。

## 架构

### 核心组件

1. **PathManager** - 路径管理器，统一管理所有路径
2. **BackupExporter** - 备份导出器
3. **BackupImporter** - 备份导入器
4. **BackupRegistry** - 备份项注册表
5. **BackupExecutor** - 备份执行器

### 备份项系统

使用装饰器 `@BackupRegistry.register()` 定义备份项：

```python
from packages.core.backup.config import BackupRegistry

@BackupRegistry.register("main_database", "主数据库", priority=10)
async def export_main_database(backup_dir, context):
    """导出主数据库"""
    pass

@BackupRegistry.register("main_database", "主数据库", priority=10)
async def import_main_database(backup_dir, context):
    """导入主数据库"""
    pass
```

## 使用方式

### 基本使用

```python
from packages.core.backup import BackupExporter, BackupImporter, PathManager
from packages.core.backup.config import BackupContext, BackupExecutor

# 创建路径管理器
path_manager = PathManager()
path_manager.ensure_directories()

# 创建备份上下文
context = BackupContext(
    backup_dir=path_manager.get_backup_dir("test_backup"),
    path_manager=path_manager,
    progress_callback=lambda stage, current, total, message: print(f"[{stage}] {current}/{total}: {message}")
)

# 导出备份
exporter = BackupExporter(path_manager)
result = await exporter.export(
    backup_name="测试备份",
    backup_description="这是一个测试备份"
)

# 导入备份
importer = BackupImporter(path_manager)
result = await importer.restore(
    backup_path=path_manager.get_backup_dir("test_backup"),
    force=False
)
```

### 使用装饰器定义备份项

```python
# 在 items.py 中定义
@BackupRegistry.register("my_custom_item", "自定义备份项", priority=100)
async def export_my_custom_item(backup_dir, context):
    """导出自定义数据"""
    import json
    from pathlib import Path

    data = {"key": "value"}
    output_file = backup_dir / "custom_data.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@BackupRegistry.register("my_custom_item", "自定义备份项", priority=100)
async def import_my_custom_item(backup_dir, context):
    """导入自定义数据"""
    import json
    from pathlib import Path

    input_file = backup_dir / "custom_data.json"
    if not input_file.exists():
        return

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 处理导入的数据
    print(f"导入数据: {data}")
```

### 管理备份项

```python
from packages.core.backup.config import BackupRegistry

# 获取所有备份项
all_items = BackupRegistry.get_all_items()

# 获取启用的备份项
enabled_items = BackupRegistry.get_enabled_items()

# 禁用某个备份项
BackupRegistry.disable_item("plugins")

# 启用某个备份项
BackupRegistry.enable_item("plugins")
```

## API 接口

### 备份相关

#### 创建备份
```
POST /api/backups
Content-Type: application/json

{
  "name": "备份名称",
  "description": "备份描述",
  "auto_backup": false
}
```

#### 列出备份
```
GET /api/backups
```

#### 获取备份详情
```
GET /api/backups/{backup_id}
```

#### 删除备份
```
DELETE /api/backups/{backup_id}
```

#### 下载备份
```
GET /api/backups/{backup_id}/download
```

### 恢复相关

#### 预检查备份
```
GET /api/backups/{backup_id}/precheck
```

#### 恢复备份
```
POST /api/backups/{backup_id}/restore
Content-Type: application/json

{
  "force": false
}
```

### 设置相关

#### 获取备份设置
```
GET /api/backups/settings
```

#### 更新备份设置
```
POST /api/backups/settings
Content-Type: application/json

{
  "auto_backup_enabled": false,
  "auto_backup_interval": 7,
  "max_backups": 10,
  "auto_backup_time": "02:00"
}
```

## 备份内容

默认备份以下内容：

1. **主数据库** - users, platforms, 等所有表
2. **配置文件** - data/config/*.json
3. **插件目录** - data/plugins
4. **插件数据** - data/plugin_data
5. **对话数据** - data/conversations
6. **知识库** - data/knowledge_base
7. **临时文件** - data/temp

## 备份清单

每个备份包含以下文件：

- `manifest.json` - 备份清单
- `backup_metadata.json` - 备份元数据
- `databases/` - 数据库导出文件
- `config/` - 配置文件
- `plugins/` - 插件目录
- `plugin_data/` - 插件数据目录
- `conversations/` - 对话目录
- `knowledge_base/` - 知识库目录
- `attachments/` - 附件文件

## 扩展备份项

要添加新的备份项，只需使用 `@BackupRegistry.register()` 装饰器定义导出和导入函数：

```python
@BackupRegistry.register("my_item", "我的备份项", priority=50)
async def export_my_item(backup_dir: Path, context: BackupContext):
    """导出逻辑"""
    pass

@BackupRegistry.register("my_item", "我的备份项", priority=50)
async def import_my_item(backup_dir: Path, context: BackupContext):
    """导入逻辑"""
    pass
```

## 注意事项

1. **版本兼容性** - 备份恢复时会检查版本兼容性，主版本不同会拒绝导入
2. **备份清理** - 可以设置 `max_backups` 参数自动清理旧备份
3. **进度回调** - 导出/导入支持进度回调，可用于显示进度条
4. **强制恢复** - 设置 `force=true` 可以跳过版本检查强制恢复
5. **重启生效** - 恢复配置文件后需要重启应用才能生效

## 测试

运行单元测试：

```bash
pytest tests/test_backup.py -v
```

## 迁移指南

从旧版备份系统迁移：

1. 旧版备份使用目录结构，新版使用ZIP格式
2. 旧版元数据在 `backup_metadata.json`，新版保持兼容
3. 新版增加了 `manifest.json` 文件包含详细的备份信息
4. 新版支持装饰器定义备份项，更加灵活

## 最佳实践

1. **定期备份** - 建议每天自动备份一次
2. **异地备份** - 将备份文件保存到云存储
3. **测试恢复** - 定期测试备份恢复功能
4. **监控备份** - 监控备份成功/失败状态
5. **清理旧备份** - 设置合理的最大备份数量
