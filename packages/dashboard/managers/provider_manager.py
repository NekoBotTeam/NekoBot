from __future__ import annotations

from .config_store import ConfigStore, ValueMap


class ProviderManager:
    """LLM 提供商配置的 CRUD（数据落在 data/config.json 的 provider_configs）。"""

    def __init__(self, config_store: ConfigStore) -> None:
        self.config_store = config_store

    def list(self) -> dict[str, ValueMap]:
        return self.config_store.get_provider_configs()

    def get(self, name: str) -> ValueMap | None:
        return self.config_store.get_provider_configs().get(name)

    async def upsert(self, name: str, config: ValueMap) -> None:
        await self.config_store.upsert_provider(name, config)

    async def delete(self, name: str) -> None:
        await self.config_store.delete_provider(name)

    async def set_enabled(self, name: str, enabled: bool) -> None:
        await self.config_store.set_provider_enabled(name, enabled)
