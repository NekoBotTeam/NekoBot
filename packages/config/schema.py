"""NekoBot 配置 Schema 定义

参考 AstrBot 的 CONFIG_METADATA_3 实现
"""

CONFIG_SCHEMA = {
    "server_group": {
        "name": "服务器设置",
        "metadata": {
            "server": {
                "type": "object",
                "description": "服务器配置",
                "items": {
                    "host": {
                        "type": "string",
                        "default": "0.0.0.0",
                        "hint": "服务器监听地址",
                    },
                    "port": {
                        "type": "int",
                        "default": 6285,
                        "validation": {"min": 1, "max": 65535},
                        "hint": "服务器端口（1-65535）",
                    },
                },
            }
        },
    },
    "jwt_group": {
        "name": "JWT 认证",
        "metadata": {
            "jwt": {
                "type": "object",
                "description": "JWT 认证配置",
                "items": {
                    "secret_key": {
                        "type": "string",
                        "default": "",
                        "hint": "JWT 密钥（自动生成）",
                    },
                    "algorithm": {
                        "type": "string",
                        "default": "HS256",
                        "options": ["HS256", "HS384", "HS512"],
                    },
                    "access_token_expire_minutes": {
                        "type": "int",
                        "default": 30,
                        "validation": {"min": 1},
                        "hint": "访问令牌过期时间（分钟）",
                    },
                },
            }
        },
    },
    "cors_group": {
        "name": "CORS 设置",
        "metadata": {
            "cors": {
                "type": "object",
                "description": "CORS 跨域配置",
                "items": {
                    "allow_origin": {
                        "type": "string",
                        "default": "*",
                        "hint": "允许的来源",
                    },
                    "allow_headers": {
                        "type": "list",
                        "default": ["Content-Type", "Authorization"],
                        "hint": "允许的请求头",
                    },
                    "allow_methods": {
                        "type": "list",
                        "default": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                        "hint": "允许的 HTTP 方法",
                    },
                },
            }
        },
    },
    "llm_group": {
        "name": "LLM 设置",
        "metadata": {
            "llm_reply_mode": {
                "type": "string",
                "default": "active",
                "options": ["active", "passive", "at", "command"],
                "hint": "LLM 回复模式",
            }
        },
    },
    "pipeline_group": {
        "name": "流水线设置",
        "metadata": {
            "pipeline_stages": {
                "type": "object",
                "description": "流水线阶段开关",
                "items": {
                    "rag_enabled": {
                        "type": "bool",
                        "default": False,
                        "hint": "启用 RAG 增强阶段",
                    },
                    "session_summary_enabled": {
                        "type": "bool",
                        "default": False,
                        "hint": "启用会话摘要阶段",
                    },
                },
            },
            "wake_prefix": {
                "type": "object",
                "description": "唤醒前缀配置",
                "items": {
                    "prefixes": {
                        "type": "list",
                        "default": ["/", "."],
                        "hint": "唤醒前缀列表",
                    },
                    "private_message_needs_wake_prefix": {
                        "type": "bool",
                        "default": False,
                        "hint": "私聊是否需要唤醒前缀",
                    },
                },
            },
        },
    },
}


def get_default_config() -> dict:
    """从 Schema 生成默认配置"""
    import copy

    config = {}
    for group_name, group_data in CONFIG_SCHEMA.items():
        for section_name, section_data in group_data["metadata"].items():
            if section_data["type"] == "object":
                config[section_name] = {
                    field_name: copy.deepcopy(field_data["default"])
                    for field_name, field_data in section_data["items"].items()
                }
            else:
                config[section_name] = section_data["default"]

    # 额外的默认值（不在 Schema 中）
    config["command_prefix"] = "/"
    config["webui_enabled"] = True
    config["webui_api_enabled"] = True
    config["demo"] = False
    config["github_proxy"] = {"url": None, "enabled": False}
    config["webui_version"] = None
    config["private_message_needs_wake_prefix"] = False
    config["ignore_at_all"] = False

    return config
