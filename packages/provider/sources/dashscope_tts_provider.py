"""DashScope TTS Provider

阿里云 DashScope 提供的语音合成服务
"""

from typing import Optional
from loguru import logger
from pathlib import Path
import time
import hashlib

from .tts_base import TTSProvider
from .register import register_tts_provider
import dashscope
from dashscope.api_plugins.tts import AioSpeechSynthesizer


@register_tts_provider(
    provider_type_name="dashscope_tts",
    desc="阿里云 DashScope TTS Provider (语音合成)",
    default_config_tmpl={
        "type": "dashscope_tts",
        "enable": False,
        "id": "dashscope_tts",
        "model": "cosyvoice-v1",
        "voice": "longxiaochun",
        "format": "mp3",
        "rate": "1.0",
        "volume": "50",
        "api_key": "",
        "output_dir": "data/tts",
    },
    provider_display_name="阿里云 DashScope TTS",
)
class DashScopeTTSProvider(TTSProvider):
    """DashScope TTS 服务提供商"""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.model = provider_config.get("model", "cosyvoice-v1")
        self.voice = provider_config.get("voice", "longxiaochun")
        self.format = provider_config.get("format", "mp3")
        self.rate = provider_config.get("rate", "1.0")
        self.volume = provider_config.get("volume", "50")
        self.output_dir = provider_config.get("output_dir", "data/tts")
        self.timeout = provider_config.get("timeout", 60)
        self._client: Optional[AioSpeechSynthesizer] = None

    def _get_client(self) -> AioSpeechSynthesizer:
        """获取或创建 DashScope TTS 客户端"""
        if self._client is None:
            self._client = AioSpeechSynthesizer(
                model=self.model,
                format=self.format,
                sample_rate=24000,
            )
        return self._client

    async def initialize(self) -> None:
        """初始化 Provider"""
        if not self.api_key:
            raise ValueError("DashScope API Key 未配置")

        # 设置 API Key
        dashscope.api_key = self.api_key

        # 创建输出目录
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        self._client = self._get_client()
        logger.info("[DashScope TTS] TTS Provider 已初始化")

    async def close(self) -> None:
        """关闭 Provider"""
        self._client = None
        logger.info("[DashScope TTS] TTS Provider 已关闭")

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
            # 调用语音合成API
            result = await client.call(
                text=text,
                voice=self.voice,
                rate=self.rate,
                volume=self.volume,
            )

            # 检查响应状态
            if result.get_audio_file() is None:
                raise Exception(f"语音合成失败: {result.get_message()}")

            # 生成输出文件名
            text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            timestamp = int(time.time())
            filename = f"tts_{text_hash}_{timestamp}.{self.format}"
            filepath = Path(self.output_dir) / filename

            # 保存音频文件
            with open(filepath, "wb") as f:
                f.write(result.get_audio_file())

            logger.info(f"[DashScope TTS] 音频生成成功: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"[DashScope TTS] 音频生成失败: {e}")
            raise

    async def get_models(self) -> list[str]:
        """获取支持的模型列表"""
        try:
            # DashScope TTS 模型列表
            return [
                "cosyvoice-v1",
                "sambert-zhichu-v1",
                "sambert-zhichu-2v1",
                "sambert-zhichu-editionv1",
                "sambert-zhichu-edition2v1",
            ]
        except Exception as e:
            logger.error(f"[DashScope TTS] 获取模型列表失败: {e}")
            return [self.model]

    async def test(self) -> None:
        """测试 Provider 是否可用"""
        await self.get_audio("测试语音合成")
