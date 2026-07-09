from __future__ import annotations

from .config_store import ConfigStore


class PersonaManager:
    """人格（System Prompt）CRUD，落在 data/config.json 的 personas。"""

    def __init__(self, config_store: ConfigStore) -> None:
        self.config_store = config_store

    def list(self) -> dict[str, str]:
        return self.config_store.get_personas()

    def get(self, name: str) -> dict[str, str] | None:
        personas = self.config_store.get_personas()
        if name in personas:
            return {"name": name, "prompt": personas[name]}
        return None

    async def create(self, name: str, prompt: str) -> None:
        personas = self.config_store.get_personas()
        personas[name] = prompt
        await self.config_store.replace_personas(personas)

    async def update(self, name: str, prompt: str) -> None:
        personas = self.config_store.get_personas()
        if name not in personas:
            raise KeyError(name)
        personas[name] = prompt
        await self.config_store.replace_personas(personas)

    async def delete(self, name: str) -> None:
        personas = self.config_store.get_personas()
        personas.pop(name, None)
        await self.config_store.replace_personas(personas)
