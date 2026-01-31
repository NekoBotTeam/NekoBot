"""Provider 单元测试

测试新增的 TTS、STT、Embedding、Rerank 提供商功能
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from packages.provider.sources import (
    edge_tts_provider,
    dashscope_tts_provider,
    dashscope_stt_provider,
    gemini_embedding_provider,
    cohere_rerank_provider,
)


class TestEdgeTTSProvider:
    """Edge TTS 提供商测试"""

    @pytest.fixture
    def provider_config(self):
        return {
            "type": "edge_tts",
            "enable": True,
            "id": "test_edge_tts",
            "voice": "zh-CN-XiaoxiaoNeural",
            "rate": "+0%",
            "pitch": "+0Hz",
            "output_dir": "data/tts_test",
        }

    @pytest.fixture
    def provider_settings(self):
        return {}

    @pytest.fixture
    def provider(self, provider_config, provider_settings):
        return edge_tts_provider.EdgeTTSProvider(provider_config, provider_settings)

    def test_initialization(self, provider, provider_config):
        """测试初始化"""
        assert provider.voice == provider_config["voice"]
        assert provider.rate == provider_config["rate"]
        assert provider.pitch == provider_config["pitch"]
        assert provider.output_dir == provider_config["output_dir"]

    @pytest.mark.asyncio
    async def test_get_audio(self, provider):
        """测试获取音频"""
        with patch("edge_tts.Communicate") as mock_communicate_class:
            # Mock communicate instance
            mock_communicate = MagicMock()
            mock_communicate_class.return_value = mock_communicate

            # Mock save method
            mock_communicate.save = AsyncMock()

            # Test
            result = await provider.get_audio("测试语音")

            # Verify
            mock_communicate.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_models(self, provider):
        """测试获取语音列表"""
        with patch("edge_tts.list_voices") as mock_list_voices:
            # Mock voices
            mock_list_voices.return_value = [
                {"Name": "zh-CN-XiaoxiaoNeural"},
                {"Name": "zh-CN-YunxiNeural"},
            ]

            models = await provider.get_models()

            assert "zh-CN-XiaoxiaoNeural" in models
            assert "zh-CN-YunxiNeural" in models


class TestDashScopeTTSProvider:
    """DashScope TTS 提供商测试"""

    @pytest.fixture
    def provider_config(self):
        return {
            "type": "dashscope_tts",
            "enable": True,
            "id": "test_dashscope_tts",
            "model": "cosyvoice-v1",
            "voice": "longxiaochun",
            "format": "mp3",
            "rate": "1.0",
            "volume": "50",
            "api_key": "test_key",
            "output_dir": "data/tts_test",
        }

    @pytest.fixture
    def provider_settings(self):
        return {}

    @pytest.fixture
    def provider(self, provider_config, provider_settings):
        return dashscope_tts_provider.DashScopeTTSProvider(
            provider_config, provider_settings
        )

    def test_initialization(self, provider, provider_config):
        """测试初始化"""
        assert provider.api_key == provider_config["api_key"]
        assert provider.model == provider_config["model"]
        assert provider.voice == provider_config["voice"]
        assert provider.format == provider_config["format"]

    @pytest.mark.asyncio
    async def test_get_audio(self, provider):
        """测试获取音频"""
        with patch(
            "dashscope.api_plugins.tts.AioSpeechSynthesizer"
        ) as mock_synthesizer_class:
            # Mock synthesizer
            mock_synthesizer = MagicMock()
            mock_synthesizer_class.return_value = mock_synthesizer

            # Mock call result
            mock_result = MagicMock()
            mock_result.get_audio_file.return_value = b"fake_audio_data"
            mock_result.get_message.return_value = "success"
            mock_synthesizer.call = AsyncMock(return_value=mock_result)

            # Mock open and write
            with patch("builtins.open", MagicMock()):
                result = await provider.get_audio("测试语音")

                # Verify
                assert result.endswith(".mp3")

    @pytest.mark.asyncio
    async def test_get_models(self, provider):
        """测试获取模型列表"""
        models = await provider.get_models()

        assert "cosyvoice-v1" in models
        assert isinstance(models, list)


class TestDashScopeSTTProvider:
    """DashScope STT 提供商测试"""

    @pytest.fixture
    def provider_config(self):
        return {
            "type": "dashscope_stt",
            "enable": True,
            "id": "test_dashscope_stt",
            "model": "paraformer-realtime-v2",
            "format": "wav",
            "sample_rate": "16000",
            "api_key": "test_key",
        }

    @pytest.fixture
    def provider_settings(self):
        return {}

    @pytest.fixture
    def provider(self, provider_config, provider_settings):
        return dashscope_stt_provider.DashScopeSTTProvider(
            provider_config, provider_settings
        )

    def test_initialization(self, provider, provider_config):
        """测试初始化"""
        assert provider.api_key == provider_config["api_key"]
        assert provider.model == provider_config["model"]
        assert provider.format == provider_config["format"]
        assert provider.sample_rate == provider_config["sample_rate"]

    @pytest.mark.asyncio
    async def test_get_text(self, provider):
        """测试获取文本"""
        with patch("dashscope.audio.asr.Transcription") as mock_transcription_class:
            # Mock transcription
            mock_transcription_class.call.return_value = MagicMock(
                status_code=200,
                output=MagicMock(
                    results=[MagicMock(sentences=[MagicMock(text="测试文本")])]
                ),
            )

            # Test
            result = await provider.get_text("test_audio.wav")

            # Verify
            assert result == "测试文本"

    @pytest.mark.asyncio
    async def test_get_models(self, provider):
        """测试获取模型列表"""
        models = await provider.get_models()

        assert "paraformer-realtime-v2" in models
        assert isinstance(models, list)


class TestGeminiEmbeddingProvider:
    """Gemini Embedding 提供商测试"""

    @pytest.fixture
    def provider_config(self):
        return {
            "type": "gemini_embedding",
            "enable": True,
            "id": "test_gemini_embedding",
            "model": "text-embedding-004",
            "api_key": "test_key",
        }

    @pytest.fixture
    def provider_settings(self):
        return {}

    @pytest.fixture
    def provider(self, provider_config, provider_settings):
        return gemini_embedding_provider.GeminiEmbeddingProvider(
            provider_config, provider_settings
        )

    def test_initialization(self, provider, provider_config):
        """测试初始化"""
        assert provider.api_key == provider_config["api_key"]
        assert provider.model == provider_config["model"]

    @pytest.mark.asyncio
    async def test_get_embedding(self, provider):
        """测试获取向量"""
        with patch("google.generativeai.embed_content") as mock_embed_content:
            # Mock embedding result
            mock_embed_content.return_value = {
                "embedding": [0.1, 0.2, 0.3] * 256,
            }

            # Test
            result = await provider.get_embedding("测试文本")

            # Verify
            assert isinstance(result, list)
            assert len(result) > 0
            assert all(isinstance(x, float) for x in result)

    @pytest.mark.asyncio
    async def test_get_embeddings(self, provider):
        """测试批量获取向量"""
        with patch("google.generativeai.embed_content") as mock_embed_content:
            # Mock embedding result
            mock_embed_content.return_value = {
                "embedding": [0.1, 0.2, 0.3] * 256,
            }

            # Test
            results = await provider.get_embeddings(["文本1", "文本2"])

            # Verify
            assert isinstance(results, list)
            assert len(results) == 2
            assert all(isinstance(x, list) for x in results)

    def test_get_dim(self, provider):
        """测试获取维度"""
        dim = provider.get_dim()
        assert isinstance(dim, int)
        assert dim > 0

    @pytest.mark.asyncio
    async def test_get_models(self, provider):
        """测试获取模型列表"""
        models = await provider.get_models()

        assert "text-embedding-004" in models
        assert isinstance(models, list)


class TestCohereRerankProvider:
    """Cohere Rerank 提供商测试"""

    @pytest.fixture
    def provider_config(self):
        return {
            "type": "cohere_rerank",
            "enable": True,
            "id": "test_cohere_rerank",
            "model": "rerank-v3.5",
            "api_key": "test_key",
            "top_n": None,
        }

    @pytest.fixture
    def provider_settings(self):
        return {}

    @pytest.fixture
    def provider(self, provider_config, provider_settings):
        return cohere_rerank_provider.CohereRerankProvider(
            provider_config, provider_settings
        )

    def test_initialization(self, provider, provider_config):
        """测试初始化"""
        assert provider.api_key == provider_config["api_key"]
        assert provider.model == provider_config["model"]
        assert provider.default_top_n == provider_config["top_n"]

    @pytest.mark.asyncio
    async def test_rerank(self, provider):
        """测试重排序"""
        from packages.provider.rerank_base import RerankResult

        with patch("cohere.AsyncClient") as mock_client_class:
            # Mock client
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock rerank result
            mock_result = MagicMock()
            mock_result.results = [
                MagicMock(index=0, relevance_score=0.9),
                MagicMock(index=1, relevance_score=0.7),
            ]
            mock_client.rerank = AsyncMock(return_value=mock_result)

            # Test
            results = await provider.rerank(
                query="查询",
                documents=["文档1", "文档2"],
                top_n=2,
            )

            # Verify
            assert isinstance(results, list)
            assert len(results) == 2
            assert all(isinstance(x, RerankResult) for x in results)
            assert results[0].score == 0.9
            assert results[1].score == 0.7

    @pytest.mark.asyncio
    async def test_get_models(self, provider):
        """测试获取模型列表"""
        models = await provider.get_models()

        assert "rerank-v3.5" in models
        assert isinstance(models, list)
