"""命令冲突解决功能测试

这个测试脚本用于验证命令冲突解决功能是否正常工作。
"""

import sys
import importlib.util
from pathlib import Path

module_path = Path(__file__).parent.parent / "packages/core/command_management.py"

spec = importlib.util.spec_from_file_location(
    "command_management",
    str(module_path),
)

if spec and spec.loader:
    command_management = importlib.util.module_from_spec(spec)
    sys.modules["command_management"] = command_management
    spec.loader.exec_module(command_management)

    register_command = command_management.register_command
    get_conflicting_handlers = command_management.get_conflicting_handlers
    ConflictResolutionStrategy = command_management.ConflictResolutionStrategy
    resolve_command_conflict = command_management.resolve_command_conflict
    list_command_conflicts = command_management.list_command_conflicts
    get_resolved_conflicts = command_management.get_resolved_conflicts
    clear_all_conflicts = command_management.clear_all_conflicts
    _command_registry = command_management._command_registry
else:
    raise ImportError("无法加载command_management模块")


def test_command_conflict_resolution():
    """测试命令冲突解决功能"""

    print("=== 开始测试命令冲突解决功能 ===\n")

    # 清空注册表
    _command_registry.clear()

    # 注册两个冲突的命令
    print("1. 注册两个冲突的命令...")
    cmd1 = register_command(
        handler_full_name="plugin1.test_command",
        handler_name="test",
        plugin_name="plugin1",
        module_path="plugin1.commands",
        description="Plugin 1 test command",
    )

    cmd2 = register_command(
        handler_full_name="plugin2.test_command",
        handler_name="test",
        plugin_name="plugin2",
        module_path="plugin2.commands",
        description="Plugin 2 test command",
    )

    print(f"   - 注册命令1: {cmd1.handler_full_name} -> {cmd1.effective_command}")
    print(f"   - 注册命令2: {cmd2.handler_full_name} -> {cmd2.effective_command}")

    # 检测冲突
    print("\n2. 检测命令冲突...")
    conflicts = list_command_conflicts()
    print(f"   - 发现 {len(conflicts)} 个冲突")
    if conflicts:
        for conflict in conflicts:
            print(f"   - 冲突命令: {conflict['conflict_key']}")
            print(f"     冲突处理器数量: {len(conflict['handlers'])}")

    # 获取冲突的处理器
    print("\n3. 获取冲突的处理器...")
    handlers = get_conflicting_handlers("test")
    print(f"   - 找到 {len(handlers)} 个处理器")
    for i, h in enumerate(handlers):
        print(f"   - 处理器 {i + 1}: {h.plugin_name} -> {h.effective_command}")

    # 解决冲突 (保留第一个命令)
    print("\n4. 解决冲突 (保留第一个命令)...")
    try:
        import asyncio

        result = asyncio.run(
            resolve_command_conflict(
                conflict_key="test",
                resolution_strategy=ConflictResolutionStrategy.KEEP_FIRST,
                keep_handler_full_name="plugin1.test_command",
            )
        )
        print(f"   - 冲突已解决")
        print(f"   - 保留命令: {result['keep_handler']} -> {result['alias_name']}")
        print(f"   - 别名命令: {result['alias_handler']} -> {result['alias_name']}")
    except Exception as e:
        print(f"   - 解决冲突失败: {e}")

    # 验证解决后的状态
    print("\n5. 验证解决后的状态...")
    cmd1_updated = _command_registry.get("plugin1.test_command")
    cmd2_updated = _command_registry.get("plugin2.test_command")

    if cmd1_updated and cmd2_updated:
        print(
            f"   - 命令1: {cmd1_updated.plugin_name} -> {cmd1_updated.effective_command}"
        )
        print(
            f"   - 命令2: {cmd2_updated.plugin_name} -> {cmd2_updated.effective_command}"
        )
        print(f"   - 命令2别名: {cmd2_updated.aliases}")

    # 检查已解决的冲突记录
    print("\n6. 检查已解决的冲突记录...")
    resolved = get_resolved_conflicts()
    print(f"   - 已解决的冲突数量: {len(resolved)}")
    if resolved:
        for r in resolved:
            print(
                f"   - 冲突: {r['conflict_key']}, 策略: {r['resolution_strategy']}, 解决时间: {r['resolved_at']}"
            )

    # 清空已解决的冲突
    print("\n7. 清空已解决的冲突...")
    import asyncio

    count = asyncio.run(clear_all_conflicts())
    print(f"   - 已清除 {count} 个冲突记录")

    # 验证清除后的状态
    print("\n8. 验证清除后的状态...")
    resolved = get_resolved_conflicts()
    print(f"   - 已解决的冲突数量: {len(resolved)}")

    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    test_command_conflict_resolution()
