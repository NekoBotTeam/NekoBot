"""统一 Provider 抽象基类

定义所有 Provider 的统一接口和类型枚举，参考 AstrBot 的 Provider 架构
"""

import abc
from enum import Enum
from typing import Optional


class ProviderType(Enum):
    """Provider 类型枚举"""

    CHAT_COMPLETION = "chat_completion"
    TEXT_TO_SPEECH = "text_to_speech"
    SPEECH_TO_TEXT = "speech_to_text"
    EMBEDDING = "embedding"
    RERANK = "rerank"


class AbstractProvider(abc.ABC):
    """所有 Provider 的统一抽象基类

    提供通用的初始化、配置管理和测试接口
    """

    def __init__(self, provider_config: dict, provider_settings: dict):
        """初始化 Provider

        Args:
            provider_config: Provider 配置字典
            provider_settings: Provider 全局设置字典
        """
        super().__init__()
        if not provider_config:
            raise ValueError("provider_config 不能为空")
        if not provider_settings:
            raise ValueError("provider_settings 不能为空")

        self.provider_config = provider_config
        self.provider_settings = provider_settings
        self.model_name = provider_config.get("model", "")

    def set_model(self, model_name: str) -> None:
        """设置当前模型名称

        Args:
            model_name: 模型名称
        """
        if not model_name:
            raise ValueError("模型名称不能为空")
        self.model_name = model_name

    def get_model(self) -> str:
        """获取当前模型名称

        Returns:
            当前模型名称
        """
        return self.model_name

    def get_current_key(self) -> str:
        """获取当前 API Key

        Returns:
            当前使用的 API Key
        """
        keys = self.get_keys()
        if keys and len(keys) > 0:
            return keys[0]
        return ""

    def get_keys(self) -> list[str]:
        """获取所有 API Key

        Returns:
            API Key 列表，如果未配置则返回空列表
        """
        keys = self.provider_config.get("api_key", [""])
        return keys or [""]

    @abc.abstractmethod
    async def get_models(self) -> list[str]:
        """获取支持的模型列表

        Returns:
            模型名称列表
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def test(self):
        """测试 Provider 是否可用

        Raises:
            Exception: 如果 Provider 不可用
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def initialize(self) -> None:
        """初始化 Provider

        在首次使用前调用，用于初始化连接、客户端等资源
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def close(self) -> None:
        """关闭 Provider

        释放资源，如关闭连接、清理缓存等
        """
        raise NotImplementedError

    def get_config(self, key: str, default: any = None) -> any:
        """获取配置项

        Args:
            key: 配置键
            default: 默认值

        Returns:
            配置值
        """
        return self.provider_config.get(key, default)

    def get_setting(self, key: str, default: any = None) -> any:
        """获取全局设置项

        Args:
            key: 设置键
            default: 默认值

        Returns:
            设置值
        """
        return self.provider_settings.get(key, default)
