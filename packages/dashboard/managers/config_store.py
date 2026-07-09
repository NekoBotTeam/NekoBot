from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from ...bootstrap.config import (
    DEFAULT_CONFIG_PATH,
    BootstrapConfig,
    load_app_config,
)

ValueMap = dict[str, Any]
ScopedValueMap = dict[str, ValueMap]


class ConfigStore:
    """data/config.json 的读写与热重载。

    所有 mutation helper 先改内存中的原始 dict，再调用 save() 原子写回并 reload。
    注意：reload 仅刷新本 Store 与 dashboard 视图；NekoBotFramework 的运行时
    ConfigurationContext 需重启进程才会完全生效（热更新留待后续）。
    """

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH) -> None:
        self.config_path = Path(config_path)
        self._bootstrap: BootstrapConfig = BootstrapConfig()
        self._raw: dict[str, Any] = {}
        self.reload()

    def reload(self) -> BootstrapConfig:
        self._bootstrap = load_app_config(self.config_path)
        if self.config_path.exists():
            text = self.config_path.read_text(encoding="utf-8")
            try:
                loaded = json.loads(text)
                self._raw = loaded if isinstance(loaded, dict) else {}
            except json.JSONDecodeError:
                logger.warning("config.json parse failed, using empty raw")
                self._raw = {}
        else:
            self._raw = {}
        return self._bootstrap

    @property
    def bootstrap(self) -> BootstrapConfig:
        return self._bootstrap

    @property
    def raw(self) -> dict[str, Any]:
        return self._raw

    # ── readers ───────────────────────────────────────────────────────────────
    def get_auth_config(self) -> ValueMap:
        return dict(self._bootstrap.auth_config)

    def get_plugin_configs(self) -> ScopedValueMap:
        return {k: dict(v) for k, v in self._bootstrap.plugin_configs.items()}

    def get_plugin_config(self, name: str) -> ValueMap:
        return dict(self._bootstrap.plugin_configs.get(name, {}))

    def get_plugin_bindings(self) -> ScopedValueMap:
        return {k: dict(v) for k, v in self._bootstrap.plugin_bindings.items()}

    def is_plugin_enabled(self, name: str) -> bool:
        binding = self._bootstrap.plugin_bindings.get(name, {})
        return bool(binding.get("enabled", True))

    def get_provider_configs(self) -> ScopedValueMap:
        return {k: dict(v) for k, v in self._bootstrap.provider_configs.items()}

    def get_platforms(self) -> list[ValueMap]:
        return [dict(p) for p in self._bootstrap.platforms]

    # ── writers (async, atomic) ───────────────────────────────────────────────
    async def _write_back(self) -> None:
        tmp = self.config_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.config_path)
        self.reload()
        logger.info("config.json persisted and reloaded")

    async def set_plugin_enabled(self, name: str, enabled: bool) -> None:
        bindings = self._raw.setdefault("plugin_bindings", {})
        binding = bindings.setdefault(name, {})
        binding["enabled"] = enabled
        await self._write_back()

    async def set_plugin_config(self, name: str, config: ValueMap) -> None:
        self._raw.setdefault("plugin_configs", {})[name] = dict(config)
        await self._write_back()

    async def upsert_provider(self, name: str, config: ValueMap) -> None:
        self._raw.setdefault("provider_configs", {})[name] = dict(config)
        await self._write_back()

    async def delete_provider(self, name: str) -> None:
        self._raw.get("provider_configs", {}).pop(name, None)
        await self._write_back()

    async def set_provider_enabled(self, name: str, enabled: bool) -> None:
        cfg = self._raw.setdefault("provider_configs", {}).setdefault(name, {})
        cfg["enabled"] = enabled
        await self._write_back()

    async def upsert_platform(self, instance_uuid: str, config: ValueMap) -> None:
        platforms = self._raw.setdefault("platforms", [])
        for p in platforms:
            if p.get("instance_uuid") == instance_uuid:
                p.update(config)
                break
        else:
            platforms.append(config)
        await self._write_back()

    async def delete_platform(self, instance_uuid: str) -> None:
        platforms = self._raw.get("platforms", [])
        self._raw["platforms"] = [
            p for p in platforms if p.get("instance_uuid") != instance_uuid
        ]
        await self._write_back()

    async def set_platform_enabled(self, instance_uuid: str, enabled: bool) -> None:
        for p in self._raw.setdefault("platforms", []):
            if p.get("instance_uuid") == instance_uuid:
                p["enabled"] = enabled
                break
        await self._write_back()

    async def replace_personas(self, personas: ValueMap) -> None:
        self._raw["personas"] = dict(personas)
        await self._write_back()

    def get_personas(self) -> ValueMap:
        raw = self._raw.get("personas")
        if isinstance(raw, dict):
            return {str(k): v for k, v in raw.items() if isinstance(v, str)}
        return {}
