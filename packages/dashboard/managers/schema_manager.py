from __future__ import annotations

from typing import Any

from ...app import NekoBotFramework
from ...schema.fields import (
    BooleanField,
    Field,
    IntegerField,
    ListField,
    ObjectSchema,
    StringField,
)
from .plugin_manager import PluginManager

_PASSWORD_HINTS = ("key", "secret", "token", "password")


def _field_to_meta(name: str, field: Field) -> dict[str, Any]:
    ftype = "string"
    if isinstance(field, IntegerField):
        ftype = "int"
    elif isinstance(field, BooleanField):
        ftype = "bool"
    elif isinstance(field, ListField):
        ftype = "list"
    elif isinstance(field, StringField) and any(
        hint in name.lower() for hint in _PASSWORD_HINTS
    ):
        ftype = "password"

    meta: dict[str, Any] = {
        "type": ftype,
        "label": name,
        "required": field.required,
    }
    if field.description:
        meta["hint"] = field.description
    if field.default is not None:
        meta["default"] = field.default
    if field.choices:
        meta["options"] = [str(choice) for choice in field.choices]
    if isinstance(field, IntegerField):
        if field.minimum is not None:
            meta["min"] = field.minimum
        if field.maximum is not None:
            meta["max"] = field.maximum
    return meta


def _object_to_config_schema(schema: ObjectSchema) -> dict[str, Any]:
    return {
        "fields": {key: _field_to_meta(key, val) for key, val in schema.fields.items()}
    }


class SchemaManager:
    """把 NekoBot 的 ObjectSchema 转成前端 ConfigSchema。"""

    PROVIDER_PREFIX = "provider."

    def __init__(
        self, framework: NekoBotFramework, plugin_manager: PluginManager
    ) -> None:
        self.framework = framework
        self.plugin_manager = plugin_manager

    def provider_schemas(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for full_name in self.framework.schema_registry.list():
            if not full_name.startswith(self.PROVIDER_PREFIX):
                continue
            provider_type = full_name[len(self.PROVIDER_PREFIX) :]
            try:
                obj = self.framework.schema_registry.get(full_name)
            except KeyError:
                continue
            result[provider_type] = _object_to_config_schema(obj)
        return result

    def plugin_schema(self, name: str) -> dict[str, Any]:
        schema_name = self.plugin_manager.config_schema_name(name)
        if not schema_name:
            return {"fields": {}}
        try:
            obj = self.framework.schema_registry.get(schema_name)
        except KeyError:
            return {"fields": {}}
        return _object_to_config_schema(obj)
