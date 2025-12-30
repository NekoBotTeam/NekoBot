"""认证API路由

提供用户登录、登出、修改密码等认证功能
"""

import re
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger
from quart import request, g

from .route import Route, Response, RouteContext
from ..auth.user import authenticate_user, get_user, update_user_password
from ..auth.jwt import create_access_token
from ..auth.hash import verify_password
from ..core.database import db_manager


class AuthRoute(Route):
    """认证路由"""

    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.routes = [
            ("/api/auth/login", "POST", self.auth_login),
            ("/api/auth/logout", "POST", self.auth_logout),
            ("/api/auth/change-password", "POST", self.auth_change_password),
        ]

    def _add_operation_log(
        self,
        operation: str,
        username: str,
        ip_address: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """添加操作日志"""
        db_manager.add_operation_log(operation, username, ip_address, details)

    def _validate_username(self, username: str) -> tuple[bool, str]:
        """验证用户名格式"""
        if not username:
            return False, "用户名不能为空"
        if len(username) < 3:
            return False, "用户名长度不能少于3个字符"
        if len(username) > 20:
            return False, "用户名长度不能超过20个字符"
        if not re.match(r"^[a-zA-Z0-9_]+$", username):
            return False, "用户名只能包含字母、数字和下划线"
        return True, ""

    def _validate_password(self, password: str) -> tuple[bool, str]:
        """验证密码强度"""
        if not password:
            return False, "密码不能为空"
        if len(password) < 8:
            return False, "密码长度不能少于8个字符"
        if len(password) > 72:
            return False, "密码长度不能超过72个字符"
        # 检查是否包含至少一个大写字母
        if not re.search(r"[A-Z]", password):
            return False, "密码必须包含至少一个大写字母"
        # 检查是否包含至少一个小写字母
        if not re.search(r"[a-z]", password):
            return False, "密码必须包含至少一个小写字母"
        # 检查是否包含至少一个数字
        if not re.search(r"\d", password):
            return False, "密码必须包含至少一个数字"
        # 检查是否包含至少一个特殊字符
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            return False, "密码必须包含至少一个特殊字符"
        return True, ""

    async def auth_login(self) -> Dict[str, Any]:
        """用户登录

        请求参数:
            username: 用户名
            password: 密码

        返回:
            包含访问令牌的响应
        """
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("缺少请求数据").to_dict()

            username = data.get("username")
            password = data.get("password")

            # 验证必填字段
            is_valid, error_msg = await self.validate_required_fields(
                data, ["username", "password"]
            )
            if not is_valid:
                return Response().error(error_msg).to_dict()

            # 验证用户名格式
            is_valid, error_msg = self._validate_username(username)
            if not is_valid:
                return Response().error(error_msg).to_dict()

            # 验证密码不为空
            if not password:
                return Response().error("密码不能为空").to_dict()

            # 获取客户端IP地址
            ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
            if ip_address and "," in ip_address:
                ip_address = ip_address.split(",")[0].strip()

            # 检查登录尝试次数
            attempts = db_manager.get_login_attempts(username, ip_address)
            if attempts:
                if attempts.get("locked", False):
                    # 检查锁定是否已过期（30分钟）
                    if attempts.get("lock_time"):
                        lock_time = datetime.fromisoformat(attempts["lock_time"])
                        if (datetime.utcnow() - lock_time).total_seconds() > 1800:
                            # 锁定已过期，重置
                            db_manager.reset_login_attempts(username, ip_address)
                        else:
                            return Response().error("账户已被锁定，请30分钟后再试").to_dict()

                # 检查失败次数（5次失败后锁定）
                if attempts.get("failed_attempts", 0) >= 5:
                    db_manager.lock_login_attempts(username, ip_address)
                    return Response().error("登录失败次数过多，账户已被锁定30分钟").to_dict()
            else:
                # 创建登录尝试记录
                db_manager.create_login_attempts(username, ip_address)

            # 验证用户
            user = authenticate_user(username, password)
            if not user:
                # 增加失败次数
                db_manager.increment_login_attempts(username, ip_address)
                return Response().error("用户名或密码错误").to_dict()

            # 记录成功登录
            db_manager.reset_login_attempts(username, ip_address)

            # 创建访问令牌
            access_token = create_access_token(data={"sub": user.username})

            # 记录操作日志
            self._add_operation_log(
                operation="login",
                username=user.username,
                ip_address=ip_address,
                details={"first_login": user.first_login},
            )

            return Response().ok(
                data={
                    "access_token": access_token,
                    "token_type": "bearer",
                    "username": user.username,
                    "first_login": user.first_login,
                },
                message="登录成功",
            ).to_dict()

        except Exception as e:
            logger.error(f"登录失败: {e}", exc_info=True)
            return Response().error(f"登录失败: {str(e)}").to_dict()

    async def auth_logout(self) -> Dict[str, Any]:
        """用户登出

        将当前令牌加入黑名单
        """
        try:
            # 获取Authorization头
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return Response().error("未提供有效的认证令牌").to_dict()

            token = auth_header.split(" ")[1]

            # 验证令牌
            try:
                from ..auth.jwt import SECRET_KEY, ALGORITHM
                from jose import jwt

                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                username = payload.get("sub")
                if not username:
                    return Response().error("无效的认证令牌").to_dict()
            except Exception as e:
                logger.error(f"令牌验证失败: {e}")
                return Response().error("无效的认证令牌").to_dict()

            # 将令牌加入黑名单
            db_manager.add_token_to_blacklist(token)

            # 获取客户端IP地址
            ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
            if ip_address and "," in ip_address:
                ip_address = ip_address.split(",")[0].strip()

            # 记录操作日志
            self._add_operation_log(
                operation="logout",
                username=username,
                ip_address=ip_address,
            )

            return Response().ok(message="登出成功").to_dict()

        except Exception as e:
            logger.error(f"登出失败: {e}", exc_info=True)
            return Response().error(f"登出失败: {str(e)}").to_dict()

    async def auth_change_password(self) -> Dict[str, Any]:
        """修改密码

        请求参数:
            old_password: 旧密码
            new_password: 新密码

        返回:
            操作结果
        """
        try:
            # 检查是否为Demo模式
            if self.context.config.get("demo", False):
                return Response().error("Demo模式下不允许修改密码").to_dict()

            data = await self.get_request_data()
            if not data:
                return Response().error("缺少请求数据").to_dict()

            old_password = data.get("old_password")
            new_password = data.get("new_password")

            # 验证必填字段
            is_valid, error_msg = await self.validate_required_fields(
                data, ["old_password", "new_password"]
            )
            if not is_valid:
                return Response().error(error_msg).to_dict()

            # 获取当前用户
            user = get_user(g.user.username)
            if not user:
                return Response().error("用户不存在").to_dict()

            # 验证旧密码
            if not verify_password(old_password, user.hashed_password):
                return Response().error("旧密码错误").to_dict()

            # 验证新密码强度
            is_valid, error_msg = self._validate_password(new_password)
            if not is_valid:
                return Response().error(error_msg).to_dict()

            # 检查新密码是否与旧密码相同
            if old_password == new_password:
                return Response().error("新密码不能与旧密码相同").to_dict()

            # 更新密码
            if not update_user_password(user.username, new_password):
                return Response().error("密码修改失败").to_dict()

            # 获取客户端IP地址
            ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
            if ip_address and "," in ip_address:
                ip_address = ip_address.split(",")[0].strip()

            # 记录操作日志
            self._add_operation_log(
                operation="change_password",
                username=user.username,
                ip_address=ip_address,
            )

            return Response().ok(message="密码修改成功").to_dict()

        except Exception as e:
            logger.error(f"修改密码失败: {e}", exc_info=True)
            return Response().error(f"修改密码失败: {str(e)}").to_dict()
