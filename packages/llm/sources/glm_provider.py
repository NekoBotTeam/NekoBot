"""智谱 GLM LLM 提供商

支持智谱 GLM-4、GLM-3 等模型
"""

from typing import Any, Optional

from loguru import logger

from ..base import BaseLLMProvider, LLMProviderType
from ..register import register_llm_provider


@register_llm_provider(
    provider_type_name="glm",
    desc="智谱 GLM 提供商 (GLM-4, GLM-3 等)",
    provider_type=LLMProviderType.CHAT_COMPLETION,
    default_config_tmpl={
        "type": "glm",
        "enable": False,
        "id": "glm",
        "model": "glm-4-flash",
        "api_key": "",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "max_tokens": 4096,
        "temperature": 0.7,
    },
    provider_display_name="智谱 GLM",
)
class GLMProvider(BaseLLMProvider):
    """智谱 GLM LLM 提供商"""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.base_url = provider_config.get("base_url", "https://open.bigmodel.cn/api/paas/v4")
        self.max_tokens = provider_config.get("max_tokens", 4096)
        self.temperature = provider_config.get("temperature", 0.7)
        self._client: Optional[Any] = None

    async def initialize(self) -> None:
        """初始化提供商"""
        if not self.api_key:
            raise ValueError("GLM API Key 未配置")

        logger.info("[GLM] GLM 提供商已初始化")

    async def text_chat(
        self,
        prompt: str,
        session_id: str,
        contexts: Optional[list] = None,
    ) -> dict[str, Any]:
        """文本聊天

        Args:
            prompt: 用户提示词
            session_id: 会话 ID
            contexts: 上下文消息列表

        Returns:
            响应字典，包含 content 等字段
        """
        import httpx

        if not self.api_key:
            raise ValueError("GLM API Key 未配置")

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            messages = []
            if contexts:
                for ctx in contexts:
                    messages.append({
                        "role": ctx.get("role", "user"),
                        "content": ctx.get("content", "")
                    })
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()

                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    return {"content": content, "raw": result}
                else:
                    logger.warning(f"[GLM] 响应格式异常: {result}")
                    return {"content": "", "raw": result}

        except httpx.HTTPStatusError as e:
            logger.error(f"[GLM] API 请求失败: {e.response.status_code} - {e.response.text}")
            return {"content": "", "error": str(e)}
        except Exception as e:
            logger.error(f"[GLM] 文本聊天失败: {e}")
            return {"content": "", "error": str(e)}
