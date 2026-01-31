"""Cohere Rerank Provider

Cohere 提供的文档重排序服务
"""

from typing import Optional, List
from loguru import logger

from .rerank_base import RerankProvider, RerankResult
from .register import register_rerank_provider
from .abstract_provider import AbstractProvider
import cohere


@register_rerank_provider(
    provider_type_name="cohere_rerank",
    desc="Cohere Rerank Provider (rerank-v3.5, rerank-multilingual-v3.0)",
    default_config_tmpl={
        "type": "cohere_rerank",
        "enable": False,
        "id": "cohere_rerank",
        "model": "rerank-v3.5",
        "api_key": "",
        "top_n": None,
    },
    provider_display_name="Cohere Rerank",
)
class CohereRerankProvider(RerankProvider):
    """Cohere Rerank 服务提供商"""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.model = provider_config.get("model", "rerank-v3.5")
        self.default_top_n = provider_config.get("top_n")
        self.timeout = provider_config.get("timeout", 60)
        self._client: Optional[cohere.AsyncClient] = None

    def _get_client(self) -> cohere.AsyncClient:
        """获取或创建 Cohere 客户端"""
        if self._client is None:
            self._client = cohere.AsyncClient(
                api_key=self.api_key,
                timeout=self.timeout,
            )
        return self._client

    async def initialize(self) -> None:
        """初始化 Provider"""
        if not self.api_key:
            raise ValueError("Cohere API Key 未配置")

        self._client = self._get_client()
        logger.info("[Cohere Rerank] Rerank Provider 已初始化")

    async def close(self) -> None:
        """关闭 Provider"""
        self._client = None
        logger.info("[Cohere Rerank] Rerank Provider 已关闭")

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
    ) -> List[RerankResult]:
        """获取查询和文档的重排序分数

        Args:
            query: 查询文本
            documents: 文档列表
            top_n: 返回前 N 个结果，None 表示返回全部

        Returns:
            重排序结果列表
        """
        if not query:
            raise ValueError("查询文本不能为空")

        if not documents:
            return []

        # 使用默认值如果未提供
        top_n = top_n or self.default_top_n

        client = self._get_client()

        try:
            response = await client.rerank(
                model=self.model,
                query=query,
                documents=documents,
                top_n=top_n or len(documents),
            )

            # 解析结果
            results = []
            for result in response.results:
                results.append(
                    RerankResult(
                        index=result.index,
                        score=result.relevance_score,
                        document=documents[result.index],
                    )
                )

            logger.info(f"[Cohere Rerank] 重排序成功，返回 {len(results)} 个结果")
            return results

        except Exception as e:
            logger.error(f"[Cohere Rerank] 重排序失败: {e}")
            raise

    async def get_models(self) -> list[str]:
        """获取支持的模型列表"""
        return [
            "rerank-v3.5",
            "rerank-english-v3.0",
            "rerank-multilingual-v3.0",
        ]

    async def test(self) -> None:
        """测试 Provider 是否可用"""
        result = await self.rerank(
            query="Apple",
            documents=["apple", "banana"],
        )
        if not result:
            raise Exception("Rerank provider test failed, no results returned")
