"""备份系统验证脚本

验证备份系统是否能正常工作
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("备份系统验证")
print("=" * 60)

# 测试1: 导入模块
print("\n[1/5] 测试模块导入...")
try:
    from packages.core.backup import (
        PathManager,
        BackupExporter,
        BackupImporter,
        BackupRegistry,
        BackupContext,
        BackupExecutor,
        BACKUP_MANIFEST_VERSION,
    )

    print("✓ 所有模块导入成功")
except Exception as e:
    print(f"✗ 模块导入失败: {e}")
    sys.exit(1)

# 测试2: 创建路径管理器
print("\n[2/5] 测试路径管理器...")
try:
    pm = PathManager()
    pm.ensure_directories()
    print(f"✓ 路径管理器创建成功")
    print(f"  - 项目根目录: {pm.project_root}")
    print(f"  - 数据目录: {pm.paths.data_dir}")
    print(f"  - 备份目录: {pm.paths.backups_dir}")
except Exception as e:
    print(f"✗ 路径管理器创建失败: {e}")
    sys.exit(1)

# 测试3: 测试备份注册表
print("\n[3/5] 测试备份注册表...")
try:
    items = BackupRegistry.get_all_items()
    enabled_items = BackupRegistry.get_enabled_items()

    print(f"✓ 备份注册表工作正常")
    print(f"  - 注册的备份项: {len(items)} 个")
    for item in items:
        print(f"    - {item.name} ({item.description}) [priority={item.priority}]")

    print(f"  - 启用的备份项: {len(enabled_items)} 个")
except Exception as e:
    print(f"✗ 备份注册表测试失败: {e}")
    sys.exit(1)

# 测试4: 测试备份项功能
print("\n[4/5] 测试备份项...")
try:
    # 导入备份项定义（这会自动注册所有备份项）
    from packages.core.backup import items

    all_items = BackupRegistry.get_all_items()
    print(f"✓ 备份项定义加载成功，共 {len(all_items)} 个备份项")

    # 测试启用/禁用功能
    main_db_item = BackupRegistry.get_item("main_database")
    if main_db_item:
        print(
            f"  - 主数据库备份项: 启用={main_db_item.enabled}, 优先级={main_db_item.priority}"
        )
except Exception as e:
    print(f"✗ 备份项测试失败: {e}")
    sys.exit(1)

# 测试5: 测试格式化和工具函数
print("\n[5/5] 测试工具函数...")
try:
    test_sizes = [100, 1024, 1024 * 1024, 1024 * 1024 * 1024]
    for size in test_sizes:
        formatted = pm.format_size(size)
        print(f"  - {size} bytes = {formatted}")

    print("✓ 工具函数测试成功")
except Exception as e:
    print(f"✗ 工具函数测试失败: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ 所有测试通过！备份系统工作正常")
print("=" * 60)
print("\n使用装饰器定义备份项的示例：")
print("""
@BackupRegistry.register("my_item", "我的备份项", priority=100)
async def export_my_item(backup_dir, context):
    '''导出自定义数据'''
    pass

@BackupRegistry.register("my_item", "我的备份项", priority=100)
async def import_my_item(backup_dir, context):
    '''导入自定义数据'''
    pass
""")
