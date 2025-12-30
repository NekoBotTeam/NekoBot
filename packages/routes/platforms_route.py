"""平台管理API路由

提供平台的增删改查功能
"""

from typing import Dict, Any, Optional
from loguru import logger
from quart import request, g

from .route import Route, Response, RouteContext
from ..core.database import db_manager


class PlatformsRoute(Route):
    """平台管理路由"""

    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.routes = [
            ("/api/platforms/list", "GET", self.list_platforms),
            ("/api/platforms/add", "POST", self.add_platform),
            ("/api/platforms/update", "POST", self.update_platform),
            ("/api/platforms/delete", "POST", self.delete_platform),
        ]

    def _add_platform_history(
        self,
        platform_id: str,
        operation: str,
        old_data: Optional[Dict[str, Any]] = None,
        new_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """添加平台变更历史"""
        db_manager.add_platform_history(
            platform_id=platform_id,
            operation=operation,
            old_data=old_data,
            new_data=new_data,
            operator=getattr(g.user, "username", "system"),
        )

    def _get_client_ip(self) -> str:
        """获取客户端IP地址"""
        ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
        if ip_address and "," in ip_address:
            ip_address = ip_address.split(",")[0].strip()
        return ip_address

    async def list_platforms(self) -> Dict[str, Any]:
        """获取平台列表

        查询参数:
            page: 页码（默认1）
            page_size: 每页数量（默认10）
            sort_by: 排序字段（默认created_at）
            order: 排序方向（asc/desc，默认desc）
            status: 状态筛选（enabled/disabled）
            type: 类型筛选

        返回:
            包含平台列表和分页信息的响应
        """
        try:
            # 获取查询参数
            page = int(request.args.get("page", 1))
            page_size = int(request.args.get("page_size", 10))
            sort_by = request.args.get("sort_by", "created_at")
            order = request.args.get("order", "desc").lower()
            status = request.args.get("status")
            platform_type = request.args.get("type")

            # 验证参数
            if page < 1:
                return Response().error("页码必须大于0").to_dict()
            if page_size < 1 or page_size > 100:
                return Response().error("每页数量必须在1-100之间").to_dict()
            if order not in ["asc", "desc"]:
                return Response().error("排序方向必须是asc或desc").to_dict()

            # 从数据库获取平台列表
            platforms = db_manager.get_platforms(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                order=order,
                status=status,
                platform_type=platform_type,
            )

            return Response().ok(
                data=platforms,
                message="获取平台列表成功",
            ).to_dict()

        except ValueError as e:
            return Response().error(f"参数格式错误: {str(e)}").to_dict()
        except Exception as e:
            logger.error(f"获取平台列表失败: {e}", exc_info=True)
            return Response().error(f"获取平台列表失败: {str(e)}").to_dict()

    async def add_platform(self) -> Dict[str, Any]:
        """添加平台

        请求参数:
            type: 平台类型
            name: 平台名称
            enable: 是否启用
            config: 平台配置

        返回:
            包含新创建平台信息的响应
        """
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("缺少请求数据").to_dict()

            # 验证必填字段
            is_valid, error_msg = await self.validate_required_fields(
                data, ["type", "name"]
            )
            if not is_valid:
                return Response().error(error_msg).to_dict()

            platform_type = data.get("type")
            name = data.get("name")
            enable = data.get("enable", True)
            config = data.get("config", {})

            # 验证平台类型
            available_platforms = self.context.app.plugins.get(
                "platform_manager"
            ).get_available_platforms()
            available_types = [p.get("id") for p in available_platforms]
            if platform_type not in available_types:
                return Response().error(
                    f"不支持的平台类型，可用类型: {', '.join(available_types)}"
                ).to_dict()

            # 检查名称是否重复
            existing_platforms = db_manager.get_platforms(page=1, page_size=1000)
            for platform in existing_platforms.get("items", []):
                if platform.get("name") == name:
                    return Response().error("平台名称已存在").to_dict()

            # 创建新平台
            new_platform = db_manager.create_platform(
                platform_type=platform_type,
                name=name,
                enable=enable,
                config=config,
            )

            # 记录变更历史
            self._add_platform_history(
                platform_id=new_platform["id"],
                operation="create",
                new_data=new_platform.copy(),
            )

            # 记录操作日志
            logger.info(
                f"用户 {g.user.username} 添加平台: {name} (ID: {new_platform['id']}), IP: {self._get_client_ip()}"
            )

            return Response().ok(
                data=new_platform, message="添加平台成功"
            ).to_dict()

        except Exception as e:
            logger.error(f"添加平台失败: {e}", exc_info=True)
            return Response().error(f"添加平台失败: {str(e)}").to_dict()

    async def update_platform(self) -> Dict[str, Any]:
        """更新平台

        请求参数:
            id: 平台ID
            name: 平台名称（可选）
            enable: 是否启用（可选）
            config: 平台配置（可选）
            version: 版本号（乐观锁）

        返回:
            包含更新后平台信息的响应
        """
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("缺少请求数据").to_dict()

            # 验证必填字段
            is_valid, error_msg = await self.validate_required_fields(data, ["id", "version"])
            if not is_valid:
                return Response().error(error_msg).to_dict()

            platform_id = data.get("id")
            version = data.get("version")

            # 获取现有平台
            platform = db_manager.get_platform(platform_id)
            if not platform:
                return Response().error("平台不存在").to_dict()

            # 检查是否已删除
            if platform.get("deleted_at"):
                return Response().error("平台已被删除，无法更新").to_dict()

            # 乐观锁检查
            if platform.get("version") != version:
                return Response().error(
                    f"数据已被其他用户修改，当前版本: {platform.get('version')}, 您的版本: {version}"
                ).to_dict()

            # 保存旧数据用于历史记录
            old_data = platform.copy()

            # 更新字段
            updated = False
            update_data = {}

            if "name" in data and data["name"]:
                # 检查名称是否重复
                existing_platforms = db_manager.get_platforms(page=1, page_size=1000)
                for p in existing_platforms.get("items", []):
                    if (
                        p.get("id") != platform_id
                        and p.get("name") == data["name"]
                        and not p.get("deleted_at")
                    ):
                        return Response().error("平台名称已存在").to_dict()
                update_data["name"] = data["name"]
                updated = True

            if "enable" in data:
                update_data["enable"] = bool(data["enable"])
                updated = True

            if "config" in data:
                update_data["config"] = data["config"]
                updated = True

            if not updated:
                return Response().error("没有需要更新的字段").to_dict()

            # 更新平台
            updated_platform = db_manager.update_platform(platform_id, update_data)

            # 记录变更历史
            self._add_platform_history(
                platform_id=platform_id,
                operation="update",
                old_data=old_data,
                new_data=updated_platform.copy(),
            )

            # 记录操作日志
            logger.info(
                f"用户 {g.user.username} 更新平台: {updated_platform['name']} (ID: {platform_id}), IP: {self._get_client_ip()}"
            )

            return Response().ok(
                data=updated_platform, message="更新平台成功"
            ).to_dict()

        except Exception as e:
            logger.error(f"更新平台失败: {e}", exc_info=True)
            return Response().error(f"更新平台失败: {str(e)}").to_dict()

    async def delete_platform(self) -> Dict[str, Any]:
        """删除平台（软删除）

        请求参数:
            ids: 平台ID或ID列表

        返回:
            操作结果
        """
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("缺少请求数据").to_dict()

            # 验证必填字段
            is_valid, error_msg = await self.validate_required_fields(data, ["ids"])
            if not is_valid:
                return Response().error(error_msg).to_dict()

            ids = data.get("ids")

            # 支持单个ID或ID列表
            if isinstance(ids, str):
                ids = [ids]
            elif not isinstance(ids, list):
                return Response().error("ids参数必须是字符串或列表").to_dict()

            deleted_count = 0
            deleted_platforms = []

            for platform_id in ids:
                # 获取平台
                platform = db_manager.get_platform(platform_id)
                if not platform:
                    continue

                # 检查是否已删除
                if platform.get("deleted_at"):
                    continue

                # 软删除
                old_data = platform.copy()
                db_manager.delete_platform(platform_id)

                # 记录变更历史
                self._add_platform_history(
                    platform_id=platform_id,
                    operation="delete",
                    old_data=old_data,
                    new_data=platform.copy(),
                )

                deleted_count += 1
                deleted_platforms.append(platform["name"])

            if deleted_count == 0:
                return Response().error("没有找到可删除的平台").to_dict()

            # 记录操作日志
            logger.info(
                f"用户 {g.user.username} 删除平台: {', '.join(deleted_platforms)}, IP: {self._get_client_ip()}"
            )

            return Response().ok(
                data={"deleted_count": deleted_count},
                message=f"成功删除 {deleted_count} 个平台",
            ).to_dict()

        except Exception as e:
            logger.error(f"删除平台失败: {e}", exc_info=True)
            return Response().error(f"删除平台失败: {str(e)}").to_dict()
