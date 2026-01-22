"""消息构建工具

提供统一的消息构建逻辑，避免在各个 Provider 中重复实现
"""

from typing import Any


class MessageBuilder:
    """消息构建器

    统一处理 LLM 请求消息的构建逻辑
    """

    @staticmethod
    def build_messages(
        prompt: str | None = None,
        system_prompt: str | None = None,
        contexts: list[dict] | None = None,
        image_urls: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """构建 LLM 消息列表

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            contexts: 对话上下文历史
            image_urls: 图片 URL 列表

        Returns:
            构建好的消息列表
        """
        messages: list[dict[str, Any]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if contexts:
            messages.extend(contexts)

        if prompt:
            user_message: dict[str, Any] = {"role": "user", "content": prompt}
            if image_urls:
                user_message["content"] = [
                    {"type": "text", "text": prompt},
                    *[
                        {"type": "image_url", "image_url": {"url": url}}
                        for url in image_urls
                    ],
                ]
            messages.append(user_message)
        elif image_urls:
            messages.append(
                {"role": "user", "content": [{"type": "text", "text": "[图片]"}]}
            )

        return messages

    @staticmethod
    def build_assistant_message(content: str) -> dict[str, str]:
        """构建助手消息

        Args:
            content: 消息内容

        Returns:
            助手消息字典
        """
        return {"role": "assistant", "content": content}

    @staticmethod
    def build_user_message(content: str) -> dict[str, str]:
        """构建用户消息

        Args:
            content: 消息内容

        Returns:
            用户消息字典
        """
        return {"role": "user", "content": content}

    @staticmethod
    def build_system_message(content: str) -> dict[str, str]:
        """构建系统消息

        Args:
            content: 消息内容

        Returns:
            系统消息字典
        """
        return {"role": "system", "content": content}

    @staticmethod
    def add_context_to_messages(
        messages: list[dict[str, Any]], context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """向消息列表添加上下文

        Args:
            messages: 原有消息列表
            context: 要添加的上下文

        Returns:
            更新后的消息列表
        """
        messages.append(context)
        return messages

    @staticmethod
    def truncate_messages(
        messages: list[dict[str, Any]], max_messages: int = 20, keep_system: bool = True
    ) -> list[dict[str, Any]]:
        """截断消息列表，防止超出 token 限制

        Args:
            messages: 原始消息列表
            max_messages: 最大消息数量
            keep_system: 是否保留系统消息

        Returns:
            截断后的消息列表
        """
        if not messages:
            return []

        system_messages = (
            [m for m in messages if m.get("role") == "system"] if keep_system else []
        )
        other_messages = [m for m in messages if m.get("role") != "system"]

        return system_messages + other_messages[-max_messages:]

    @staticmethod
    def merge_user_content(
        messages: list[dict[str, Any]],
        new_content: str,
        new_images: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """合并用户消息内容

        Args:
            messages: 原始消息列表
            new_content: 新的文本内容
            new_images: 新的图片列表

        Returns:
            更新后的消息列表
        """
        if not messages:
            messages = []

        last_message = messages[-1] if messages else None

        if last_message and last_message.get("role") == "user":
            existing_content = last_message.get("content", "")

            if isinstance(existing_content, str):
                new_message_content = existing_content + new_content
                if new_images:
                    new_message_content = [
                        {"type": "text", "text": new_message_content},
                        *[
                            {"type": "image_url", "image_url": {"url": url}}
                            for url in new_images
                        ],
                    ]
            elif isinstance(existing_content, list):
                new_message_content = existing_content.copy()
                if new_content:
                    new_message_content.append({"type": "text", "text": new_content})
                if new_images:
                    new_message_content.extend(
                        [
                            {"type": "image_url", "image_url": {"url": url}}
                            for url in new_images
                        ]
                    )
            else:
                new_message_content = new_content
                if new_images:
                    new_message_content = [
                        {"type": "text", "text": new_content},
                        *[
                            {"type": "image_url", "image_url": {"url": url}}
                            for url in new_images
                        ],
                    ]

            messages[-1]["content"] = new_message_content
        else:
            messages.append(MessageBuilder.build_user_message(new_content))

        return messages


__all__ = [
    "MessageBuilder",
]
