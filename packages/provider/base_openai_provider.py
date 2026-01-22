"""OpenAI 兼容提供商基类

为所有 OpenAI 兼容的 LLM 提供商提供基础实现。
"""

from typing import Optional

from loguru import logger

from .base import BaseLLMProvider
from openai import AsyncOpenAI


class BaseOpenAICompatibleProvider(BaseLLMProvider):
    """OpenAI 兼容提供商基类"""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        """初始化提供商

        Args:
            provider_config: 提供商配置字典
            provider_settings: 提供商设置字典
        """
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.base_url = provider_config.get("base_url", self.get_default_base_url())
        self.max_tokens = provider_config.get("max_tokens", 4096)
        self.temperature = provider_config.get("temperature", 0.7)
        self.timeout = provider_config.get("timeout", 120)
        self.custom_headers = provider_config.get("custom_headers", {})
        self._client: Optional[AsyncOpenAI] = None
        self._current_key_index = 0

    def get_default_base_url(self) -> str:
        """获取默认的 API 基础 URL

        子类应重写此方法以提供特定的基础 URL。

        Returns:
            默认的 API 基础 URL
        """
        return ""

    def _get_client(self) -> AsyncOpenAI:
        """获取或创建 OpenAI 客户端

        Returns:
            AsyncOpenAI 客户端实例
        """
        if self._client is None or self._client.is_closed:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                default_headers=self.custom_headers,
                timeout=self.timeout,
            )
        return self._client

    def get_current_key(self) -> str:
        """获取当前 API Key

        Returns:
            当前使用的 API Key
        """
        keys = self.get_keys()
        if keys and self._current_key_index < len(keys):
            return keys[self._current_key_index]
        return ""

    def set_key(self, key: str) -> None:
        """设置 API Key

        Args:
            key: 要设置的 API Key
        """
        self.provider_config["api_key"] = [key]
        self.api_key = key
        self._client = None

    async def initialize(self) -> None:
        """初始化提供商

        Raises:
            ValueError: 如果 API Key 未配置
        """
        if not self.api_key:
            raise ValueError(
                f"{self.provider_config.get('type', 'Provider')} API Key 未配置"
            )

        self._client = self._get_client()
        provider_name = self.provider_config.get("type", "Provider")
        logger.info(f"[{provider_name}] 提供商已初始化")

    async def get_models(self) -> list[str]:
        """获取支持的模型列表

        Returns:
            模型名称列表

        Raises:
            Exception: 获取模型列表失败
        """
        try:
            models_str = []
            models = await self._client.models.list()
            models = sorted(models.data, key=lambda x: x.id)
            for model in models:
                models_str.append(model.id)
            return models_str
        except Exception as e:
            raise Exception(f"获取模型列表失败：{e}")

    async def close(self) -> None:
        """关闭提供商"""
        if self._client and not self._client.is_closed:
            await self._client.close()
            provider_name = self.provider_config.get("type", "Provider")
            logger.info(f"[{provider_name}] 提供商已关闭")

    async def _build_messages(
        self,
        prompt: str | None = None,
        image_urls: list[str] | None = None,
        contexts: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> list[dict]:
        """构建消息列表

        Args:
            prompt: 提示词
            image_urls: 图片 URL 列表
            contexts: 上下文消息列表
            system_prompt: 系统提示词

        Returns:
            构建好的消息列表
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if contexts:
            messages.extend(contexts)

        if prompt:
            user_message = {"role": "user", "content": prompt}
            if image_urls:
                user_message["content"] = [
                    {"type": "text", "text": prompt},
                    *[
                        {"type": "image_url", "image_url": {"url": url}}
                        for url in image_urls
                    ],
                ]
            messages.append(user_message)
        elif image_urls:
            messages.append(
                {"role": "user", "content": [{"type": "text", "text": "[图片]"}]}
            )

        return messages
