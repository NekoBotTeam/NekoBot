"""OpenAI TTS Provider

支持 OpenAI 的 TTS API，包括 tts-1 和 tts-1-hd 模型
"""

from typing import Optional
from loguru import logger

from .tts_base import TTSProvider
from .register import register_tts_provider
from openai import AsyncOpenAI
import os


@register_tts_provider(
    provider_type_name="openai_tts",
    desc="OpenAI TTS Provider (tts-1, tts-1-hd)",
    default_config_tmpl={
        "type": "openai_tts",
        "enable": False,
        "id": "openai_tts",
        "model": "tts-1",
        "voice": "alloy",
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
    },
    provider_display_name="OpenAI TTS",
)
class OpenAITTSProvider(TTSProvider):
    """OpenAI TTS 服务提供商"""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.base_url = provider_config.get("base_url", "https://api.openai.com/v1")
        self.model = provider_config.get("model", "tts-1")
        self.voice = provider_config.get("voice", "alloy")
        self.timeout = provider_config.get("timeout", 60)
        self.output_dir = provider_config.get("output_dir", "data/tts")
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

        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)

        self._client = self._get_client()
        logger.info("[OpenAI TTS] TTS Provider 已初始化")

    async def close(self) -> None:
        """关闭 Provider"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.info("[OpenAI TTS] TTS Provider 已关闭")

    async def get_audio(self, text: str) -> str:
        """获取文本的音频，返回音频文件路径

        Args:
            text: 要转换的文本

        Returns:
            音频文件路径
        """
        if not text:
            raise ValueError("文本不能为空")

        client = self._get_client()

        try:
            response = await client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=text,
            )

            # 生成输出文件名
            import time
            import hashlib

            text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            timestamp = int(time.time())
            filename = f"tts_{text_hash}_{timestamp}.mp3"
            filepath = os.path.join(self.output_dir, filename)

            # 保存音频文件
            response.stream_to_file(filepath)

            logger.info(f"[OpenAI TTS] 音频生成成功: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"[OpenAI TTS] 音频生成失败: {e}")
            raise

    async def get_models(self) -> list[str]:
        """获取支持的模型列表"""
        return ["tts-1", "tts-1-hd"]

    async def test(self) -> None:
        """测试 Provider 是否可用"""
        await self.get_audio("Hello, this is a test.")
