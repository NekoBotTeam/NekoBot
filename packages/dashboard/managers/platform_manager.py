from __future__ import annotations

from .config_store import ConfigStore, ValueMap


class PlatformManager:
    """平台实例配置 CRUD（数据落在 data/config.json 的 platforms）。"""

    def __init__(self, config_store: ConfigStore) -> None:
        self.config_store = config_store

    def list(self) -> list[ValueMap]:
        return self.config_store.get_platforms()

    async def upsert(self, instance_uuid: str, config: ValueMap) -> None:
        await self.config_store.upsert_platform(instance_uuid, config)

    async def delete(self, instance_uuid: str) -> None:
        await self.config_store.delete_platform(instance_uuid)

    async def set_enabled(self, instance_uuid: str, enabled: bool) -> None:
        await self.config_store.set_platform_enabled(instance_uuid, enabled)
