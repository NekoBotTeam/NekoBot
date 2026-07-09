from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from loguru import logger

from ...app import NekoBotFramework
from ...contracts import RegisteredPlugin
from .config_store import ConfigStore


class PluginManager:
    """插件加载器与视图组装。

    扫描 plugins_dir 下每个含 main.py 的子目录，import_module 后交给
    framework.bind_module 注册到 RuntimeRegistry。视图层信息由 ConfigStore
    的 enabled/config 合并而来。
    """

    def __init__(
        self,
        framework: NekoBotFramework,
        config_store: ConfigStore,
        plugins_dir: Path | None = None,
    ) -> None:
        self.framework = framework
        self.config_store = config_store
        self.plugins_dir = (
            Path(plugins_dir) if plugins_dir is not None else Path("data/plugins")
        )

    def discover(self) -> list[str]:
        if not self.plugins_dir.exists():
            return []
        return sorted(
            p.name
            for p in self.plugins_dir.iterdir()
            if p.is_dir() and not p.name.startswith("_") and (p / "main.py").exists()
        )

    def load_all(self) -> None:
        for name in self.discover():
            self.load_one(name)

    def load_one(self, dir_name: str) -> None:
        module_path = f"data.plugins.{dir_name}.main"
        try:
            module = importlib.import_module(module_path)
        except Exception:
            logger.exception("failed to import plugin module: {}", module_path)
            return
        try:
            self.framework.bind_module(module)
            logger.info("plugin loaded: {}", dir_name)
        except Exception:
            logger.exception("failed to bind plugin: {}", dir_name)

    def list_registered(self) -> list[RegisteredPlugin]:
        return list(self.framework.runtime_registry.plugins.values())

    def get_registered(self, name: str) -> RegisteredPlugin | None:
        return self.framework.runtime_registry.plugins.get(name)

    def to_info(self, rp: RegisteredPlugin) -> dict[str, Any]:
        spec = rp.spec
        meta = spec.metadata or {}
        return {
            "name": spec.name,
            "enabled": self.config_store.is_plugin_enabled(spec.name),
            "version": spec.version,
            "description": spec.description,
            "author": str(meta.get("author", "")),
            "display_name": str(meta.get("display_name", "")),
            "repository": str(meta.get("repository", "")),
            "tags": list(meta.get("tags", [])),
        }

    def config_schema_name(self, name: str) -> str | None:
        rp = self.get_registered(name)
        if rp is None or rp.spec.config_schema is None:
            return None
        return rp.spec.config_schema.name
