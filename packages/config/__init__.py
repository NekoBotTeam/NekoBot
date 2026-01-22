"""NekoBot 配置管理

提供配置变更监听、持久化和配置模型
"""

from .manager import (
    ConfigChangeType,
    ConfigChangeEvent,
    ConfigWatcher,
    ConfigManager,
    get_config_manager,
    config,
)

# 新的配置类（参考 AstrBot）
from .schema import CONFIG_SCHEMA, get_default_config
from .nekobot_config import NekoBotConfig

# 向后兼容函数
_global_config: NekoBotConfig | None = None


def load_config() -> dict:
    """加载配置（向后兼容）

    Returns:
        配置字典
    """
    global _global_config

    if _global_config is None:
        from pathlib import Path

        config_path = Path(__file__).parent.parent.parent / "data" / "config.json"
        _global_config = NekoBotConfig(config_path)

    return dict(_global_config)


__all__ = [
    # 配置管理（向后兼容）
    "ConfigChangeType",
    "ConfigChangeEvent",
    "ConfigWatcher",
    "ConfigManager",
    "get_config_manager",
    "config",
    # 新的配置类
    "CONFIG_SCHEMA",
    "get_default_config",
    "NekoBotConfig",
    # 向后兼容
    "load_config",
]
