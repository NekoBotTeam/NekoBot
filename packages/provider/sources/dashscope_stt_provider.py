"""DashScope STT Provider

阿里云 DashScope 提供的语音识别服务
"""

from typing import Optional
from loguru import logger
from pathlib import Path
import os

from .stt_base import STTProvider
from .register import register_stt_provider
import dashscope
from dashscope.audio.asr import Transcription


@register_stt_provider(
    provider_type_name="dashscope_stt",
    desc="阿里云 DashScope STT Provider (语音识别)",
    default_config_tmpl={
        "type": "dashscope_stt",
        "enable": False,
        "id": "dashscope_stt",
        "model": "paraformer-realtime-v2",
        "format": "wav",
        "sample_rate": "16000",
        "api_key": "",
    },
    provider_display_name="阿里云 DashScope STT",
)
class DashScopeSTTProvider(STTProvider):
    """DashScope STT 服务提供商"""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.model = provider_config.get("model", "paraformer-realtime-v2")
        self.format = provider_config.get("format", "wav")
        self.sample_rate = provider_config.get("sample_rate", "16000")
        self.timeout = provider_config.get("timeout", 300)

    async def initialize(self) -> None:
        """初始化 Provider"""
        if not self.api_key:
            raise ValueError("DashScope API Key 未配置")

        # 设置 API Key
        dashscope.api_key = self.api_key

        logger.info("[DashScope STT] STT Provider 已初始化")

    async def close(self) -> None:
        """关闭 Provider"""
        logger.info("[DashScope STT] STT Provider 已关闭")

    async def get_text(self, audio_url: str) -> str:
        """获取音频的文本

        Args:
            audio_url: 音频文件路径或 URL

        Returns:
            识别出的文本
        """
        if not audio_url:
            raise ValueError("音频文件路径不能为空")

        try:
            # 判断是本地文件还是 URL
            if os.path.exists(audio_url):
                # 本地文件
                transcription = Transcription.call(
                    model=self.model,
                    file_urls=[f"file://{audio_url}"],
                    format=self.format,
                    sample_rate=int(self.sample_rate),
                )
            else:
                # URL
                transcription = Transcription.call(
                    model=self.model,
                    file_urls=[audio_url],
                    format=self.format,
                    sample_rate=int(self.sample_rate),
                )

            # 检查响应状态
            if transcription.status_code != 200:
                raise Exception(
                    f"语音识别失败: {transcription.code} - {transcription.message}"
                )

            # 解析结果
            text = ""
            if hasattr(transcription, "output") and transcription.output:
                if hasattr(transcription.output, "results"):
                    results = transcription.output.results
                    if results:
                        # 合并所有识别结果
                        sentences = []
                        for result in results:
                            if hasattr(result, "sentences"):
                                for sentence in result.sentences:
                                    if hasattr(sentence, "text"):
                                        sentences.append(sentence.text)
                        text = "".join(sentences)

            logger.info(f"[DashScope STT] 音频识别成功，文本长度: {len(text)}")
            return text

        except Exception as e:
            logger.error(f"[DashScope STT] 音频识别失败: {e}")
            raise

    async def get_models(self) -> list[str]:
        """获取支持的模型列表"""
        try:
            # DashScope STT 模型列表
            return [
                "paraformer-realtime-v2",
                "paraformer-8k-v1",
                "paraformer-16k-v1",
                "paraformer-mtl-v1",
                "paraformer-8k-thermal-v1",
                "paraformer-16k-thermal-v1",
            ]
        except Exception as e:
            logger.error(f"[DashScope STT] 获取模型列表失败: {e}")
            return [self.model]

    async def test(self) -> None:
        """测试 Provider 是否可用"""
        sample_audio_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "samples",
            "stt_health_check.wav",
        )

        if not os.path.exists(sample_audio_path):
            logger.warning(f"[DashScope STT] 测试音频文件不存在: {sample_audio_path}")
            return

        await self.get_text(sample_audio_path)
