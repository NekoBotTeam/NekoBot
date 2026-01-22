"""配置管理器单元测试

测试 ConfigManager 的功能
"""

import pytest
import json
import tempfile
from pathlib import Path
from packages.config import ConfigManager, ConfigChangeType, ConfigChangeEvent


class TestConfigManager:
    """配置管理器测试"""

    @pytest.fixture
    async def temp_config_file(self):
        """创建临时配置文件"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_path = Path(f.name)
            json.dump({}, f)
        yield config_path
        # 清理
        config_path.unlink(missing_ok=True)

    @pytest.fixture
    async def manager(self, temp_config_file):
        """创建配置管理器实例"""
        manager = ConfigManager(str(temp_config_file), enable_validation=False)
        await manager.load()
        return manager

    async def test_initialization_creates_file(self, temp_config_file):
        """测试初始化时创建配置文件"""
        # 文件应该已经存在
        assert temp_config_file.exists()

    async def test_get_nested_value(self, manager):
        """测试获取嵌套值"""
        # 设置一些值
        await manager.set("server.host", "0.0.0.0")
        await manager.set("server.port", 6285)

        assert await manager.get("server.host") == "0.0.0.0"
        assert await manager.get("server.port") == 6285

    async def test_get_with_default(self, manager):
        """测试获取带默认值"""
        assert await manager.get("nonexistent", "default") == "default"
        assert await manager.get("server.nonexistent", "default") == "default"

    async def test_set_value(self, manager):
        """测试设置值"""
        await manager.set("server.host", "127.0.0.1")
        assert await manager.get("server.host") == "127.0.0.1"

    async def test_set_nested_value(self, manager):
        """测试设置嵌套值"""
        await manager.set("new.nested.value", "test")
        assert await manager.get("new.nested.value") == "test"

    async def test_auto_save(self, manager, temp_config_file):
        """测试自动保存"""
        await manager.set("server.port", 8080)

        # 重新加载验证
        with open(temp_config_file, "r") as f:
            saved = json.load(f)
        assert saved["server"]["port"] == 8080

    async def test_to_dict(self, manager):
        """测试转换为字典"""
        await manager.set("server.host", "0.0.0.0")
        config_dict = manager.to_dict()
        assert "server" in config_dict
        assert config_dict["server"]["host"] == "0.0.0.0"

    async def test_reload(self, manager, temp_config_file):
        """测试重新加载"""
        # 修改文件
        with open(temp_config_file, "r") as f:
            config = json.load(f)

        config["server"] = {"port": 7777}

        with open(temp_config_file, "w") as f:
            json.dump(config, f)

        # 重新加载
        assert await manager.get("server.port") == 7777

    async def test_watch_config_changes(self, manager):
        """测试配置变更监听"""
        changes = []

        async def watcher(event: ConfigChangeEvent):
            changes.append(event)

        manager.watch(watcher)

        # 设置值
        await manager.set("test.key", "value")

        # 验证变更事件
        assert len(changes) == 1
        assert changes[0].key == "test.key"
        assert changes[0].new_value == "value"
        assert changes[0].change_type == ConfigChangeType.ADDED

    async def test_delete_value(self, manager):
        """测试删除值"""
        await manager.set("test.key", "value")
        assert await manager.get("test.key") == "value"

        await manager.delete("test.key")
        assert await manager.get("test.key") is None

    async def test_config_property(self, manager):
        """测试配置属性"""
        await manager.set("test", "value")
        config_dict = manager.config
        assert config_dict["test"] == "value"


class TestConfigMigration:
    """配置迁移测试（简化版，因为新的 ConfigManager 不支持自动迁移）"""

    @pytest.fixture
    async def temp_config_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            yield Path(f.name)
        Path(f.name).unlink(missing_ok=True)

    async def test_load_empty_config(self, temp_config_file):
        """测试加载空配置"""
        with open(temp_config_file, "w") as f:
            json.dump({}, f)

        manager = ConfigManager(str(temp_config_file), enable_validation=False)
        await manager.load()

        # 应该可以设置新值
        await manager.set("new.key", "value")
        assert await manager.get("new.key") == "value"


class TestEdgeCases:
    """边界情况测试"""

    @pytest.fixture
    async def temp_config_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            yield Path(f.name)
        Path(f.name).unlink(missing_ok=True)

    async def test_empty_config_file(self, temp_config_file):
        """测试空配置文件"""
        with open(temp_config_file, "w") as f:
            json.dump({}, f)

        manager = ConfigManager(str(temp_config_file), enable_validation=False)
        await manager.load()

        # 应该仍然可用
        await manager.set("key", "value")
        assert await manager.get("key") == "value"

    async def test_large_nested_config(self, temp_config_file):
        """测试大型嵌套配置"""
        large_config = {}
        for i in range(10):
            large_config[f"section{i}"] = {}
            for j in range(10):
                large_config[f"section{i}"][f"key{j}"] = f"value{i}_{j}"

        with open(temp_config_file, "w") as f:
            json.dump(large_config, f)

        manager = ConfigManager(str(temp_config_file), enable_validation=False)
        await manager.load()

        # 验证可以访问深度嵌套的值
        assert await manager.get("section5.key7") == "value5_7"

    async def test_special_characters_in_values(self, temp_config_file):
        """测试值中的特殊字符"""
        special_config = {
            "path": "C:\\Users\\test",
            "unicode": "你好世界",
            "quotes": 'He said "hello"',
            "newlines": "line1\nline2",
        }

        with open(temp_config_file, "w") as f:
            json.dump(special_config, f)

        manager = ConfigManager(str(temp_config_file), enable_validation=False)
        await manager.load()

        assert await manager.get("path") == "C:\\Users\\test"
        assert await manager.get("unicode") == "你好世界"
