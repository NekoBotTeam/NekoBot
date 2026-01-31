"""Gemini Embedding Provider

Google Gemini 提供的嵌入向量服务
"""

from typing import Optional, List
from loguru import logger

from .embedding_base import EmbeddingProvider
from .register import register_embedding_provider
import google.generativeai as genai


@register_embedding_provider(
    provider_type_name="gemini_embedding",
    desc="Google Gemini Embedding Provider (text-embedding-004)",
    default_config_tmpl={
        "type": "gemini_embedding",
        "enable": False,
        "id": "gemini_embedding",
        "model": "text-embedding-004",
        "api_key": "",
    },
    provider_display_name="Google Gemini Embedding",
)
class GeminiEmbeddingProvider(EmbeddingProvider):
    """Gemini Embedding 服务提供商"""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.model = provider_config.get("model", "text-embedding-004")
        self.timeout = provider_config.get("timeout", 60)
        self._dimensions = None

    async def initialize(self) -> None:
        """初始化 Provider"""
        if not self.api_key:
            raise ValueError("Gemini API Key 未配置")

        # 配置 API Key
        genai.configure(api_key=self.api_key)

        # 测试获取维度
        try:
            test_embedding = await self.get_embedding("test")
            self._dimensions = len(test_embedding)
            logger.info(
                f"[Gemini Embedding] Embedding Provider 已初始化，向量维度: {self._dimensions}"
            )
        except Exception as e:
            logger.error(f"[Gemini Embedding] 初始化失败: {e}")
            raise

    async def close(self) -> None:
        """关闭 Provider"""
        logger.info("[Gemini Embedding] Embedding Provider 已关闭")

    async def get_embedding(self, text: str) -> List[float]:
        """获取文本的向量

        Args:
            text: 输入文本

        Returns:
            向量列表
        """
        if not text:
            raise ValueError("文本不能为空")

        try:
            # 获取嵌入模型
            embedding_model = genai.embed_content(
                model=f"models/{self.model}",
                content=text,
            )

            # 解析结果
            embedding = embedding_model["embedding"]

            return list(embedding)

        except Exception as e:
            logger.error(f"[Gemini Embedding] 获取向量失败: {e}")
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

        try:
            # Gemini Embedding API 不支持批量请求，需要逐个请求
            embeddings = []
            for text in texts:
                embedding = await self.get_embedding(text)
                embeddings.append(embedding)

            return embeddings

        except Exception as e:
            logger.error(f"[Gemini Embedding] 批量获取向量失败: {e}")
            raise

    def get_dim(self) -> int:
        """获取向量的维度

        Returns:
            向量维度
        """
        if self._dimensions is None:
            # 根据模型名称返回默认维度
            model_dimensions = {
                "text-embedding-004": 768,
                "text-multilingual-embedding-002": 768,
                "text-embedding-004": 768,
                "text-embedding-001": 768,
            }
            self._dimensions = model_dimensions.get(self.model, 768)
        return self._dimensions

    async def get_models(self) -> list[str]:
        """获取支持的模型列表"""
        return [
            "text-embedding-004",
            "text-multilingual-embedding-002",
            "text-embedding-001",
        ]

    async def test(self) -> None:
        """测试 Provider 是否可用"""
        await self.get_embedding("test")
