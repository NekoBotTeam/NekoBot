"""NekoBot 统一路径管理模块

参考 AstrBot 的 astrbot_path.py 实现，提供统一的路径管理功能

项目路径：固定为源码所在路径
根目录路径：默认为当前工作目录，可通过环境变量 NEKOBOT_ROOT 指定
数据目录路径：固定为根目录下的 data 目录
配置文件路径：固定为数据目录下的 config 目录
插件目录路径：固定为数据目录下的 plugins 目录
插件数据目录路径：固定为数据目录下的 plugin_data 目录
临时文件目录路径：固定为数据目录下的 temp 目录
"""

import os


def get_nekobot_path() -> str:
    """获取 NekoBot 项目路径"""
    return os.path.realpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../"),
    )


def get_nekobot_root() -> str:
    """获取 NekoBot 根目录路径"""
    if path := os.environ.get("NEKOBOT_ROOT"):
        return os.path.realpath(path)
    return os.path.realpath(os.getcwd())


def get_nekobot_data_path() -> str:
    """获取 NekoBot 数据目录路径"""
    return os.path.realpath(os.path.join(get_nekobot_root(), "data"))


def get_nekobot_config_path() -> str:
    """获取 NekoBot 配置文件路径"""
    return os.path.realpath(os.path.join(get_nekobot_data_path(), "config"))


def get_nekobot_plugin_path() -> str:
    """获取 NekoBot 插件目录路径"""
    return os.path.realpath(os.path.join(get_nekobot_data_path(), "plugins"))


def get_nekobot_plugin_data_path() -> str:
    """获取 NekoBot 插件数据目录路径"""
    return os.path.realpath(os.path.join(get_nekobot_data_path(), "plugin_data"))


def get_nekobot_temp_path() -> str:
    """获取 NekoBot 临时文件目录路径"""
    return os.path.realpath(os.path.join(get_nekobot_data_path(), "temp"))


def get_nekobot_knowledge_base_path() -> str:
    """获取 NekoBot 知识库根目录路径"""
    return os.path.realpath(os.path.join(get_nekobot_data_path(), "knowledge_base"))


def get_nekobot_backups_path() -> str:
    """获取 NekoBot 备份目录路径"""
    return os.path.realpath(os.path.join(get_nekobot_data_path(), "backups"))


def get_nekobot_dist_path() -> str:
    """获取 NekoBot WebUI 静态文件目录路径"""
    return os.path.realpath(os.path.join(get_nekobot_data_path(), "dist"))


def get_nekobot_logs_path() -> str:
    """获取 NekoBot 日志目录路径"""
    return os.path.realpath(os.path.join(get_nekobot_data_path(), "logs"))


def ensure_directories() -> None:
    """确保所有必要的目录存在"""
    directories = [
        get_nekobot_data_path(),
        get_nekobot_config_path(),
        get_nekobot_plugin_path(),
        get_nekobot_plugin_data_path(),
        get_nekobot_temp_path(),
        get_nekobot_knowledge_base_path(),
        get_nekobot_backups_path(),
        get_nekobot_logs_path(),
    ]

    for directory in directories:
        os.makedirs(directory, exist_ok=True)


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
