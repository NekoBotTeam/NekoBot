"""OpenAI Embedding Provider

支持 OpenAI 的 Embedding API，生成文本的嵌入向量
"""

from typing import Optional, List
from loguru import logger

from .embedding_base import EmbeddingProvider
from .register import register_embedding_provider
from openai import AsyncOpenAI


@register_embedding_provider(
    provider_type_name="openai_embedding",
    desc="OpenAI Embedding Provider (text-embedding-3-small, text-embedding-3-large)",
    default_config_tmpl={
        "type": "openai_embedding",
        "enable": False,
        "id": "openai_embedding",
        "model": "text-embedding-3-small",
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
    },
    provider_display_name="OpenAI Embedding",
)
class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI Embedding 服务提供商"""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.base_url = provider_config.get("base_url", "https://api.openai.com/v1")
        self.model = provider_config.get("model", "text-embedding-3-small")
        self.timeout = provider_config.get("timeout", 60)
        self._client: Optional[AsyncOpenAI] = None
        self._dimensions = None

    def _get_client(self) -> AsyncOpenAI:
        """获取或创建 OpenAI 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def initialize(self) -> None:
        """初始化 Provider"""
        if not self.api_key:
            raise ValueError("OpenAI API Key 未配置")

        self._client = self._get_client()

        # 测试获取维度
        try:
            test_embedding = await self.get_embedding("test")
            self._dimensions = len(test_embedding)
            logger.info(
                f"[OpenAI Embedding] Embedding Provider 已初始化，向量维度: {self._dimensions}"
            )
        except Exception as e:
            logger.error(f"[OpenAI Embedding] 初始化失败: {e}")
            raise

    async def close(self) -> None:
        """关闭 Provider"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.info("[OpenAI Embedding] Embedding Provider 已关闭")

    async def get_embedding(self, text: str) -> List[float]:
        """获取文本的向量

        Args:
            text: 输入文本

        Returns:
            向量列表
        """
        if not text:
            raise ValueError("文本不能为空")

        client = self._get_client()

        try:
            response = await client.embeddings.create(
                model=self.model,
                input=text,
            )

            embedding = response.data[0].embedding
            return embedding

        except Exception as e:
            logger.error(f"[OpenAI Embedding] 获取向量失败: {e}")
            raise

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """批量获取文本的向量

        Args:
            texts: 输入文本列表

        Returns:
            向量列表
        """
        if not texts:
            return []

        client = self._get_client()

        try:
            response = await client.embeddings.create(
                model=self.model,
                input=texts,
            )

            embeddings = [item.embedding for item in response.data]
            return embeddings

        except Exception as e:
            logger.error(f"[OpenAI Embedding] 批量获取向量失败: {e}")
            raise

    def get_dim(self) -> int:
        """获取向量的维度

        Returns:
            向量维度
        """
        if self._dimensions is None:
            # 根据模型名称返回默认维度
            model_dimensions = {
                "text-embedding-3-small": 1536,
                "text-embedding-3-large": 3072,
                "text-embedding-ada-002": 1536,
            }
            self._dimensions = model_dimensions.get(self.model, 1536)
        return self._dimensions

    async def get_models(self) -> list[str]:
        """获取支持的模型列表"""
        return [
            "text-embedding-3-small",
            "text-embedding-3-large",
            "text-embedding-ada-002",
        ]

    async def test(self) -> None:
        """测试 Provider 是否可用"""
        await self.get_embedding("test")
