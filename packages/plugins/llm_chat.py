from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from loguru import logger

from ..conversations.context import ConversationContext
from ..conversations.models import ConversationKey, IsolationMode
from ..decorators import event_handler, plugin
from ..providers.types import ProviderResponse
from .base import BasePlugin

__version__ = "0.3.0"

_DEFAULT_HISTORY_LIMIT = 20      # 保留的最大对话轮数
_COMPRESS_KEEP_TURNS = 5         # 压缩后保留的最近轮数
_SUMMARIZE_PROMPT = (
    "请将以下对话历史简洁地总结成几句话，保留关键信息和结论，"
    "不要包含无关细节。总结用中文输出。\n\n对话历史：\n{history}"
)

# provider_preferences 里存的 key（用户会话）
_PREF_ENABLED = "reply_enabled"
_PREF_MODEL = "preferred_model"
_PREF_PROVIDER = "preferred_provider"

# group settings 里存的 key
_PREF_GROUP_ENABLED = "group_reply_enabled"
_PREF_BLACKLIST = "user_blacklist"    # list[str] 黑名单 QQ 号
_PREF_WHITELIST = "user_whitelist"   # list[str] 白名单 QQ 号（非空时只响应名单内用户）


@plugin(
    name="llm_chat",
    version=__version__,
    description="Built-in LLM chat handler with history, persona, waking, commands",
)
class LLMChatPlugin(BasePlugin):
    @event_handler(event="message.private", description="Handle private messages")
    async def on_private_message(self, payload: dict[str, Any]) -> None:
        await self._handle_message(payload, is_group=False)

    @event_handler(event="message.group", description="Handle group messages")
    async def on_group_message(self, payload: dict[str, Any]) -> None:
        await self._handle_message(payload, is_group=True)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    async def _handle_message(
        self, payload: dict[str, Any], *, is_group: bool
    ) -> None:
        plain_text = payload.get("plain_text")
        if not isinstance(plain_text, str) or not plain_text.strip():
            return

        text = plain_text.strip()

        # --- 命令优先（不需要唤醒信号）---
        if text.startswith("/reset"):
            await self._cmd_reset()
            return
        if text.startswith("/llm"):
            await self._cmd_llm(text)
            return

        # --- 群聊回复总开关 + 黑/白名单检查 ---
        if is_group:
            if not self._is_group_reply_enabled(payload):
                return
            actor_id = self.context.execution.actor_id
            if actor_id and not self._is_user_allowed(actor_id):
                return

        # --- 群聊唤醒检查 ---
        text, should_respond = self._check_wake(payload, text, is_group)
        if not should_respond:
            return

        # --- 回复开关检查 ---
        if not self._is_reply_enabled():
            return

        provider_name = self._resolve_provider_name()
        if provider_name is None:
            logger.warning("llm_chat: no provider configured, skipping")
            return

        model = self._resolve_model()
        system_prompt = self._get_system_prompt()
        nickname = self._extract_nickname(payload)
        actor_id = self.context.execution.actor_id
        messages = self._build_messages(text, nickname=nickname, actor_id=actor_id)

        logger.info(
            "llm_chat: provider={} model={} history_turns={} text={}",
            provider_name,
            model or "default",
            len(messages) // 2,
            text[:80] + "..." if len(text) > 80 else text,
        )

        try:
            result = await self.request_provider(
                provider_name,
                messages=messages,
                system_prompt=system_prompt,
                model=model,
            )
        except Exception as exc:
            logger.error("llm_chat: provider call failed: {}", exc)
            await self.reply("喵～出了点问题，稍后再试吧 (´；ω；`)")
            return

        if not isinstance(result, ProviderResponse):
            logger.warning("llm_chat: unexpected result type: {}", type(result))
            return

        if result.error:
            logger.error("llm_chat: provider error: {}", result.error.message)
            await self.reply("喵～服务返回了错误，稍后再试吧")
            return

        if not result.content:
            logger.warning("llm_chat: empty response from provider")
            return

        await self._save_history(text, result.content, provider_name, model)
        await self.reply(result.content)

    # ------------------------------------------------------------------
    # 命令处理
    # ------------------------------------------------------------------

    async def _cmd_reset(self) -> None:
        """清空当前对话的历史记录和摘要。"""
        conversation = self.context.conversation
        if conversation is None:
            await self.reply("当前对话上下文不存在，无需重置。")
            return
        cleared = replace(conversation, history=[], summary=None)
        self.context.conversation = self.context.save_conversation(cleared)
        logger.info(
            "llm_chat: conversation reset for key={}", conversation.conversation_key
        )
        await self.reply("✅ 对话历史已清空，我们重新开始吧！")

    async def _cmd_llm(self, text: str) -> None:
        """/llm [on|off|model <name>|provider <name>|status] — 控制 LLM 行为。"""
        parts = text.split()
        sub = parts[1].lower() if len(parts) > 1 else "status"

        _ADMIN_SUBS = {"on", "off", "model", "provider", "reset", "clearmodel",
                       "compress", "summarize", "group", "blacklist", "whitelist"}
        if sub in _ADMIN_SUBS and not self.check_permissions("command.invoke"):
            await self.reply("喵～你没有权限使用此命令 (＞﹏＜)")
            return

        conversation = self.context.conversation
        prefs: dict[str, object] = dict(
            conversation.provider_preferences if conversation else {}
        )

        if sub == "off":
            prefs[_PREF_ENABLED] = False
            self._save_prefs(prefs)
            await self.reply("🔕 已关闭自动回复，发送 /llm on 可重新开启。")

        elif sub == "on":
            prefs[_PREF_ENABLED] = True
            self._save_prefs(prefs)
            await self.reply("🔔 已开启自动回复。")

        elif sub == "model" and len(parts) > 2:
            model_name = parts[2]
            prefs[_PREF_MODEL] = model_name
            self._save_prefs(prefs)
            await self.reply(f"✅ 模型已切换为：{model_name}")

        elif sub == "provider" and len(parts) > 2:
            provider_name = parts[2]
            prefs[_PREF_PROVIDER] = provider_name
            self._save_prefs(prefs)
            await self.reply(f"✅ Provider 已切换为：{provider_name}")

        elif sub == "reset" or sub == "clearmodel":
            prefs.pop(_PREF_MODEL, None)
            prefs.pop(_PREF_PROVIDER, None)
            self._save_prefs(prefs)
            await self.reply("✅ 已恢复默认模型和 Provider。")

        elif sub == "compress" or sub == "summarize":
            await self._do_compress()

        elif sub == "group" and len(parts) > 2:
            await self._cmd_llm_group(parts[2].lower())

        elif sub == "blacklist":
            await self._cmd_list_manage(_PREF_BLACKLIST, parts)

        elif sub == "whitelist":
            await self._cmd_list_manage(_PREF_WHITELIST, parts)

        else:
            # status
            enabled = prefs.get(_PREF_ENABLED, True)
            model = prefs.get(_PREF_MODEL) or "默认"
            provider = (
                prefs.get(_PREF_PROVIDER)
                or self.context.configuration.resolve_provider_name()
                or "未配置"
            )
            turns = len(conversation.history) // 2 if conversation else 0
            has_summary = bool(conversation.summary if conversation else False)
            is_group = self.context.execution.scope == "group"
            group_line = ""
            bl_line = ""
            wl_line = ""
            if is_group:
                group_enabled = self._is_group_reply_enabled(None)
                gs = self._load_group_settings()
                bl = gs.provider_preferences.get(_PREF_BLACKLIST, [])
                wl = gs.provider_preferences.get(_PREF_WHITELIST, [])
                group_line = f"• 群回复：{'开启' if group_enabled else '关闭'}\n"
                bl_line = (
                    f"• 黑名单：{', '.join(str(u) for u in bl) or '(空)'}\n"
                )
                wl_line = (
                    f"• 白名单：{', '.join(str(u) for u in wl) or '(空)'}\n"
                )
            await self.reply(
                f"📊 LLM 状态\n"
                f"• 自动回复：{'开启' if enabled else '关闭'}\n"
                f"{group_line}"
                f"{bl_line}"
                f"{wl_line}"
                f"• Provider：{provider}\n"
                f"• 模型：{model}\n"
                f"• 历史轮数：{turns}\n"
                f"• 有摘要：{'是' if has_summary else '否'}\n\n"
                f"命令：/llm on|off | /llm group on|off\n"
                f"/llm blacklist add/remove/clear <qq>\n"
                f"/llm whitelist add/remove/clear <qq>\n"
                f"/llm model <名称> | /llm provider <名称>\n"
                f"/llm compress | /reset"
            )

    async def _cmd_list_manage(self, pref_key: str, parts: list[str]) -> None:
        """管理黑名单/白名单：add/remove/clear/list <qq>"""
        label = "黑名单" if pref_key == _PREF_BLACKLIST else "白名单"
        if self.context.execution.group_id is None:
            await self.reply("此命令仅在群聊中有效。")
            return
        action = parts[2].lower() if len(parts) > 2 else "list"
        gs = self._load_group_settings()
        prefs = dict(gs.provider_preferences)
        current: list[str] = list(prefs.get(pref_key, []))  # type: ignore[arg-type]

        if action == "list":
            await self.reply(
                f"📋 {label}：{', '.join(current) if current else '(空)'}"
            )
            return

        if action == "clear":
            prefs[pref_key] = []
            self._save_group_settings(gs, prefs)
            await self.reply(f"✅ 已清空{label}。")
            return

        if len(parts) < 4:
            cmd = "blacklist" if pref_key == _PREF_BLACKLIST else "whitelist"
            await self.reply(f"用法：/llm {cmd} add/remove/clear/list <qq>")
            return

        target_id = str(parts[3])
        if action == "add":
            if target_id not in current:
                current.append(target_id)
            prefs[pref_key] = current
            self._save_group_settings(gs, prefs)
            await self.reply(f"✅ 已将 {target_id} 加入{label}。")
        elif action == "remove":
            if target_id in current:
                current.remove(target_id)
                prefs[pref_key] = current
                self._save_group_settings(gs, prefs)
                await self.reply(f"✅ 已将 {target_id} 移出{label}。")
            else:
                await self.reply(f"{target_id} 不在{label}中。")
        else:
            await self.reply(f"未知操作：{action}")

    def _load_group_settings(self) -> ConversationContext:
        group_id = self.context.execution.group_id or "global"
        key = self._group_settings_key(group_id)
        return self.context.load_conversation(key) or ConversationContext(
            isolation_mode=IsolationMode.SHARED_GROUP,
            conversation_key=ConversationKey(key),
            scope="group",
            chat_id=group_id,
        )

    def _save_group_settings(
        self, existing: ConversationContext, prefs: dict[str, object]
    ) -> None:
        self.context.save_conversation(replace(existing, provider_preferences=prefs))

    def _is_user_allowed(self, user_id: str) -> bool:
        """黑名单/白名单检查。黑名单命中 → 拒绝；白名单非空且未命中 → 拒绝。"""
        gs = self._load_group_settings()
        prefs = gs.provider_preferences
        blacklist: list[object] = prefs.get(_PREF_BLACKLIST, [])  # type: ignore[assignment]
        if isinstance(blacklist, list) and user_id in blacklist:
            logger.debug("llm_chat: user {} is blacklisted", user_id)
            return False
        whitelist: list[object] = prefs.get(_PREF_WHITELIST, [])  # type: ignore[assignment]
        if isinstance(whitelist, list) and whitelist and user_id not in whitelist:
            logger.debug("llm_chat: user {} not in whitelist", user_id)
            return False
        return True

    async def _cmd_llm_group(self, action: str) -> None:
        """/llm group on|off — 控制当前群的全局回复开关（需管理员权限）。"""
        if self.context.execution.group_id is None:
            await self.reply("此命令仅在群聊中有效。")
            return
        gs = self._load_group_settings()
        prefs = dict(gs.provider_preferences)
        if action == "off":
            prefs[_PREF_GROUP_ENABLED] = False
            self._save_group_settings(gs, prefs)
            await self.reply("🔕 已关闭本群自动回复，发送 /llm group on 可重新开启。")
        elif action == "on":
            prefs[_PREF_GROUP_ENABLED] = True
            self._save_group_settings(gs, prefs)
            await self.reply("🔔 已开启本群自动回复。")
        else:
            await self.reply("用法：/llm group on|off")

    def _group_settings_key(self, group_id: str) -> str:
        instance = self.context.execution.platform_instance_uuid or "default"
        return f"group_settings:{instance}:{group_id}"

    def _is_group_reply_enabled(self, payload: dict[str, Any] | None) -> bool:
        group_id = self.context.execution.group_id
        if group_id is None:
            return True
        key = self._group_settings_key(group_id)
        ctx = self.context.load_conversation(key)
        if ctx is None:
            return True
        return bool(ctx.provider_preferences.get(_PREF_GROUP_ENABLED, True))

    def _save_prefs(self, prefs: dict[str, object]) -> None:
        conversation = self.context.conversation
        if conversation is None:
            return
        updated = replace(conversation, provider_preferences=prefs)
        self.context.conversation = self.context.save_conversation(updated)

    # ------------------------------------------------------------------
    # 唤醒逻辑
    # ------------------------------------------------------------------

    def _check_wake(
        self, payload: dict[str, Any], text: str, is_group: bool
    ) -> tuple[str, bool]:
        if not is_group:
            return text, True

        self_id = self._get_self_id(payload)
        if self_id and self._is_at_me(payload, self_id):
            stripped = self._strip_at_prefix(text, self_id)
            logger.debug("llm_chat: woken by @mention, self_id={}", self_id)
            return stripped, True

        chat_prefix = self._get_config_str("chat_prefix", "/chat")
        if text.startswith(chat_prefix):
            stripped = text[len(chat_prefix):].lstrip()
            if not stripped:
                return text, False
            logger.debug("llm_chat: woken by prefix {!r}", chat_prefix)
            return stripped, True

        keywords_raw = self.context.get_config("wake_keywords")
        if isinstance(keywords_raw, list):
            for kw in keywords_raw:
                if isinstance(kw, str) and kw and kw in text:
                    logger.debug("llm_chat: woken by keyword {!r}", kw)
                    return text, True

        return text, False

    def _get_self_id(self, payload: dict[str, Any]) -> str | None:
        raw = payload.get("raw_event")
        if isinstance(raw, dict):
            self_id = raw.get("self_id")
            if isinstance(self_id, (str, int)):
                return str(self_id)
        meta = payload.get("metadata")
        if isinstance(meta, dict):
            self_id = meta.get("onebot_self_id")
            if isinstance(self_id, str):
                return self_id
        return None

    def _is_at_me(self, payload: dict[str, Any], self_id: str) -> bool:
        segments = payload.get("segments")
        if not isinstance(segments, list):
            return False
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            if seg.get("type") == "at":
                data = seg.get("data", {})
                if isinstance(data, dict) and str(data.get("qq", "")) == self_id:
                    return True
        return False

    def _strip_at_prefix(self, text: str, self_id: str) -> str:
        stripped = text.strip()
        prefix = f"@{self_id}"
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):].lstrip()
        return stripped or text

    # ------------------------------------------------------------------
    # 历史记录 & 摘要
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        user_text: str,
        *,
        nickname: str | None = None,
        actor_id: str | None = None,
    ) -> list[dict[str, object]]:
        conversation = self.context.conversation
        history_limit = self._get_config_int("history_limit", _DEFAULT_HISTORY_LIMIT)
        messages: list[dict[str, object]] = []

        if conversation is not None:
            # 如果有摘要，注入为首条 system 消息
            if conversation.summary:
                messages.append({
                    "role": "system",
                    "content": f"[对话历史摘要]\n{conversation.summary}",
                })

            history = conversation.history
            cutoff = max(0, len(history) - history_limit * 2)
            for entry in history[cutoff:]:
                role = entry.get("role")
                content = entry.get("content")
                if isinstance(role, str) and isinstance(content, str):
                    messages.append({"role": role, "content": content})

        # 注入当前时间 + 用户信息
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ctx_parts = [f"当前时间：{now}"]
        if nickname:
            ctx_parts.append(f"用户名：{nickname}")
        if actor_id and self._get_config_bool("inject_user_id", False):
            ctx_parts.append(f"用户ID：{actor_id}")
        messages.append({
            "role": "system",
            "content": "[当前上下文] " + "、".join(ctx_parts),
        })

        messages.append({"role": "user", "content": user_text})
        return messages

    async def _save_history(
        self,
        user_text: str,
        assistant_text: str,
        provider_name: str,
        model: str | None,
    ) -> None:
        conversation = self.context.conversation
        if conversation is None:
            return

        new_history = list(conversation.history) + [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ]

        history_limit = self._get_config_int("history_limit", _DEFAULT_HISTORY_LIMIT)
        compress_threshold = history_limit * 2  # 超过阈值才压缩

        summary = conversation.summary
        if len(new_history) > compress_threshold:
            summary, new_history = await self._compress(
                new_history, provider_name, model
            )

        updated = replace(conversation, history=new_history, summary=summary)
        self.context.conversation = self.context.save_conversation(updated)
        logger.debug(
            "llm_chat: saved history turns={} has_summary={}",
            len(new_history) // 2,
            bool(summary),
        )

    async def _compress(
        self,
        history: list[dict[str, object]],
        provider_name: str,
        model: str | None,
    ) -> tuple[str | None, list[dict[str, object]]]:
        """将超出部分的历史摘要化，保留最近 N 轮。"""
        keep = _COMPRESS_KEEP_TURNS * 2
        to_summarize = history[:-keep] if len(history) > keep else history
        recent = history[-keep:] if len(history) > keep else []

        history_text = "\n".join(
            f"{e.get('role', '?')}: {e.get('content', '')}"
            for e in to_summarize
            if isinstance(e.get("role"), str) and isinstance(e.get("content"), str)
        )
        prompt = _SUMMARIZE_PROMPT.format(history=history_text)

        try:
            result = await self.request_provider(
                provider_name,
                messages=[{"role": "user", "content": prompt}],
                model=model,
            )
            if isinstance(result, ProviderResponse) and result.content:
                logger.info(
                    "llm_chat: compressed {} turns into summary", len(to_summarize) // 2
                )
                return result.content, recent
        except Exception as exc:
            logger.warning(
                "llm_chat: compression failed, keeping full history: {}", exc
            )

        # 压缩失败时只截断，不生成摘要
        return None, history[-keep:]

    async def _do_compress(self) -> None:
        """手动触发压缩（/llm compress）。"""
        conversation = self.context.conversation
        if conversation is None or not conversation.history:
            await self.reply("当前没有历史记录可以压缩。")
            return

        provider_name = self._resolve_provider_name()
        if provider_name is None:
            await self.reply("未配置 Provider，无法压缩。")
            return

        model = self._resolve_model()
        summary, new_history = await self._compress(
            conversation.history, provider_name, model
        )
        updated = replace(conversation, history=new_history, summary=summary)
        self.context.conversation = self.context.save_conversation(updated)

        if summary:
            await self.reply(
                f"✅ 已压缩历史记录（保留最近 {_COMPRESS_KEEP_TURNS} 轮）\n\n"
                f"📝 摘要：{summary[:200]}{'...' if len(summary) > 200 else ''}"
            )
        else:
            await self.reply(f"✅ 已截断历史记录，保留最近 {_COMPRESS_KEEP_TURNS} 轮。")

    # ------------------------------------------------------------------
    # 配置 & 偏好 helpers
    # ------------------------------------------------------------------

    def _is_reply_enabled(self) -> bool:
        conversation = self.context.conversation
        if conversation is None:
            return True
        return bool(conversation.provider_preferences.get(_PREF_ENABLED, True))

    def _resolve_provider_name(self) -> str | None:
        conversation = self.context.conversation
        if conversation is not None:
            pref = conversation.provider_preferences.get(_PREF_PROVIDER)
            if isinstance(pref, str) and pref:
                return pref
        return self.context.configuration.resolve_provider_name()

    def _resolve_model(self) -> str | None:
        conversation = self.context.conversation
        if conversation is not None:
            pref = conversation.provider_preferences.get(_PREF_MODEL)
            if isinstance(pref, str) and pref:
                return pref
        return None

    def _get_system_prompt(self) -> str | None:
        raw = self.context.get_config("system_prompt")
        return raw if isinstance(raw, str) and raw.strip() else None

    def _extract_nickname(self, payload: dict[str, Any]) -> str | None:
        sender = payload.get("sender")
        if isinstance(sender, dict):
            name = sender.get("card") or sender.get("nickname")
            if isinstance(name, str) and name:
                return name
        return None

    def _get_config_str(self, key: str, default: str) -> str:
        val = self.context.get_config(key)
        return val if isinstance(val, str) else default

    def _get_config_int(self, key: str, default: int) -> int:
        val = self.context.get_config(key)
        return val if isinstance(val, int) else default

    def _get_config_bool(self, key: str, default: bool) -> bool:
        val = self.context.get_config(key)
        return val if isinstance(val, bool) else default
