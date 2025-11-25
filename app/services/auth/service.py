from __future__ import annotations

from app.services.base import Service
from app.services.settings.service import SettingsService
from datetime import timedelta  # 每次调用时再导入，避免循环引用
from app.services.auth.utils import create_access_token  # 生成 JWT 的工具函数

class AuthService(Service):
    name = "auth_service"

    def __init__(self, settings_service: SettingsService):
        self.settings_service = settings_service

    async def issue_tokens(self, user_id: int) -> dict:
        # import locally to avoid circulars

        # 从设置服务中读取过期时间配置（分钟、天）
        access_minutes = self.settings_service.settings.access_expire_min  # ACCESS_EXPIRE_MIN 配置
        refresh_days = self.settings_service.settings.refresh_expire_days  # REFRESH_EXPIRE_DAYS 配置

        # 生成 access token，包含用户 ID 与类型声明
        access = create_access_token({"sub": str(user_id), "type": "access"}, timedelta(minutes=access_minutes))  # 访问令牌
        # 生成 refresh token，时间更长，仅用于刷新 access
        refresh = create_access_token({"sub": str(user_id), "type": "refresh"}, timedelta(days=refresh_days))  # 刷新令牌

        # 打包返回给上层（路由层会附带 user 信息）
        return {"access": access, "refresh": refresh}  # 返回令牌对
