"""LLM Provider 基类

提供 LLM 服务提供商的抽象接口
"""

import abc
import asyncio
from typing import Any, AsyncGenerator

from .register import LLMProviderMetaData, llm_provider_cls_map
from .entities import LLMResponse


class BaseLLMProvider(abc.ABC):
    """LLM 服务提供商基类"""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        """初始化 LLM 提供商

        Args:
            provider_config: 提供商配置字典
            provider_settings: 提供商设置字典

        Raises:
            ValueError: 如果 provider_config 无效
        """
        super().__init__()
        if not provider_config:
            raise ValueError("provider_config 不能为空")
        if not provider_settings:
            raise ValueError("provider_settings 不能为空")

        self.provider_config = provider_config
        self.provider_settings = provider_settings
        self.model_name = provider_config.get("model", "")
        self._meta_cache: LLMProviderMetaData | None = None

    def set_model(self, model_name: str) -> None:
        """设置当前模型名称

        Args:
            model_name: 模型名称
        """
        if not model_name:
            raise ValueError("模型名称不能为空")
        self.model_name = model_name
        # 清除元数据缓存，因为模型已更改
        self._meta_cache = None

    def get_model(self) -> str:
        """获取当前模型名称

        Returns:
            当前模型名称
        """
        return self.model_name

    def meta(self) -> LLMProviderMetaData:
        """获取服务提供商元数据

        Returns:
            LLMProviderMetaData 对象

        Raises:
            ValueError: 如果服务提供商类型未注册
        """
        if self._meta_cache is not None:
            return self._meta_cache

        provider_type_name = self.provider_config.get("type", "unknown")
        meta_data = llm_provider_cls_map.get(provider_type_name)
        if not meta_data:
            raise ValueError(f"Provider type {provider_type_name} not registered")

        self._meta_cache = LLMProviderMetaData(
            id=self.provider_config.get("id", "default"),
            model=self.get_model(),
            type=provider_type_name,
            desc=meta_data.desc,
            provider_type=meta_data.provider_type,
            cls_type=type(self),
            default_config_tmpl=meta_data.default_config_tmpl,
            provider_display_name=meta_data.provider_display_name,
        )
        return self._meta_cache

    @abc.abstractmethod
    def get_current_key(self) -> str:
        """获取当前 API Key

        Returns:
            当前使用的 API Key
        """
        raise NotImplementedError

    def get_keys(self) -> list[str]:
        """获取所有 API Key

        Returns:
            API Key 列表，如果未配置则返回空列表
        """
        keys = self.provider_config.get("api_key", [""])
        if isinstance(keys, str):
            keys = [keys]
        return keys or [""]

    @abc.abstractmethod
    def set_key(self, key: str) -> None:
        """设置 API Key

        Args:
            key: 要设置的 API Key
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def get_models(self) -> list[str]:
        """获取支持的模型列表

        Returns:
            模型名称列表
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def text_chat(
        self,
        prompt: str | None = None,
        session_id: str | None = None,
        image_urls: list[str] | None = None,
        contexts: list[dict] | None = None,
        system_prompt: str | None = None,
        model: str | None = None,
        func_tool: Any = None,
        tool_calls_result: Any = None,
        extra_user_content_parts: Any = None,
        **kwargs,
    ) -> LLMResponse:
        """获取 LLM 的文本对话结果

        Args:
            prompt: 提示词
            session_id: 会话 ID（已废弃，保留兼容性）
            image_urls: 图片 URL 列表
            contexts: 上下文消息列表
            system_prompt: 系统提示词
            model: 模型名称，如果为 None 则使用默认模型
            func_tool: 工具集
            tool_calls_result: 工具调用结果
            extra_user_content_parts: 额外的用户内容部分
            **kwargs: 其他参数

        Returns:
            LLMResponse 对象
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def text_chat_stream(
        self,
        prompt: str | None = None,
        session_id: str | None = None,
        image_urls: list[str] | None = None,
        contexts: list[dict] | None = None,
        system_prompt: str | None = None,
        model: str | None = None,
        func_tool: Any = None,
        tool_calls_result: Any = None,
        extra_user_content_parts: Any = None,
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        """流式获取 LLM 的文本对话结果

        Args:
            prompt: 提示词
            session_id: 会话 ID（已废弃，保留兼容性）
            image_urls: 图片 URL 列表
            contexts: 上下文消息列表
            system_prompt: 系统提示词
            model: 模型名称，如果为 None 则使用默认模型
            func_tool: 工具集
            tool_calls_result: 工具调用结果
            extra_user_content_parts: 额外的用户内容部分
            **kwargs: 其他参数

        Yields:
            LLMResponse 对象
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def initialize(self) -> None:
        """初始化提供商

        子类应在此方法中执行初始化操作，如建立连接、验证配置等。

        Raises:
            Exception: 如果初始化失败
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def close(self) -> None:
        """关闭提供商，释放资源

        子类应在此方法中执行清理操作，如关闭连接、释放资源等。
        """
        raise NotImplementedError

    async def test(self, timeout: float = 45.0, test_prompt: str | None = None) -> None:
        """测试服务提供商是否可用

        Args:
            timeout: 超时时间（秒）
            test_prompt: 测试提示词，如果为 None 则使用默认提示词

        Raises:
            Exception: 如果服务提供商不可用或超时
        """
        if test_prompt is None:
            test_prompt = "REPLY `PONG` ONLY"

        try:
            await asyncio.wait_for(
                self.text_chat(prompt=test_prompt),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise Exception(f"服务提供商测试超时（{timeout}秒）")
        except Exception as e:
            raise Exception(f"服务提供商测试失败: {e}")
