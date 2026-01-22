"""核心工具模块"""

from .path_manager import (
    get_nekobot_path,
    get_nekobot_root,
    get_nekobot_data_path,
    get_nekobot_config_path,
    get_nekobot_plugin_path,
    get_nekobot_plugin_data_path,
    get_nekobot_temp_path,
    get_nekobot_knowledge_base_path,
    get_nekobot_backups_path,
    get_nekobot_dist_path,
    get_nekobot_logs_path,
    ensure_directories,
)

__all__ = [
    "get_nekobot_path",
    "get_nekobot_root",
    "get_nekobot_data_path",
    "get_nekobot_config_path",
    "get_nekobot_plugin_path",
    "get_nekobot_plugin_data_path",
    "get_nekobot_temp_path",
    "get_nekobot_knowledge_base_path",
    "get_nekobot_backups_path",
    "get_nekobot_dist_path",
    "get_nekobot_logs_path",
    "ensure_directories",
]
