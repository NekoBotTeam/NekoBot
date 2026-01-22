"""配置验证器单元测试

测试 P0: 配置 Schema 验证功能
"""

import pytest
import json
import tempfile
from pathlib import Path

from packages.config.validator import (
    ConfigValidator,
    get_validator,
    ConfigValidationError
)


class TestConfigValidator:
    """测试配置验证器"""

    @pytest.fixture
    def validator(self):
        """创建验证器实例"""
        return ConfigValidator()

    @pytest.fixture
    def sample_schema(self):
        """示例 Schema"""
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer", "minimum": 0, "maximum": 150},
                "email": {"type": "string", "format": "email"},
                "enabled": {"type": "boolean"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                        "city": {"type": "string"}
                    },
                    "required": ["street", "city"]
                }
            },
            "required": ["name", "age"]
        }

    def test_register_schema(self, validator, sample_schema):
        """测试注册 Schema"""
        validator.register_schema("user_config", sample_schema)

        assert "user_config" in validator._schemas
        assert validator._schemas["user_config"] == sample_schema

    def test_register_schema_from_file(self, validator):
        """测试从文件注册 Schema"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            schema = {
                "type": "object",
                "properties": {
                    "test": {"type": "string"}
                }
            }
            json.dump(schema, f)
            temp_path = f.name

        try:
            validator.register_schema_from_file("test_schema", temp_path)
            assert "test_schema" in validator._schemas
        finally:
            Path(temp_path).unlink()

    def test_validate_valid_config(self, validator, sample_schema):
        """测试验证有效配置"""
        validator.register_schema("user_config", sample_schema)

        valid_config = {
            "name": "Alice",
            "age": 30,
            "email": "alice@example.com",
            "enabled": True,
            "tags": ["developer", "python"],
            "address": {
                "street": "123 Main St",
                "city": "New York"
            }
        }

        result = validator.validate(valid_config, "user_config")

        assert result is True

    def test_validate_invalid_config_missing_required(self, validator, sample_schema):
        """测试验证缺少必填字段的配置"""
        validator.register_schema("user_config", sample_schema)

        invalid_config = {
            "name": "Alice"
            # 缺少 age (必填)
        }

        with pytest.raises(ConfigValidationError):
            validator.validate(invalid_config, "user_config")

    def test_validate_invalid_config_type_mismatch(self, validator, sample_schema):
        """测试验证类型不匹配的配置"""
        validator.register_schema("user_config", sample_schema)

        invalid_config = {
            "name": "Alice",
            "age": "thirty"  # 应该是 integer
        }

        with pytest.raises(ConfigValidationError):
            validator.validate(invalid_config, "user_config")

    def test_validate_invalid_config_out_of_range(self, validator, sample_schema):
        """测试验证超出范围的配置"""
        validator.register_schema("user_config", sample_schema)

        invalid_config = {
            "name": "Alice",
            "age": 200  # 超过 maximum 150
        }

        with pytest.raises(ConfigValidationError):
            validator.validate(invalid_config, "user_config")

    def test_validate_nested_object(self, validator, sample_schema):
        """测试验证嵌套对象"""
        validator.register_schema("user_config", sample_schema)

        invalid_config = {
            "name": "Alice",
            "age": 30,
            "address": {
                "street": "123 Main St"
                # 缺少 city (必填)
            }
        }

        with pytest.raises(ConfigValidationError):
            validator.validate(invalid_config, "user_config")

    def test_validate_array_items(self, validator, sample_schema):
        """测试验证数组项"""
        validator.register_schema("user_config", sample_schema)

        invalid_config = {
            "name": "Alice",
            "age": 30,
            "tags": [1, 2, 3]  # 应该是字符串数组
        }

        with pytest.raises(ConfigValidationError):
            validator.validate(invalid_config, "user_config")

    def test_validate_value_by_path(self, validator, sample_schema):
        """测试按路径验证单个值"""
        validator.register_schema("user_config", sample_schema)

        # 有效值
        result = validator.validate_value(
            25,  # value
            "user_config",  # schema_name
            "age"  # property_path
        )
        assert result is True

        # 无效值（超出范围）
        with pytest.raises(ConfigValidationError):
            validator.validate_value(
                200,  # value
                "user_config",  # schema_name
                "age"  # property_path
            )

    def test_unregister_schema(self, validator, sample_schema):
        """测试注销 Schema"""
        validator.register_schema("user_config", sample_schema)

        assert "user_config" in validator._schemas

        validator.unregister_schema("user_config")

        assert "user_config" not in validator._schemas

    def test_list_schemas(self, validator):
        """测试列出所有 Schema"""
        validator.register_schema("schema1", {"type": "object"})
        validator.register_schema("schema2", {"type": "object"})

        schemas = validator.list_schemas()

        assert "schema1" in schemas
        assert "schema2" in schemas

    def test_get_schema(self, validator):
        """测试获取 Schema"""
        schema = {"type": "object"}
        validator.register_schema("test_schema", schema)

        result = validator.get_schema("test_schema")

        assert result == schema


class TestConfigValidatorIntegration:
    """集成测试"""

    def test_validate_with_default_values(self):
        """测试带默认值的验证"""
        validator = ConfigValidator()

        schema_with_defaults = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "Anonymous"},
                "count": {"type": "integer", "default": 0},
                "enabled": {"type": "boolean", "default": True}
            }
        }

        validator.register_schema("config_with_defaults", schema_with_defaults)

        # 空配置应该通过验证（使用默认值）
        result = validator.validate({}, "config_with_defaults")

        assert result is True

    def test_validate_complex_schema(self):
        """测试复杂 Schema 验证"""
        validator = ConfigValidator()

        complex_schema = {
            "type": "object",
            "properties": {
                "users": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "profile": {
                                "type": "object",
                                "properties": {
                                    "bio": {"type": "string"},
                                    "skills": {
                                        "type": "array",
                                        "items": {"type": "string"}
                                    }
                                }
                            }
                        },
                        "required": ["id"]
                    }
                }
            },
            "required": ["users"]
        }

        validator.register_schema("complex_config", complex_schema)

        valid_config = {
            "users": [
                {
                    "id": "user1",
                    "profile": {
                        "bio": "Developer",
                        "skills": ["python", "javascript"]
                    }
                }
            ]
        }

        result = validator.validate(valid_config, "complex_config")

        assert result is True


class TestGlobalValidator:
    """测试全局验证器"""

    def test_get_validator_singleton(self):
        """测试获取单例验证器"""
        validator1 = get_validator()
        validator2 = get_validator()

        assert validator1 is validator2

    def test_global_validator_register_and_validate(self):
        """测试全局验证器注册和验证"""
        validator = get_validator()

        schema = {
            "type": "object",
            "properties": {
                "value": {"type": "number"}
            },
            "required": ["value"]
        }

        validator.register_schema("test", schema)

        config = {"value": 42}
        result = validator.validate(config, "test")

        assert result is True


class TestConfigValidationError:
    """测试配置验证错误类"""

    def test_error_creation(self):
        """测试创建错误对象"""
        error = ConfigValidationError("验证失败")

        assert str(error) == "验证失败"
        assert error.errors == []

    def test_error_with_errors_list(self):
        """测试带错误列表的错误对象"""
        error = ConfigValidationError(
            "配置验证失败",
            errors=["字段 age 无效", "字段 email 格式错误"]
        )

        assert len(error.errors) == 2
        assert "字段 age 无效" in error.errors

    def test_error_str_representation(self):
        """测试错误的字符串表示"""
        error = ConfigValidationError(
            "配置验证失败",
            errors=["错误1", "错误2"]
        )

        error_str = str(error)

        assert "配置验证失败" in error_str
