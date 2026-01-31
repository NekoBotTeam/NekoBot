"""统一的 Provider 管理器

管理所有类型的 Provider（LLM、TTS、STT、Embedding、Rerank），提供统一的接口和生命周期管理
"""

import asyncio
from typing import Optional, Dict, Any, Type
from loguru import logger

from .base import BaseLLMProvider
from .tts_base import TTSProvider
from .stt_base import STTProvider
from .embedding_base import EmbeddingProvider
from .rerank_base import RerankProvider, RerankResult
from .register import ProviderType, ProviderMetaData, get_provider_metadata
from .abstract_provider import AbstractProvider


class ProviderManager:
    """统一的 Provider 管理器

    负责加载、初始化、管理和关闭所有类型的 Provider
    """

    def __init__(self, config_manager, database_manager):
        """初始化 ProviderManager

        Args:
            config_manager: 配置管理器
            database_manager: 数据库管理器
        """
        self.config_manager = config_manager
        self.db_manager = database_manager
        self.reload_lock = asyncio.Lock()

        # 各类型 Provider 实例
        self.llm_providers: list[BaseLLMProvider] = []
        self.tts_providers: list[TTSProvider] = []
        self.stt_providers: list[STTProvider] = []
        self.embedding_providers: list[EmbeddingProvider] = []
        self.rerank_providers: list[RerankProvider] = []

        # Provider 实例映射
        self.inst_map: Dict[str, AbstractProvider] = {}

        # 当前使用的 Provider（从配置读取）
        self.curr_llm_provider_id: Optional[str] = None
        self.curr_tts_provider_id: Optional[str] = None
        self.curr_stt_provider_id: Optional[str] = None
        self.curr_embedding_provider_id: Optional[str] = None
        self.curr_rerank_provider_id: Optional[str] = None

    async def initialize(self) -> None:
        """初始化所有 Provider"""
        logger.info("开始初始化 ProviderManager...")

        # 加载配置
        config = self.config_manager.get_config()
        providers_config = config.get("providers", {})

        # 加载各类 Provider
        await self._load_llm_providers(providers_config.get("llm", {}))
        await self._load_tts_providers(providers_config.get("tts", {}))
        await self._load_stt_providers(providers_config.get("stt", {}))
        await self._load_embedding_providers(providers_config.get("embedding", {}))
        await self._load_rerank_providers(providers_config.get("rerank", {}))

        # 设置默认 Provider
        self.curr_llm_provider_id = providers_config.get("default_llm")
        self.curr_tts_provider_id = providers_config.get("default_tts")
        self.curr_stt_provider_id = providers_config.get("default_stt")
        self.curr_embedding_provider_id = providers_config.get("default_embedding")
        self.curr_rerank_provider_id = providers_config.get("default_rerank")

        logger.info("ProviderManager 初始化完成")

    async def _load_llm_providers(self, llm_configs: Dict[str, Any]) -> None:
        """加载 LLM Provider

        Args:
            llm_configs: LLM Provider 配置字典
        """
        logger.info("开始加载 LLM Provider...")

        for provider_id, provider_config in llm_configs.items():
            if not provider_config.get("enabled", False):
                continue

            try:
                await self._load_provider(
                    provider_type=provider_config.get("type"),
                    provider_id=provider_id,
                    provider_config=provider_config,
                    provider_class=BaseLLMProvider,
                    target_list=self.llm_providers,
                )
            except Exception as e:
                logger.error(f"加载 LLM Provider {provider_id} 失败: {e}")

        logger.info(f"LLM Provider 加载完成，共 {len(self.llm_providers)} 个")

    async def _load_tts_providers(self, tts_configs: Dict[str, Any]) -> None:
        """加载 TTS Provider

        Args:
            tts_configs: TTS Provider 配置字典
        """
        logger.info("开始加载 TTS Provider...")

        for provider_id, provider_config in tts_configs.items():
            if not provider_config.get("enabled", False):
                continue

            try:
                await self._load_provider(
                    provider_type=provider_config.get("type"),
                    provider_id=provider_id,
                    provider_config=provider_config,
                    provider_class=TTSProvider,
                    target_list=self.tts_providers,
                )
            except Exception as e:
                logger.error(f"加载 TTS Provider {provider_id} 失败: {e}")

        logger.info(f"TTS Provider 加载完成，共 {len(self.tts_providers)} 个")

    async def _load_stt_providers(self, stt_configs: Dict[str, Any]) -> None:
        """加载 STT Provider

        Args:
            stt_configs: STT Provider 配置字典
        """
        logger.info("开始加载 STT Provider...")

        for provider_id, provider_config in stt_configs.items():
            if not provider_config.get("enabled", False):
                continue

            try:
                await self._load_provider(
                    provider_type=provider_config.get("type"),
                    provider_id=provider_id,
                    provider_config=provider_config,
                    provider_class=STTProvider,
                    target_list=self.stt_providers,
                )
            except Exception as e:
                logger.error(f"加载 STT Provider {provider_id} 失败: {e}")

        logger.info(f"STT Provider 加载完成，共 {len(self.stt_providers)} 个")

    async def _load_embedding_providers(
        self, embedding_configs: Dict[str, Any]
    ) -> None:
        """加载 Embedding Provider

        Args:
            embedding_configs: Embedding Provider 配置字典
        """
        logger.info("开始加载 Embedding Provider...")

        for provider_id, provider_config in embedding_configs.items():
            if not provider_config.get("enabled", False):
                continue

            try:
                await self._load_provider(
                    provider_type=provider_config.get("type"),
                    provider_id=provider_id,
                    provider_config=provider_config,
                    provider_class=EmbeddingProvider,
                    target_list=self.embedding_providers,
                )
            except Exception as e:
                logger.error(f"加载 Embedding Provider {provider_id} 失败: {e}")

        logger.info(
            f"Embedding Provider 加载完成，共 {len(self.embedding_providers)} 个"
        )

    async def _load_rerank_providers(self, rerank_configs: Dict[str, Any]) -> None:
        """加载 Rerank Provider

        Args:
            rerank_configs: Rerank Provider 配置字典
        """
        logger.info("开始加载 Rerank Provider...")

        for provider_id, provider_config in rerank_configs.items():
            if not provider_config.get("enabled", False):
                continue

            try:
                await self._load_provider(
                    provider_type=provider_config.get("type"),
                    provider_id=provider_id,
                    provider_config=provider_config,
                    provider_class=RerankProvider,
                    target_list=self.rerank_providers,
                )
            except Exception as e:
                logger.error(f"加载 Rerank Provider {provider_id} 失败: {e}")

        logger.info(f"Rerank Provider 加载完成，共 {len(self.rerank_providers)} 个")

    async def _load_provider(
        self,
        provider_type: str,
        provider_id: str,
        provider_config: Dict[str, Any],
        provider_class: Type,
        target_list: list,
    ) -> None:
        """加载单个 Provider

        Args:
            provider_type: Provider 类型
            provider_id: Provider ID
            provider_config: Provider 配置
            provider_class: Provider 类（基类）
            target_list: 目标列表
        """
        # 获取 Provider 元数据
        metadata = get_provider_metadata(provider_type)
        if not metadata:
            raise ValueError(f"Provider 类型 {provider_type} 未注册")

        # 获取 Provider 类
        provider_cls = metadata.cls_type
        provider_settings = {}

        # 创建 Provider 实例
        provider_inst = provider_cls(provider_config, provider_settings)
        await provider_inst.initialize()

        # 添加到列表和映射表
        target_list.append(provider_inst)
        self.inst_map[provider_id] = provider_inst

        logger.info(f"成功加载 Provider: {provider_id} ({provider_type})")

    def get_using_provider(
        self, provider_type: ProviderType
    ) -> Optional[AbstractProvider]:
        """获取当前使用的 Provider

        Args:
            provider_type: Provider 类型

        Returns:
            Provider 实例，如果未配置则返回 None
        """
        provider_id_map = {
            ProviderType.CHAT_COMPLETION: self.curr_llm_provider_id,
            ProviderType.TEXT_TO_SPEECH: self.curr_tts_provider_id,
            ProviderType.SPEECH_TO_TEXT: self.curr_stt_provider_id,
            ProviderType.EMBEDDING: self.curr_embedding_provider_id,
            ProviderType.RERANK: self.curr_rerank_provider_id,
        }

        provider_id = provider_id_map.get(provider_type)
        if not provider_id:
            return None

        return self.inst_map.get(provider_id)

    async def text_to_speech(self, text: str) -> str:
        """文本转语音

        Args:
            text: 要转换的文本

        Returns:
            音频文件路径

        Raises:
            ValueError: 如果 TTS Provider 未配置
        """
        provider = self.get_using_provider(ProviderType.TEXT_TO_SPEECH)
        if not provider or not isinstance(provider, TTSProvider):
            raise ValueError("TTS Provider 未配置或类型错误")

        return await provider.get_audio(text)

    async def speech_to_text(self, audio_url: str) -> str:
        """语音转文本

        Args:
            audio_url: 音频文件路径或 URL

        Returns:
            识别出的文本

        Raises:
            ValueError: 如果 STT Provider 未配置
        """
        provider = self.get_using_provider(ProviderType.SPEECH_TO_TEXT)
        if not provider or not isinstance(provider, STTProvider):
            raise ValueError("STT Provider 未配置或类型错误")

        return await provider.get_text(audio_url)

    async def get_embedding(self, text: str) -> list[float]:
        """获取嵌入向量

        Args:
            text: 输入文本

        Returns:
            向量列表

        Raises:
            ValueError: 如果 Embedding Provider 未配置
        """
        provider = self.get_using_provider(ProviderType.EMBEDDING)
        if not provider or not isinstance(provider, EmbeddingProvider):
            raise ValueError("Embedding Provider 未配置或类型错误")

        return await provider.get_embedding(text)

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """批量获取嵌入向量

        Args:
            texts: 输入文本列表

        Returns:
            向量列表

        Raises:
            ValueError: 如果 Embedding Provider 未配置
        """
        provider = self.get_using_provider(ProviderType.EMBEDDING)
        if not provider or not isinstance(provider, EmbeddingProvider):
            raise ValueError("Embedding Provider 未配置或类型错误")

        return await provider.get_embeddings(texts)

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: Optional[int] = None,
    ) -> list[RerankResult]:
        """重排序

        Args:
            query: 查询文本
            documents: 文档列表
            top_n: 返回前 N 个结果，None 表示返回全部

        Returns:
            重排序结果列表

        Raises:
            ValueError: 如果 Rerank Provider 未配置
        """
        provider = self.get_using_provider(ProviderType.RERANK)
        if not provider or not isinstance(provider, RerankProvider):
            raise ValueError("Rerank Provider 未配置或类型错误")

        return await provider.rerank(query, documents, top_n)

    async def close_all(self) -> None:
        """关闭所有 Provider"""
        logger.info("开始关闭所有 Provider...")

        # 关闭所有 Provider
        for provider in self.inst_map.values():
            try:
                await provider.close()
            except Exception as e:
                logger.error(f"关闭 Provider 失败: {e}")

        # 清空列表
        self.llm_providers.clear()
        self.tts_providers.clear()
        self.stt_providers.clear()
        self.embedding_providers.clear()
        self.rerank_providers.clear()
        self.inst_map.clear()

        logger.info("所有 Provider 已关闭")

    def get_all_providers(self) -> Dict[str, Dict[str, Any]]:
        """获取所有 Provider 信息

        Returns:
            包含所有 Provider 信息的字典
        """
        return {
            "llm": {"count": len(self.llm_providers), "providers": self.llm_providers},
            "tts": {"count": len(self.tts_providers), "providers": self.tts_providers},
            "stt": {"count": len(self.stt_providers), "providers": self.stt_providers},
            "embedding": {
                "count": len(self.embedding_providers),
                "providers": self.embedding_providers,
            },
            "rerank": {
                "count": len(self.rerank_providers),
                "providers": self.rerank_providers,
            },
        }
