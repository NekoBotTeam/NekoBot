"""处理消息阶段

处理消息（Agent/LLM 请求）
"""

import asyncio
from typing import AsyncGenerator, Optional
from loguru import logger

from .stage import Stage, register_stage
from .context import PipelineContext


@register_stage
class ProcessStage(Stage):
    """处理消息阶段"""

    async def initialize(self, ctx: PipelineContext) -> None:
        """初始化阶段"""

    async def process(
        self, event: dict, ctx: PipelineContext
    ) -> Optional[AsyncGenerator[None, None]]:
        """处理消息事件

        Args:
            event: 事件数据
            ctx: Pipeline 上下文

        Returns:
            None
        """
        post_type = event.get("post_type")

        if post_type == "message":
            await self._process_message(event, ctx)
        elif post_type == "notice":
            await self._process_notice(event, ctx)
        elif post_type == "request":
            await self._process_request(event, ctx)

        return None

    async def _process_message(self, event: dict, ctx: PipelineContext) -> None:
        """处理消息事件"""
        message_type = event.get("message_type", "unknown")
        user_id = event.get("user_id", "unknown")
        group_id = event.get("group_id", "N/A")
        text_content = self._format_message(event)

        def _trim_text(t: str, n: int = 120) -> str:
            s = " ".join(t.splitlines())
            try:
                return s if len(s) <= n else s[: n - 3] + "..."
            except UnicodeEncodeError:
                # 如果遇到无法编码的字符，先使用 replace 过滤掉
                safe_chars = []
                for c in s:
                    try:
                        c.encode("gbk")
                        safe_chars.append(c)
                    except UnicodeEncodeError:
                        pass
                s_safe = "".join(safe_chars)
                return s_safe if len(s_safe) <= n else s_safe[: n - 3] + "..."
        text_log = _trim_text(text_content)
        sender = (
            event.get("sender", {}) if isinstance(event.get("sender"), dict) else {}
        )
        nickname = sender.get("card") or sender.get("nickname") or str(user_id)
        user_disp = f"{nickname}({user_id})"
        group_name = event.get("group_name")
        group_disp = f"{group_name}({group_id})" if group_name else f"{group_id}"
        if message_type == "group":
            logger.info(f"猫猫 | 接收 <- 群聊 [{group_disp}] [{user_disp}] {text_log}")
        else:
            logger.info(f"猫猫 | 接收 <- 私聊 [{user_disp}] {text_log}")

        message_type = event.get("message_type", "")
        event.get("message", "")

        # 获取 LLM 回复模式配置
        from ..config import load_config
        config = load_config()
        llm_reply_mode = config.get("llm_reply_mode", "active")

        # 检查是否被艾特
        is_at_me = self._check_if_at_me(event, ctx)

        # 检查是否是命令
        is_command = self._check_if_command(event, ctx)

        # 私聊消息处理
        if message_type == "private":
            await ctx.plugin_manager.handle_message(event)
            # passive 模式下私聊也不触发 LLM
            if llm_reply_mode != "passive":
                asyncio.create_task(self._trigger_llm_response(event, ctx))
            return

        # 群聊消息根据模式决定是否触发 LLM
        should_trigger_llm = False

        if llm_reply_mode == "active":
            # 主动模式：所有消息都触发
            should_trigger_llm = True
        elif llm_reply_mode == "passive":
            # 被动模式：不主动回复，只响应命令
            should_trigger_llm = False
        elif llm_reply_mode == "at":
            # 艾特模式：只有被艾特时触发
            should_trigger_llm = is_at_me
            logger.debug(f"艾特模式: is_at_me={is_at_me}, should_trigger_llm={should_trigger_llm}")
        elif llm_reply_mode == "command":
            # 命令模式：只有使用命令前缀时触发
            should_trigger_llm = is_command

        logger.debug(f"LLM 回复模式: {llm_reply_mode}, 触发: {should_trigger_llm}, 是命令: {is_command}")

        # 处理消息
        await ctx.plugin_manager.handle_message(event)

        # 如果是命令，先尝试处理命令
        if is_command:
            command_handled = await self._process_command(event, ctx)
            if not command_handled and should_trigger_llm:
                asyncio.create_task(self._trigger_llm_response(event, ctx))
        elif should_trigger_llm:
            asyncio.create_task(self._trigger_llm_response(event, ctx))

    async def _process_command(self, event: dict, ctx: PipelineContext) -> bool:
        """处理命令"""
        from ..server import format_message

        normalized_text = format_message(event, simple=False)
        platform_id = event.get("platform_id", "onebot")
        platform = ctx.platform_manager.get_platform(platform_id)
        command_prefix = platform.get_config("command_prefix", "/") if platform else "/"
        if isinstance(normalized_text, str) and normalized_text.startswith(
            command_prefix
        ):
            command_text = normalized_text[len(command_prefix) :]
            parts = command_text.split()
            command = parts[0] if parts else ""
            args = parts[1:] if len(parts) > 1 else []
            if command:
                # 命令别名映射
                command_aliases = {
                    "plugin": "plugins",
                }
                command = command_aliases.get(command, command)

                # 基础命令
                if command == "help":
                    await self._handle_help_command(event, ctx)
                    return True
                elif command == "ping":
                    await self._handle_ping_command(event, ctx)
                    return True
                elif command == "sid":
                    await self._handle_sid_command(event, ctx)
                    return True

                # 会话管理命令
                elif command == "new":
                    await self._handle_new_command(event, ctx)
                    return True
                elif command == "ls":
                    await self._handle_ls_command(event, ctx)
                    return True
                elif command == "del":
                    await self._handle_del_command(event, ctx)
                    return True
                elif command == "switch":
                    await self._handle_switch_command(event, ctx, args)
                    return True
                elif command == "rename":
                    await self._handle_rename_command(event, ctx, args)
                    return True
                elif command == "reset":
                    await self._handle_reset_command(event, ctx)
                    return True

                # LLM 配置命令
                elif command == "model":
                    await self._handle_model_command(event, ctx, args)
                    return True
                elif command == "provider":
                    await self._handle_provider_command(event, ctx, args)
                    return True
                elif command == "llm":
                    await self._handle_llm_command(event, ctx, args)
                    return True

                # 工具管理命令
                elif command == "tool":
                    await self._handle_tool_command(event, ctx, args)
                    return True

                # 权限管理命令
                elif command == "op":
                    await self._handle_op_command(event, ctx, args)
                    return True
                elif command == "deop":
                    await self._handle_deop_command(event, ctx, args)
                    return True
                elif command == "wl":
                    await self._handle_wl_command(event, ctx, args)
                    return True
                elif command == "dwl":
                    await self._handle_dwl_command(event, ctx, args)
                    return True

                # 插件管理命令
                elif command == "plugins":
                    await self._handle_plugins_command(event, ctx, args)
                    return True

                handled = await ctx.plugin_manager.execute_command(command, args, event)
                if handled:
                    return True
                logger.warning(f"未找到命令处理器: {command}")
        return False

    async def _process_notice(self, event: dict, ctx: PipelineContext) -> None:
        """处理通知事件"""
        notice_type = event.get("notice_type", "unknown")
        logger.info(f"收到通知事件: {notice_type}")

        if notice_type in [
            "group_increase",
            "group_decrease",
            "group_ban",
            "friend_add",
        ]:
            await ctx.plugin_manager.handle_message(event)

    async def _process_request(self, event: dict, ctx: PipelineContext) -> None:
        """处理请求事件"""
        request_type = event.get("request_type", "unknown")
        logger.info(f"收到请求事件: {request_type}")
        await ctx.plugin_manager.handle_message(event)

    async def _trigger_llm_response(self, event: dict, ctx: PipelineContext) -> None:
        """触发 LLM 回复"""
        try:
            from ...provider.context_manager import (
                LLMContextManager,
                ContextConfig,
                ContextCompressionStrategy,
            )
            from ...provider.entities import LLMResponse
            from ...agent.tools import ToolRegistry, ToolDefinition, ToolCategory
            from ..config import load_config

            message_text = self._format_message(event, simple=False)
            config = load_config()
            llm_providers = config.get("llm_providers", {})

            # 记录 LLM 提供商状态（不暴露敏感信息）
            provider_names = [p.get("name", "未命名") for p in llm_providers.values()]
            enabled_count = sum(1 for p in llm_providers.values() if p.get("enabled", False))
            logger.debug(f"LLM 提供商: 共 {len(llm_providers)} 个，已启用 {enabled_count} 个: {', '.join(provider_names)}")

            provider_config = None
            for provider in llm_providers.values():
                if provider.get("enabled", False):
                    provider_config = provider
                    break

            if not provider_config:
                logger.warning("未找到启用的 LLM 提供商")
                return

            provider_type = provider_config.get("type", "unknown")
            from ...provider.register import llm_provider_cls_map

            provider_meta = llm_provider_cls_map.get(provider_type)
            if not provider_meta:
                logger.warning(f"未找到 LLM 提供商类型: {provider_type}")
                return

            provider = provider_meta.cls_type(provider_config, {})

            user_id = event.get("user_id", "unknown")
            group_id = event.get("group_id", "private")
            session_id = f"{group_id}_{user_id}"

            # 获取用户信息用于构建系统提示词
            sender = event.get("sender", {}) if isinstance(event.get("sender"), dict) else {}
            nickname = sender.get("card") or sender.get("nickname") or str(user_id)
            user_disp = f"{nickname}({user_id})"

            # 获取群组信息
            group_name = event.get("group_name")
            message_type = event.get("message_type", "")
            bot_id = event.get("self_id", "unknown")

            # 初始化工具注册表并注册内置工具
            tool_registry = ToolRegistry()

            # 工具：获取用户信息
            def get_user_info() -> str:
                """获取当前用户信息"""
                return f"""用户信息详情:
- QQ号: {user_id}
- 昵称: {nickname}
- 显示名称: {user_disp}
- 消息类型: {'群聊' if message_type == 'group' else '私聊'}
{f"- 所在群组: {group_name} ({group_id})" if message_type == 'group' else ""}"""

            tool_registry.register_tool(ToolDefinition(
                name="get_user_info",
                category=ToolCategory.SYSTEM,
                description="获取当前对话用户的详细信息，包括QQ号、昵称、显示名称、消息类型等",
                function=get_user_info,
                enabled=True
            ))

            # 工具：获取群组信息
            def get_group_info() -> str:
                """获取当前群组信息"""
                if message_type != "group":
                    return "当前是私聊对话，无法获取群组信息"
                return f"""群组信息详情:
- 群组ID: {group_id}
- 群组名称: {group_name or '未知'}
- 你的机器人ID: {bot_id}
- 当前用户: {user_disp}"""

            tool_registry.register_tool(ToolDefinition(
                name="get_group_info",
                category=ToolCategory.SYSTEM,
                description="获取当前群组的详细信息，包括群组ID、群组名称等（仅在群聊时可用）",
                function=get_group_info,
                enabled=True
            ))

            # 工具：列出可用工具
            def list_tools() -> str:
                """列出所有可用的工具"""
                tools = tool_registry.get_all_tools()
                tool_list = "\n".join([
                    f"【{tool.name}】\n  描述: {tool.description}\n  类别: {tool.category.value}\n  状态: {'已启用' if tool.enabled else '已禁用'}"
                    for tool in tools
                ])
                return f"""当前可用工具列表（共 {len(tools)} 个）:\n\n{tool_list}\n\n提示: 你可以在回答中告诉用户这些工具的用途和功能。"""

            tool_registry.register_tool(ToolDefinition(
                name="list_tools",
                category=ToolCategory.SYSTEM,
                description="列出所有可用的工具及其详细描述，包括工具名称、功能、类别和状态",
                function=list_tools,
                enabled=True
            ))

            # 从 prompt_manager 获取工具提示词
            from ..prompt_manager import prompt_manager

            # 构建工具列表描述
            tools_desc = "=== 可用工具列表 ===\n\n"
            for tool in tool_registry.get_all_tools():
                tool_prompt = prompt_manager.get_tool_prompt(tool.name)
                tools_desc += f"【{tool.name}】\n- 功能: {tool_prompt}\n- 描述: {tool.description}\n\n"
            tools_desc += "=== 工具说明 ===\n这些工具可以帮助你更好地理解当前对话环境和用户需求。你可以在回答中主动提及这些工具，或根据用户需求调用相关工具获取信息。"

            # 从 prompt_manager 获取人格提示词
            personality_prompt = ""
            try:
                # 获取所有启用的人格提示词
                enabled_personalities = prompt_manager.get_enabled_personalities()
                if enabled_personalities:
                    # 使用第一个启用的人格
                    personality_prompt = enabled_personalities[0]["prompt"]
            except Exception as e:
                logger.warning(f"加载人格提示词失败: {e}，使用默认提示词")
                personality_prompt = ""

            # 从 prompt_manager 获取系统提示词
            system_prompt_base = prompt_manager.get_system_prompt()

            # 构建用户信息系统提示词
            user_info_prompt = f"""{system_prompt_base}

=== 当前对话环境 ===
- 用户: {user_disp}
- 消息类型: {'群聊' if message_type == 'group' else '私聊'}
{f"- 群组: {group_name}({group_id})" if message_type == 'group' and group_name else ""}
- 机器人ID: {bot_id}

=== 可访问的用户信息 ===
1. 用户QQ号: {user_id}
2. 用户昵称: {nickname}
3. 对话类型: {'群聊' if message_type == 'group' else '私聊'}
{f"4. 当前群组: {group_name} ({group_id})" if message_type == 'group' and group_name else ""}

{tools_desc}

{personality_prompt}

=== 你的角色和任务 ===
1. 你是一个友好、专业的 AI 助手
2. 你可以访问上述用户信息并在回答中引用
3. 你可以使用提供的工具来获取更多信息
4. 当用户询问可用工具时，请详细列出所有工具及其功能
5. 在群聊中，注意区分不同用户的消息，避免混淆
6. 回复时保持自然、友好的语气
7. 如果用户询问框架功能或工具，请详细解释每个工具的用途和使用场景

=== 重要提示 ===
- 用户信息是实时可用的，你可以直接在回答中引用
- 工具是用来增强你能力的辅助手段，根据需要选择使用
- 当用户询问"你有什么工具"或类似问题时，请详细列出所有工具及其功能描述
- 你可以告诉用户这些工具是如何帮助解决他们的问题的

请根据用户的问题，结合以上信息和工具，给出专业、友好的回答。
"""

            compression_strategy_name = provider_config.get("compression_strategy", "fifo").lower()
            # 确保策略名称有效
            valid_strategies = ["none", "fifo", "lru", "summary", "chat_summary"]
            if compression_strategy_name not in valid_strategies:
                compression_strategy_name = "fifo"

            context_config = ContextConfig(
                max_messages=provider_config.get("max_messages", 20),
                compression_strategy=ContextCompressionStrategy(compression_strategy_name),
            )
            context_manager = LLMContextManager(context_config)

            response: LLMResponse = await provider.text_chat(
                prompt=message_text,
                session_id=session_id,
                contexts=await context_manager.get_context(session_id),
                system_prompt=user_info_prompt,
            )

            response_text = response.completion_text or response.content
            if not response_text:
                logger.warning("LLM 返回空响应")
                return

            await self._send_message(event, ctx, response_text)

            await context_manager.add_message(session_id, "user", message_text)
            await context_manager.add_message(session_id, "assistant", response_text)

        except Exception as e:
            logger.error(f"触发 LLM 回复失败: {e}")

    async def _handle_help_command(self, event: dict, ctx: PipelineContext) -> None:
        """处理 help 命令"""
        platform_id = event.get("platform_id", "onebot")
        platform = ctx.platform_manager.get_platform(platform_id)
        command_prefix = platform.get_config("command_prefix", "/") if platform else "/"
        from ..server import get_full_version

        help_text = f"NekoBot {get_full_version()}\n"
        help_text += "内置指令:\n"
        help_text += f"  {command_prefix}help - 查看帮助\n"
        help_text += f"  {command_prefix}ping - 检查机器人状态\n"
        help_text += f"  {command_prefix}sid - 获取会话 ID\n"
        help_text += "\n[会话管理]\n"
        help_text += f"  {command_prefix}new - 创建新对话\n"
        help_text += f"  {command_prefix}ls - 查看对话列表\n"
        help_text += f"  {command_prefix}del - 删除当前对话\n"
        help_text += f"  {command_prefix}switch <序号> - 切换对话\n"
        help_text += f"  {command_prefix}rename <名称> - 重命名对话\n"
        help_text += f"  {command_prefix}reset - 重置 LLM 会话\n"
        help_text += "\n[LLM 配置]\n"
        help_text += f"  {command_prefix}model - 查看或切换模型\n"
        help_text += f"  {command_prefix}provider - 查看或切换 Provider\n"
        help_text += f"  {command_prefix}llm <on|off> - 开启/关闭 LLM\n"
        help_text += "\n[工具管理]\n"
        help_text += f"  {command_prefix}tool list - 列出所有工具\n"
        help_text += f"  {command_prefix}tool enable/disable <工具名> - 启用/禁用工具\n"
        help_text += "\n[权限管理]\n"
        help_text += f"  {command_prefix}op <用户ID> - 授权管理员\n"
        help_text += f"  {command_prefix}deop <用户ID> - 取消管理员\n"
        help_text += f"  {command_prefix}wl <会话ID> - 添加白名单\n"
        help_text += f"  {command_prefix}dwl <会话ID> - 删除白名单\n"
        help_text += "\n[插件管理]\n"
        help_text += f"  {command_prefix}plugins ls - 显示已加载的插件\n"
        help_text += f"  {command_prefix}plugins enable <插件名> - 启用插件\n"
        help_text += f"  {command_prefix}plugins disable <插件名> - 禁用插件\n"
        help_text += f"  {command_prefix}plugins reload <插件名> - 重载插件\n"
        help_text += f"  {command_prefix}plugins install <URL> - 从 URL 安装插件\n"
        help_text += f"  {command_prefix}plugins uninstall <插件名> - 卸载插件\n"
        help_text += f"  {command_prefix}plugins help <插件名> - 查看插件帮助"

        await self._send_message(event, ctx, help_text)

    async def _handle_ping_command(self, event: dict, ctx: PipelineContext) -> None:
        """处理 ping 命令"""
        await self._send_message(event, ctx, "Pong!")

    async def _handle_plugins_command(self, event: dict, ctx: PipelineContext, args: list) -> None:
        """处理 plugins 命令"""
        if not args:
            plugins_info = ctx.plugin_manager.get_all_plugins_info()
            text = "已加载的插件:\n"
            for name, info in plugins_info.items():
                status = "已启用" if info.get("enabled") else "已禁用"
                text += f"  {name} ({info.get('version', '未知版本')}) - {status}\n"
            text += "\n使用 /plugins help <插件名> 查看插件帮助和加载的指令。\n"
            text += "使用 /plugins enable/disable <插件名> 启用或禁用插件。"
            await self._send_message(event, ctx, text)
        else:
            action = args[0]
            # 支持 ls 作为 list 的别名
            if action == "list" or action == "ls":
                plugins_info = ctx.plugin_manager.get_all_plugins_info()
                text = "已加载的插件:\n"
                for name, info in plugins_info.items():
                    status = "已启用" if info.get("enabled") else "已禁用"
                    text += f"  {name} ({info.get('version', '未知版本')}) - {status}\n"
                await self._send_message(event, ctx, text)
            elif action == "enable":
                if len(args) < 2:
                    await self._send_message(
                        event, ctx, "用法: /plugins enable <插件名>"
                    )
                else:
                    success = await ctx.plugin_manager.enable_plugin(args[1])
                    if success:
                        await self._send_message(
                            event, ctx, f"插件 {args[1]} 已启用"
                        )
                    else:
                        await self._send_message(
                            event, ctx, f"插件 {args[1]} 启用失败"
                        )
            elif action == "disable":
                if len(args) < 2:
                    await self._send_message(
                        event, ctx, "用法: /plugins disable <插件名>"
                    )
                else:
                    success = await ctx.plugin_manager.disable_plugin(args[1])
                    if success:
                        await self._send_message(
                            event, ctx, f"插件 {args[1]} 已禁用"
                        )
                    else:
                        await self._send_message(
                            event, ctx, f"插件 {args[1]} 禁用失败"
                        )
            elif action == "reload":
                if len(args) < 2:
                    await self._send_message(
                        event, ctx, "用法: /plugins reload <插件名>"
                    )
                else:
                    success = await ctx.plugin_manager.reload_plugin(args[1])
                    if success:
                        await self._send_message(
                            event, ctx, f"插件 {args[1]} 已重载"
                        )
                    else:
                        await self._send_message(
                            event, ctx, f"插件 {args[1]} 重载失败"
                        )
            elif action == "install":
                if len(args) < 2:
                    await self._send_message(event, ctx, "用法: /plugins install <URL>")
                else:
                    try:
                        await ctx.plugin_manager.install_plugin_from_url(args[1])
                        await self._send_message(event, ctx, "插件安装成功")
                    except Exception as e:
                        await self._send_message(event, ctx, f"插件安装失败: {e}")
            elif action == "uninstall":
                if len(args) < 2:
                    await self._send_message(
                        event, ctx, "用法: /plugins uninstall <插件名>"
                    )
                else:
                    try:
                        await ctx.plugin_manager.delete_plugin(args[1])
                        await self._send_message(
                            event, ctx, f"插件 {args[1]} 已卸载"
                        )
                    except Exception as e:
                        await self._send_message(event, ctx, f"插件卸载失败: {e}")
            elif action == "help":
                if len(args) < 2:
                    await self._send_message(event, ctx, "用法: /plugins help <插件名>")
                else:
                    await self._handle_plugin_help_command(event, ctx, args[1])
            else:
                await self._send_message(
                    event,
                    ctx,
                    f"未知的子命令: {action}\n可用子命令: list/ls, enable, disable, reload, install, uninstall, help",
                )

    async def _handle_plugin_help_command(self, event: dict, ctx: PipelineContext, plugin_name: str) -> None:
        """处理插件帮助命令"""
        plugin = ctx.plugin_manager.plugins.get(plugin_name)
        if plugin is None:
            await self._send_message(event, ctx, "未找到此插件。")
            return

        help_msg = f"插件 {plugin_name} 帮助信息：\n\n"
        help_msg += f"作者: {getattr(plugin, 'author', '未知')}\n"
        help_msg += f"版本: {getattr(plugin, 'version', '未知')}\n"
        help_msg += f"描述: {getattr(plugin, 'desc', '无描述')}\n"

        command_handlers = []
        command_names = []
        for cmd_name, cmd_func in plugin.commands.items():
            cmd_info = getattr(cmd_func, "_nekobot_command", None)
            command_handlers.append(cmd_func)
            command_names.append(cmd_name)

        if len(command_handlers) > 0:
            help_msg += "\n指令列表：\n"
            for i in range(len(command_handlers)):
                line = f"  {command_names[i]}"
                cmd_info = getattr(command_handlers[i], "_nekobot_command", None)
                if cmd_info and cmd_info.description:
                    line += f": {cmd_info.description}"
                help_msg += line + "\n"
            help_msg += "\nTip: 指令的触发需要添加唤醒前缀，默认为 /。"

        help_msg += "\n更多帮助信息请查看插件仓库 README。"
        await self._send_message(event, ctx, help_msg)

    async def _handle_sid_command(self, event: dict, ctx: PipelineContext) -> None:
        """处理 sid 命令 - 获取会话 ID"""
        user_id = event.get("user_id", "unknown")
        group_id = event.get("group_id", "private")
        message_type = event.get("message_type", "unknown")
        platform_id = event.get("platform_id", "unknown")

        sid_text = "会话 ID 信息:\n"
        sid_text += f"  平台 ID: {platform_id}\n"
        sid_text += f"  用户 ID: {user_id}\n"
        sid_text += f"  消息类型: {message_type}\n"
        if message_type == "group":
            sid_text += f"  群组 ID: {group_id}\n"
        sid_text += f"  统一会话 ID: {group_id}_{user_id}"

        await self._send_message(event, ctx, sid_text)

    async def _handle_op_command(self, event: dict, ctx: PipelineContext, args: list) -> None:
        """处理 op 命令 - 授权管理员"""
        if not args:
            await self._send_message(
                event, ctx, "用法: /op <用户ID> 授权管理员；可通过 /sid 获取 ID。"
            )
            return

        admin_id = args[0]
        from ..config import load_config

        config = load_config()
        admins = config.get("admins_id", [])
        if admin_id not in admins:
            admins.append(str(admin_id))
            config["admins_id"] = admins
            config.save_config()
            await self._send_message(event, ctx, f"用户 {admin_id} 已授权为管理员。")
        else:
            await self._send_message(event, ctx, f"用户 {admin_id} 已经是管理员。")

    async def _handle_deop_command(self, event: dict, ctx: PipelineContext, args: list) -> None:
        """处理 deop 命令 - 取消管理员授权"""
        if not args:
            await self._send_message(
                event, ctx, "用法: /deop <用户ID> 取消管理员；可通过 /sid 获取 ID。"
            )
            return

        admin_id = args[0]
        from ..config import load_config

        config = load_config()
        admins = config.get("admins_id", [])
        if admin_id in admins:
            admins.remove(str(admin_id))
            config["admins_id"] = admins
            config.save_config()
            await self._send_message(
                event, ctx, f"用户 {admin_id} 已取消管理员授权。"
            )
        else:
            await self._send_message(
                event, ctx, f"用户 {admin_id} 不在管理员名单内。"
            )

    async def _handle_wl_command(self, event: dict, ctx: PipelineContext, args: list) -> None:
        """处理 wl 命令 - 添加白名单"""
        if not args:
            await self._send_message(
                event, ctx, "用法: /wl <会话ID> 添加白名单；可通过 /sid 获取 ID。"
            )
            return

        sid = args[0]
        from ..config import load_config

        config = load_config()
        whitelist = config.get("id_whitelist", [])
        if sid not in whitelist:
            whitelist.append(str(sid))
            config["id_whitelist"] = whitelist
            config.save_config()
            await self._send_message(event, ctx, f"会话 {sid} 已添加到白名单。")
        else:
            await self._send_message(event, ctx, f"会话 {sid} 已经在白名单内。")

    async def _handle_dwl_command(self, event: dict, ctx: PipelineContext, args: list) -> None:
        """处理 dwl 命令 - 删除白名单"""
        if not args:
            await self._send_message(
                event, ctx, "用法: /dwl <会话ID> 删除白名单；可通过 /sid 获取 ID。"
            )
            return

        sid = args[0]
        from ..config import load_config

        config = load_config()
        whitelist = config.get("id_whitelist", [])
        if sid in whitelist:
            whitelist.remove(str(sid))
            config["id_whitelist"] = whitelist
            config.save_config()
            await self._send_message(event, ctx, f"会话 {sid} 已从白名单删除。")
        else:
            await self._send_message(event, ctx, f"会话 {sid} 不在白名单内。")

    # ========== 会话管理命令 ==========

    def _get_unified_session_id(self, event: dict) -> str:
        """获取统一会话 ID（参考 AstrBot 的 unified_msg_origin）"""
        platform_id = event.get("platform_id", "onebot")
        message_type = event.get("message_type", "private")  # private/group
        user_id = str(event.get("user_id", ""))
        group_id = str(event.get("group_id", ""))

        if message_type == "group":
            # 群聊：平台:群:群号
            return f"{platform_id}:group:{group_id}"
        else:
            # 私聊：平台:私:用户ID
            return f"{platform_id}:private:{user_id}"

    async def _handle_new_command(self, event: dict, ctx: PipelineContext) -> None:
        """处理 new 命令 - 创建新对话"""
        if not ctx.conv_manager:
            await self._send_message(event, ctx, "会话管理器未初始化")
            return

        session_id = self._get_unified_session_id(event)
        conv = await ctx.conv_manager.new_conversation(
            session_id=session_id,
            title="新对话"
        )

        await self._send_message(
            event, ctx,
            f"✓ 已创建新对话\n对话ID: {conv.conversation_id}\n会话ID: {session_id}"
        )

    async def _handle_ls_command(self, event: dict, ctx: PipelineContext) -> None:
        """处理 ls 命令 - 查看对话列表"""
        if not ctx.conv_manager:
            await self._send_message(event, ctx, "会话管理器未初始化")
            return

        session_id = self._get_unified_session_id(event)
        conversations = ctx.conv_manager.list_conversations(session_id)

        if not conversations:
            await self._send_message(event, ctx, "暂无对话记录\n提示: 使用 /new 创建新对话")
            return

        # 获取当前对话
        current_conv = ctx.conv_manager.get_current_conversation(session_id)

        text = f"📋 对话列表（共 {len(conversations)} 个）:\n\n"
        for i, conv in enumerate(conversations, 1):
            is_current = "👉 " if conv == current_conv else "   "
            msg_count = len(conv.messages)
            last_msg = conv.messages[-1].get("content", "")[:25] if conv.messages else "无"
            text += f"{is_current}{i}. {conv.title}\n"
            text += f"      ID: {conv.conversation_id}\n"
            text += f"      消息: {msg_count} | 最后: {last_msg}...\n"

        await self._send_message(event, ctx, text)

    async def _handle_del_command(self, event: dict, ctx: PipelineContext) -> None:
        """处理 del 命令 - 删除当前对话"""
        if not ctx.conv_manager:
            await self._send_message(event, ctx, "会话管理器未初始化")
            return

        session_id = self._get_unified_session_id(event)
        current_conv = ctx.conv_manager.get_current_conversation(session_id)

        if not current_conv:
            await self._send_message(event, ctx, "当前没有活动对话")
            return

        conv_id = current_conv.conversation_id
        success = await ctx.conv_manager.delete_conversation(conv_id)

        if success:
            await self._send_message(event, ctx, f"✓ 已删除对话: {current_conv.title}")
        else:
            await self._send_message(event, ctx, "删除对话失败")

    async def _handle_switch_command(self, event: dict, ctx: PipelineContext, args: list) -> None:
        """处理 switch 命令 - 切换对话"""
        if not ctx.conv_manager:
            await self._send_message(event, ctx, "会话管理器未初始化")
            return

        if not args:
            await self._send_message(event, ctx, "用法: /switch <序号>\n请先使用 /ls 查看对话列表")
            return

        try:
            index = int(args[0]) - 1
            session_id = self._get_unified_session_id(event)
            conversations = ctx.conv_manager.list_conversations(session_id)

            if 0 <= index < len(conversations):
                target_conv = conversations[index]
                success = await ctx.conv_manager.switch_conversation(session_id, target_conv.conversation_id)

                if success:
                    await self._send_message(
                        event, ctx,
                        f"✓ 已切换到对话: {target_conv.title}\n对话ID: {target_conv.conversation_id}"
                    )
                else:
                    await self._send_message(event, ctx, "切换失败")
            else:
                await self._send_message(event, ctx, f"无效的序号，请使用 1-{len(conversations)}")
        except ValueError:
            await self._send_message(event, ctx, "请输入有效的序号数字")

    async def _handle_rename_command(self, event: dict, ctx: PipelineContext, args: list) -> None:
        """处理 rename 命令 - 重命名对话"""
        if not ctx.conv_manager:
            await self._send_message(event, ctx, "会话管理器未初始化")
            return

        if not args:
            await self._send_message(event, ctx, "用法: /rename <新名称>")
            return

        new_name = " ".join(args)
        session_id = self._get_unified_session_id(event)
        current_conv = ctx.conv_manager.get_current_conversation(session_id)

        if not current_conv:
            await self._send_message(event, ctx, "当前没有活动对话")
            return

        # 更新标题
        current_conv.title = new_name
        current_conv.updated_at = current_conv.updated_at  # 触发更新时间

        # 保存
        await ctx.conv_manager._save_conversations()

        await self._send_message(event, ctx, f"✓ 对话已重命名为: {new_name}")

    async def _handle_reset_command(self, event: dict, ctx: PipelineContext) -> None:
        """处理 reset 命令 - 重置当前对话上下文"""
        if not ctx.conv_manager:
            await self._send_message(event, ctx, "会话管理器未初始化")
            return

        session_id = self._get_unified_session_id(event)
        current_conv = ctx.conv_manager.get_current_conversation(session_id)

        if not current_conv:
            await self._send_message(event, ctx, "当前没有活动对话")
            return

        # 清空消息历史
        current_conv.messages.clear()
        current_conv.updated_at = current_conv.updated_at

        # 保存
        await ctx.conv_manager._save_conversations()

        await self._send_message(
            event, ctx,
            f"✓ 已重置对话上下文\n对话: {current_conv.title}\n提示: 新消息将不会包含之前的历史记录"
        )

    # ========== LLM 配置命令 ==========

    async def _handle_model_command(self, event: dict, ctx: PipelineContext, args: list) -> None:
        """处理 model 命令 - 查看或切换模型"""
        from ..config import load_config

        config = load_config()
        llm_providers = config.get("llm_providers", {})

        if not args:
            # 列出所有可用模型
            text = "可用模型:\n"
            for provider_id, provider in llm_providers.items():
                if provider.get("enabled", False):
                    model = provider.get("model", "未设置")
                    name = provider.get("name", provider_id)
                    text += f"  [{provider_id}] {name}: {model}\n"
            await self._send_message(event, ctx, text)
        else:
            # 切换模型（这里简化处理，实际需要更复杂的逻辑）
            await self._send_message(
                event, ctx,
                "模型切换功能暂未实现\n请通过 WebUI 或配置文件修改"
            )

    async def _handle_provider_command(self, event: dict, ctx: PipelineContext, args: list) -> None:
        """处理 provider 命令 - 查看或切换 LLM Provider"""
        from ..config import load_config

        config = load_config()
        llm_providers = config.get("llm_providers", {})

        if not args:
            # 列出所有 Provider
            text = "可用 LLM Provider:\n"
            for provider_id, provider in llm_providers.items():
                status = "✓" if provider.get("enabled", False) else "✗"
                name = provider.get("name", provider_id)
                text += f"  {status} [{provider_id}] {name}\n"
            await self._send_message(event, ctx, text)
        else:
            await self._send_message(
                event, ctx,
                "Provider 切换功能暂未实现\n请通过 WebUI 或配置文件修改"
            )

    async def _handle_llm_command(self, event: dict, ctx: PipelineContext, args: list) -> None:
        """处理 llm 命令 - 开启/关闭 LLM"""
        if not args:
            await self._send_message(event, ctx, "用法: /llm <on|off>")
            return

        action = args[0].lower()
        if action == "on":
            await self._send_message(event, ctx, "LLM 已开启")
        elif action == "off":
            await self._send_message(event, ctx, "LLM 已关闭")
        else:
            await self._send_message(event, ctx, "用法: /llm <on|off>")

    # ========== 工具管理命令 ==========

    async def _handle_tool_command(self, event: dict, ctx: PipelineContext, args: list) -> None:
        """处理 tool 命令 - 函数工具管理"""
        if not args:
            await self._send_message(
                event, ctx,
                "用法:\n"
                "  /tool list - 列出所有工具\n"
                "  /tool enable <工具名> - 启用工具\n"
                "  /tool disable <工具名> - 禁用工具"
            )
            return

        action = args[0].lower()

        if action == "list":
            from ...agent.tools import ToolRegistry
            registry = ToolRegistry()
            tools = registry.get_all_tools()

            text = f"可用工具（共 {len(tools)} 个）:\n"
            for tool in tools:
                status = "✓" if getattr(tool, "enabled", True) else "✗"
                name = getattr(tool, "name", tool.__class__.__name__)
                desc = getattr(tool, "description", "无描述")
                text += f"  {status} {name}: {desc}\n"
            await self._send_message(event, ctx, text)
        elif action == "enable":
            if len(args) < 2:
                await self._send_message(event, ctx, "用法: /tool enable <工具名>")
            else:
                await self._send_message(event, ctx, f"工具 {args[1]} 启用功能暂未实现")
        elif action == "disable":
            if len(args) < 2:
                await self._send_message(event, ctx, "用法: /tool disable <工具名>")
            else:
                await self._send_message(event, ctx, f"工具 {args[1]} 禁用功能暂未实现")
        else:
            await self._send_message(
                event, ctx,
                "未知操作，可用操作: list, enable, disable"
            )

    def _check_if_at_me(self, event: dict, ctx: PipelineContext) -> bool:
        """检查消息中是否艾特了机器人或使用了唤醒前缀
        
        参考 AstrBot 的实现方式，支持：
        1. 检查消息段中的 at 类型，是否艾特了机器人自己
        2. 兼容不同格式的 self_id 和 qq 值（数字、字符串）
        3. 支持艾特全体成员触发
        4. 支持引用机器人的消息触发
        5. 支持唤醒前缀（wake_prefix）触发
        6. 私聊消息根据配置决定是否需要唤醒前缀
        """
        from ..config import load_config

        message = event.get("message", "")
        self_id = event.get("self_id")
        message_type = event.get("message_type", "")

        # 加载配置
        config = load_config()
        wake_prefixes = config.get("wake_prefix", ["/", "."])
        private_needs_wake_prefix = config.get("private_message_needs_wake_prefix", False)
        ignore_at_all = config.get("ignore_at_all", False)

        logger.debug(f"检查艾特: message_type={message_type}, self_id={self_id}, message={message}")

        if not message or not self_id:
            return False

        # 将 self_id 转换为字符串集合，方便比较
        self_id_set = {
            str(self_id),
            int(self_id) if str(self_id).isdigit() else None
        }.difference({None})

        logger.debug(f"self_id 集合: {self_id_set}")

        if isinstance(message, list):
            first_seg_is_at = False
            at_qq_first = None

            # 首先检查是否有艾特或引用
            for i, msg_seg in enumerate(message):
                seg_type = msg_seg.get("type", "")
                seg_data = msg_seg.get("data", {})
                logger.debug(f"消息段: type={seg_type}, data={seg_data}")

                # 检查 at 消息段
                if seg_type == "at":
                    at_qq = seg_data.get("qq", "")

                    # 记录第一个 at 消息段的 QQ 号
                    if i == 0:
                        first_seg_is_at = True
                        at_qq_first = at_qq

                    # 检查是否艾特全体成员
                    if str(at_qq) == "all":
                        if ignore_at_all:
                            logger.debug("忽略艾特全体成员")
                            continue
                        logger.debug("检测到艾特全体成员")
                        return True

                    # 尝试多种格式比较
                    at_qq_formats = {
                        str(at_qq),
                        int(at_qq) if str(at_qq).isdigit() else None
                    }.difference({None})

                    # 检查是否有交集
                    if self_id_set & at_qq_formats:
                        logger.debug(f"检测到艾特机器人: at_qq={at_qq}, self_id={self_id}")
                        return True

                # 检查 reply 消息段（引用消息）
                elif seg_type == "reply":
                    reply_sender_id = seg_data.get("sender_id", "")
                    if reply_sender_id:
                        reply_sender_formats = {
                            str(reply_sender_id),
                            int(reply_sender_id) if str(reply_sender_id).isdigit() else None
                        }.difference({None})

                        if self_id_set & reply_sender_formats:
                            logger.debug(f"检测到引用机器人的消息: sender_id={reply_sender_id}")
                            return True

            # 检查唤醒前缀（参考 AstrBot 的逻辑）
            for msg_seg in message:
                if msg_seg.get("type") == "text":
                    text = msg_seg.get("data", {}).get("text", "")
                    text_stripped = text.strip()

                    # 检查是否以唤醒前缀开头
                    for prefix in wake_prefixes:
                        if text_stripped.startswith(prefix):
                            # 如果是群聊且第一个消息段是艾特，需要检查是否艾特机器人
                            if message_type == "group" and first_seg_is_at:
                                if at_qq_first is not None and str(at_qq_first) != "all":
                                    # 第一个艾特不是机器人也不是全体成员，不唤醒
                                    logger.debug("群聊中第一个艾特不是机器人或全体成员，不唤醒")
                                    return False
                            logger.debug(f"检测到唤醒前缀: {prefix}")
                            return True

                    break

            # 检查私聊消息
            if message_type == "private" and not private_needs_wake_prefix:
                logger.debug("私聊消息自动唤醒")
                return True

        elif isinstance(message, str):
            # 纯字符串消息（兼容性处理）
            text_stripped = message.strip()

            # 检查是否以唤醒前缀开头
            for prefix in wake_prefixes:
                if text_stripped.startswith(prefix):
                    logger.debug(f"检测到唤醒前缀: {prefix}")
                    return True

            # 检查私聊消息
            if message_type == "private" and not private_needs_wake_prefix:
                logger.debug("私聊消息自动唤醒")
                return True

        return False

    def _check_if_command(self, event: dict, ctx: PipelineContext) -> bool:
        """检查是否是命令消息"""
        message = event.get("message", "")

        if isinstance(message, list):
            for msg_seg in message:
                if msg_seg.get("type") == "text":
                    text = msg_seg.get("data", {}).get("text", "")
                    platform_id = event.get("platform_id", "onebot")
                    platform = ctx.platform_manager.get_platform(platform_id)
                    command_prefix = (
                        platform.get_config("command_prefix", "/") if platform else "/"
                    )
                    if text.startswith(command_prefix):
                        return True
        elif isinstance(message, str) and message.startswith("/"):
            return True

        return False

    def _format_message(self, event: dict, simple: bool = True) -> str:
        """格式化消息内容"""
        import re

        if not simple:
            # 始终使用解析后的消息而不是 raw_message，避免 CQ 码传入 LLM
            msg = event.get("message")
            if isinstance(msg, list):
                parts = []
                for seg in msg:
                    if not isinstance(seg, dict):
                        continue
                    t = seg.get("type")
                    data = seg.get("data", {}) if isinstance(seg.get("data"), dict) else {}
                    if t == "text":
                        parts.append(data.get("text", ""))
                return "".join(parts)

            # 如果是字符串，过滤 CQ 码
            raw = event.get("raw_message")
            if isinstance(raw, str):
                raw = re.sub(r"\[CQ:[^\]]+\]", "", raw)
                return raw.strip()

        msg = event.get("message")

        if isinstance(msg, list):
            parts = []
            for seg in msg:
                if not isinstance(seg, dict):
                    continue
                t = seg.get("type")
                data = seg.get("data", {}) if isinstance(seg.get("data"), dict) else {}

                if t == "text":
                    parts.append(data.get("text", ""))
                elif t == "at":
                    parts.append(f"[@{data.get('qq', 'User')}]")
                elif t == "image":
                    parts.append("[图片]")
                elif t == "face":
                    parts.append("[表情]")
                elif t == "record":
                    parts.append("[语音]")
                elif t == "video":
                    parts.append("[视频]")
                elif t == "share":
                    parts.append(f"[分享: {data.get('title', '链接')}]")
                elif t == "xml":
                    parts.append("[XML卡片]")
                elif t == "json":
                    parts.append("[JSON卡片]")
                elif t == "reply":
                    parts.append(f"[回复: {data.get('id', 'Unknown')}]")
                else:
                    parts.append(f"[{t}]")
            return "".join(parts)

        raw = event.get("raw_message")
        if isinstance(raw, str):
            if simple:
                raw = re.sub(r"\[CQ:image,[^\]]+\]", "[图片]", raw)
                raw = re.sub(r"\[CQ:face,[^\]]+\]", "[表情]", raw)
                raw = re.sub(r"\[CQ:record,[^\]]+\]", "[语音]", raw)
                raw = re.sub(r"\[CQ:video,[^\]]+\]", "[视频]", raw)
                raw = re.sub(r"\[CQ:at,qq=(\d+)[^\]]*\]", r"[@\1]", raw)
                raw = re.sub(r"\[CQ:([^,]+),[^\]]+\]", r"[\1]", raw)
            return raw

        return ""

    async def _send_message(self, event: dict, ctx: PipelineContext, text: str) -> None:
        """发送消息"""
        platform_id = event.get("platform_id", "onebot")
        message_type = event.get("message_type", "")
        target_id = None

        if message_type == "private":
            target_id = event.get("user_id")
        elif message_type == "group":
            target_id = event.get("group_id")

        if target_id:
            chat_type = "群聊" if message_type == "group" else "私聊"
            group_id = event.get("group_id", "N/A")
            group_name = event.get("group_name")
            group_disp = (
                f"{group_name}({group_id})"
                if (message_type == "group" and group_id)
                else ""
            )
            bot_id = event.get("self_id")
            bot_disp = f"猫猫({bot_id})" if bot_id else "猫猫"

            def _trim_text(t: str, n: int = 120) -> str:
                s = " ".join(t.splitlines())
                return s if len(s) <= n else s[: n - 3] + "..."
            log_text = _trim_text(text)
            if message_type == "group":
                logger.info(
                    f"猫猫 | 发送 -> {chat_type} [{group_disp}] [{bot_disp}] {log_text}"
                )
            else:
                logger.info(f"猫猫 | 发送 -> {chat_type} [{bot_disp}] {log_text}")
            await ctx.platform_manager.send_message(
                platform_id, message_type, target_id, text
            )
