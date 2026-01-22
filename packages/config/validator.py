"""配置 Schema 验证器

提供基于 JSON Schema 的配置验证功能
"""

from pathlib import Path
from typing import Any, Optional, Dict, List
from loguru import logger
import json


class ConfigValidationError(Exception):
    """配置验证错误"""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or []


class ConfigValidator:
    """配置验证器

    使用 JSON Schema 验证配置文件
    """

    def __init__(self):
        self._schemas: Dict[str, dict] = {}
        self._schema_dir: Optional[Path] = None

    def load_schema_from_file(self, schema_path: str) -> dict:
        """从文件加载 Schema

        Args:
            schema_path: Schema 文件路径

        Returns:
            Schema 字典

        Raises:
            ConfigValidationError: 加载失败
        """
        try:
            schema_file = Path(schema_path)
            if not schema_file.exists():
                raise ConfigValidationError(f"Schema 文件不存在: {schema_path}")

            with open(schema_file, "r", encoding="utf-8") as f:
                schema = json.load(f)

            logger.debug(f"已加载 Schema: {schema_path}")
            return schema

        except json.JSONDecodeError as e:
            raise ConfigValidationError(f"Schema JSON 解析失败: {e}")
        except Exception as e:
            raise ConfigValidationError(f"加载 Schema 失败: {e}")

    def register_schema(self, name: str, schema: dict) -> None:
        """注册 Schema

        Args:
            name: Schema 名称
            schema: Schema 字典
        """
        self._schemas[name] = schema
        logger.debug(f"已注册 Schema: {name}")

    def register_schema_from_file(self, name: str, schema_path: str) -> None:
        """从文件注册 Schema

        Args:
            name: Schema 名称
            schema_path: Schema 文件路径
        """
        schema = self.load_schema_from_file(schema_path)
        self.register_schema(name, schema)

    def unregister_schema(self, name: str) -> None:
        """注销 Schema

        Args:
            name: Schema 名称
        """
        if name in self._schemas:
            del self._schemas[name]
            logger.debug(f"已注销 Schema: {name}")

    def validate(self, config: dict, schema_name: str) -> bool:
        """验证配置

        Args:
            config: 配置字典
            schema_name: Schema 名称

        Returns:
            是否验证通过

        Raises:
            ConfigValidationError: 验证失败
        """
        if schema_name not in self._schemas:
            raise ConfigValidationError(f"Schema 不存在: {schema_name}")

        schema = self._schemas[schema_name]

        try:
            from jsonschema import validate, ValidationError

            validate(instance=config, schema=schema)
            logger.debug(f"配置验证通过: {schema_name}")
            return True

        except ImportError:
            logger.warning("jsonschema 未安装，跳过配置验证")
            return True

        except ValidationError as e:
            errors = self._format_validation_error(e)
            raise ConfigValidationError(f"配置验证失败: {schema_name}", errors=errors)

    def validate_value(self, value: Any, schema_name: str, property_path: str) -> bool:
        """验证单个配置值

        Args:
            value: 配置值
            schema_name: Schema 名称
            property_path: 属性路径（如 "llm.openai.api_key"）

        Returns:
            是否验证通过

        Raises:
            ConfigValidationError: 验证失败
        """
        if schema_name not in self._schemas:
            raise ConfigValidationError(f"Schema 不存在: {schema_name}")

        schema = self._schemas[schema_name]

        # 导航到目标属性的子 Schema
        target_schema = self._navigate_schema(schema, property_path)
        if target_schema is None:
            # 属性不在 Schema 中，跳过验证
            return True

        try:
            from jsonschema import validate, ValidationError

            validate(instance=value, schema=target_schema)
            logger.debug(f"配置值验证通过: {property_path}")
            return True

        except ImportError:
            logger.warning("jsonschema 未安装，跳过配置验证")
            return True

        except ValidationError as e:
            errors = self._format_validation_error(e)
            raise ConfigValidationError(
                f"配置值验证失败: {property_path}", errors=errors
            )

    def _navigate_schema(self, schema: dict, property_path: str) -> Optional[dict]:
        """导航到指定属性的子 Schema

        Args:
            schema: 完整 Schema
            property_path: 属性路径（如 "llm.openai.api_key"）

        Returns:
            子 Schema，如果不存在则返回 None
        """
        parts = property_path.split(".")
        current = schema.get("properties", {})

        for i, part in enumerate(parts[:-1]):
            if part not in current:
                return None
            current = current[part].get("properties", {})

        last_part = parts[-1]
        return current.get(last_part)

    def _format_validation_error(self, error: Any) -> List[str]:
        """格式化验证错误

        Args:
            error: jsonschema ValidationError

        Returns:
            错误信息列表
        """
        errors = [str(error.message)]

        # 添加上下文信息
        if error.path:
            path_str = " -> ".join(str(p) for p in error.path)
            errors.append(f"路径: {path_str}")

        if error.schema_path:
            schema_path_str = " -> ".join(str(p) for p in error.schema_path)
            errors.append(f"Schema 路径: {schema_path_str}")

        return errors

    def get_schema(self, name: str) -> Optional[dict]:
        """获取 Schema

        Args:
            name: Schema 名称

        Returns:
            Schema 字典，如果不存在则返回 None
        """
        return self._schemas.get(name)

    def list_schemas(self) -> List[str]:
        """列出所有已注册的 Schema

        Returns:
            Schema 名称列表
        """
        return list(self._schemas.keys())


# 全局验证器实例
_global_validator: Optional[ConfigValidator] = None


def get_validator() -> ConfigValidator:
    """获取全局配置验证器实例

    Returns:
        配置验证器实例
    """
    global _global_validator
    if _global_validator is None:
        _global_validator = ConfigValidator()
    return _global_validator


__all__ = [
    "ConfigValidationError",
    "ConfigValidator",
    "get_validator",
]
