"""NekoBot 配置类

参考 AstrBot 的 AstrBotConfig 实现，继承 dict 支持点号访问
"""

import json
import copy
import secrets
from pathlib import Path
from typing import Any
from loguru import logger
from .schema import CONFIG_SCHEMA, get_default_config


class NekoBotConfig(dict):
    """NekoBot 配置类（继承 dict）"""

    def __init__(self, config_path: Path, schema: dict = None):
        super().__init__()
        self.config_path = config_path
        self.schema = schema or CONFIG_SCHEMA
        self.reload_lock = None

        # 初始化配置
        self._initialize_config()

    def _initialize_config(self):
        """初始化配置（加载或创建）"""
        if self.config_path.exists():
            self.load()
            self._check_config_integrity()
        else:
            # 创建默认配置
            default = get_default_config()

            # 自动生成 JWT secret_key
            default["jwt"]["secret_key"] = secrets.token_urlsafe(32)

            self.update(default)
            self.save()
            logger.info(f"已创建配置文件: {self.config_path}")
            logger.info("已自动生成 JWT secret_key")

    def load(self) -> None:
        """从文件加载配置"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.clear()
                self.update(data)
                logger.debug(f"已加载配置: {self.config_path}")
        except json.JSONDecodeError as e:
            logger.error(f"配置文件格式错误: {e}")
            raise
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            raise

    def save(self) -> None:
        """保存配置到文件"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(dict(self), f, indent=2, ensure_ascii=False)
            logger.debug(f"已保存配置: {self.config_path}")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            raise

    def _check_config_integrity(self, refer_conf: dict = None, path: str = "") -> None:
        """检查配置完整性（参考 AstrBot）

        1. 插入缺失的配置项
        2. 移除多余的配置项（可选）
        3. 同步配置顺序
        4. 自动保存变更
        """
        refer_conf = refer_conf or get_default_config()
        has_changes = False

        # 检查缺失项
        for key, value in refer_conf.items():
            if key not in self:
                self[key] = copy.deepcopy(value)
                logger.debug(f"插入缺失配置: {path}{key}")
                has_changes = True
            elif isinstance(value, dict):
                current = self.get(key)
                if isinstance(current, dict):
                    # 递归检查嵌套对象
                    for sub_key, sub_value in value.items():
                        if sub_key not in current:
                            current[sub_key] = copy.deepcopy(sub_value)
                            logger.debug(f"插入缺失配置: {path}{key}.{sub_key}")
                            has_changes = True

        # 同步顺序（按 refer_conf 顺序）
        ordered_config = {}
        for key in refer_conf.keys():
            if key in self:
                ordered_config[key] = self[key]

        # 添加不在 refer_conf 中的配置（向后兼容）
        for key in self.keys():
            if key not in ordered_config:
                ordered_config[key] = self[key]

        self.clear()
        self.update(ordered_config)

        # 自动保存
        if has_changes:
            self.save()
            logger.info("配置完整性检查完成，已自动修复")

    def __getattr__(self, key: str) -> Any:
        """支持点号访问"""
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{key}'")

    def __setattr__(self, key: str, value: Any) -> None:
        """支持点号赋值"""
        if key in ("config_path", "schema", "reload_lock"):
            super().__setattr__(key, value)
        else:
            self[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """获取嵌套配置值（支持点号路径）"""
        if "." not in key:
            return super().get(key, default)

        # 支持 "server.host" 格式
        parts = key.split(".")
        current = self
        for part in parts[:-1]:
            current = current.get(part, {})
            if not isinstance(current, dict):
                return default
        return current.get(parts[-1], default)

    def set(self, key: str, value: Any) -> None:
        """设置嵌套配置值（支持点号路径）"""
        if "." not in key:
            self[key] = value
            return

        parts = key.split(".")
        current = self
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
