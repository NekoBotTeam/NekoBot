"""OpenAI STT Provider

支持 OpenAI Whisper API 进行语音转文字
"""

from typing import Optional
from loguru import logger

from .stt_base import STTProvider
from .register import register_stt_provider
from openai import AsyncOpenAI
import os


@register_stt_provider(
    provider_type_name="openai_stt",
    desc="OpenAI Whisper API Provider (whisper-1)",
    default_config_tmpl={
        "type": "openai_stt",
        "enable": False,
        "id": "openai_stt",
        "model": "whisper-1",
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
    },
    provider_display_name="OpenAI Whisper",
)
class OpenAISTTProvider(STTProvider):
    """OpenAI STT 服务提供商"""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.base_url = provider_config.get("base_url", "https://api.openai.com/v1")
        self.model = provider_config.get("model", "whisper-1")
        self.timeout = provider_config.get("timeout", 300)
        self._client: Optional[AsyncOpenAI] = None

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
        logger.info("[OpenAI STT] STT Provider 已初始化")

    async def close(self) -> None:
        """关闭 Provider"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.info("[OpenAI STT] STT Provider 已关闭")

    async def get_text(self, audio_url: str) -> str:
        """获取音频的文本

        Args:
            audio_url: 音频文件路径或 URL

        Returns:
            识别出的文本
        """
        if not audio_url:
            raise ValueError("音频文件路径不能为空")

        client = self._get_client()

        try:
            # 判断是本地文件还是 URL
            if os.path.exists(audio_url):
                with open(audio_url, "rb") as audio_file:
                    transcript = await client.audio.transcriptions.create(
                        model=self.model,
                        file=audio_file,
                    )
            else:
                # 如果是 URL，需要先下载
                import aiohttp

                async with aiohttp.ClientSession() as session:
                    async with session.get(audio_url) as resp:
                        if resp.status != 200:
                            raise Exception(f"下载音频文件失败: {resp.status}")
                        audio_data = await resp.read()

                import io

                audio_file = io.BytesIO(audio_data)
                audio_file.name = "audio.mp3"
                transcript = await client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                )

            text = transcript.text
            logger.info(f"[OpenAI STT] 音频识别成功，文本长度: {len(text)}")
            return text

        except Exception as e:
            logger.error(f"[OpenAI STT] 音频识别失败: {e}")
            raise

    async def get_models(self) -> list[str]:
        """获取支持的模型列表"""
        return ["whisper-1"]

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
            logger.warning(f"[OpenAI STT] 测试音频文件不存在: {sample_audio_path}")
            return

        await self.get_text(sample_audio_path)
