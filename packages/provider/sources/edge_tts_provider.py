"""Edge TTS Provider

Microsoft Edge TTS 提供的免费在线语音合成服务，不需要 API 密钥
"""

from typing import Optional
from loguru import logger
from pathlib import Path
import time
import hashlib

from .tts_base import TTSProvider
from .register import register_tts_provider


@register_tts_provider(
    provider_type_name="edge_tts",
    desc="Microsoft Edge TTS Provider (免费在线TTS)",
    default_config_tmpl={
        "type": "edge_tts",
        "enable": False,
        "id": "edge_tts",
        "voice": "zh-CN-XiaoxiaoNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "output_dir": "data/tts",
    },
    provider_display_name="Edge TTS",
)
class EdgeTTSProvider(TTSProvider):
    """Edge TTS 服务提供商"""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.voice = provider_config.get("voice", "zh-CN-XiaoxiaoNeural")
        self.rate = provider_config.get("rate", "+0%")
        self.pitch = provider_config.get("pitch", "+0Hz")
        self.output_dir = provider_config.get("output_dir", "data/tts")
        self._communicate: Optional = None

    async def initialize(self) -> None:
        """初始化 Provider"""
        import edge_tts

        # 创建输出目录
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        self._communicate = edge_tts.Communicate(
            text="", voice=self.voice, rate=self.rate, pitch=self.pitch
        )
        logger.info("[Edge TTS] TTS Provider 已初始化")

    async def close(self) -> None:
        """关闭 Provider"""
        self._communicate = None
        logger.info("[Edge TTS] TTS Provider 已关闭")

    async def get_audio(self, text: str) -> str:
        """获取文本的音频，返回音频文件路径

        Args:
            text: 要转换的文本

        Returns:
            音频文件路径
        """
        if not text:
            raise ValueError("文本不能为空")

        import edge_tts

        # 创建新的 Communicate 实例（因为 edge_tts 每次调用需要新的实例）
        communicate = edge_tts.Communicate(
            text=text, voice=self.voice, rate=self.rate, pitch=self.pitch
        )

        try:
            # 生成输出文件名
            text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            timestamp = int(time.time())
            filename = f"tts_{text_hash}_{timestamp}.mp3"
            filepath = Path(self.output_dir) / filename

            # 保存音频文件
            await communicate.save(str(filepath))

            logger.info(f"[Edge TTS] 音频生成成功: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"[Edge TTS] 音频生成失败: {e}")
            raise

    async def get_models(self) -> list[str]:
        """获取支持的语音列表"""
        try:
            import edge_tts

            voices = await edge_tts.list_voices()
            return [voice["Name"] for voice in voices]
        except Exception as e:
            logger.error(f"[Edge TTS] 获取语音列表失败: {e}")
            return [self.voice]

    async def test(self) -> None:
        """测试 Provider 是否可用"""
        await self.get_audio("测试语音合成")
