from fastapi import APIRouter, Depends, HTTPException 
from pydantic import BaseModel, Field  
from sqlmodel.ext.asyncio.session import AsyncSession  # 

from app.services.database.models.user.model import User  # 用户 ORM 模型
from app.services.database.models.user.crud import get_user_by_id  # 通过 ID 获取用户
from app.services.deps import get_session, get_settings_service  # 获取数据库会话与设置服务
from app.services.auth.utils import get_hash_password, password_verify, create_access_token, jwt_decode  # 认证工具
from app.services.auth.factory import AuthServiceFactory  # AuthService 工厂
from app.services.schema import ServiceType  # 服务类型枚举字符串
from app.services.deps import get_service  # 服务定位器：统一从 deps 获取
from app.services.settings.service import SettingsService  # 设置服务类型
    # 检查用户名是否已存在

from sqlmodel import select  # 延迟导入以避免顶部依赖杂乱

router = APIRouter(prefix="/auth", tags=["auth"])  


class AuthPayload(BaseModel):  # 登录/注册请求体模型
    username: str 
    password: str


class TokenPair(BaseModel):  # 返回的令牌对模型
    access: str  # 短期访问令牌
    refresh: str  # 长期刷新令牌


class UserOut(BaseModel):  # 对外暴露的用户信息
    id: int  # 用户 ID
    username: str  # 用户名


class LoginResult(BaseModel):  # 登录/注册响应模型
    access: str  # 访问令牌
    refresh: str  # 刷新令牌
    user: UserOut  # 用户基本信息


class RefreshPayload(BaseModel):  # 刷新请求体
    refresh: str  # 刷新令牌字符串


class AccessOnly(BaseModel):  # 刷新响应体
    access: str  # 新的访问令牌

def get_auth_service() -> "AuthService":  # 依赖：按需获取 AuthService 实例
    settings_service: SettingsService = get_settings_service()  # 获取设置服务
    return get_service(ServiceType.AUTH_SERVICE, AuthServiceFactory())  # 返回 AuthService


@router.post("/register", response_model=LoginResult)  # 注册接口：返回与登录相同结构
async def register(payload: AuthPayload, db: AsyncSession = Depends(get_session)):
    exists = (await db.execute(select(User).where(User.username == payload.username))).scalar()  # 查询重名
    if exists :  # 若已存在则报错
        raise HTTPException(status_code=400, detail="Username already exists")  # 400 用户名重复

    # 创建用户并持久化
    hashed = await get_hash_password(payload.password)  # 计算密码哈希
    user = User(username=payload.username, email=f"{payload.username}@example.com", password=hashed)  # 简化：email 占位
    db.add(user)  # 加入会话
    await db.commit()  # 提交事务
    await db.refresh(user)  # 刷新获取自增 ID

    # 签发访问/刷新令牌
    auth = get_auth_service()  # 获取 AuthService 实例
    tokens = await auth.issue_tokens(user.id)  # 生成令牌对

    # 组装响应
    return LoginResult(access=tokens["access"], refresh=tokens["refresh"], user=UserOut(id=user.id, username=user.username))  # 返回数据


@router.post("/login", response_model=LoginResult)  # 登录接口
async def login(payload: AuthPayload, db: AsyncSession = Depends(get_session)):
    # 通过用户名查询用户
    from sqlmodel import select  # 延迟导入 select
    user = (await db.execute(select(User).where(User.username == payload.username))).scalar()  # 查找用户
    if not user:  # 用户不存在
        raise HTTPException(status_code=401, detail="Invalid credentials And User not found")  # 401 凭证无效

    # 校验密码
    ok = await password_verify(payload.password, user.password)  # 比对密码哈希
    if not ok:  # 密码错误
        raise HTTPException(status_code=401, detail="Invalid credentials And Password not match")  

    # 签发令牌
    auth = get_auth_service()  # 获取 AuthService
    tokens = await auth.issue_tokens(user.id)  # 生成令牌对

    # 返回结果
    return LoginResult(access=tokens["access"], refresh=tokens["refresh"], user=UserOut(id=user.id, username=user.username))  # 登录成功

@router.post("/refresh", response_model=AccessOnly)  # 刷新接口
async def refresh_token(payload: RefreshPayload):
    # 解码 refresh，确认有效与类型
    user_id = await jwt_decode(payload.refresh)  # 从 refresh 中取出 sub=user_id
    if not user_id:  # 过期或无效
        raise HTTPException(status_code=401, detail="Invalid refresh token")  # 401 刷新无效

    # 解析载荷以验证类型字段
    import jwt as _jwt  # 引入 jwt 库用于无校验读取（类型检查）
    from app.services.deps import get_settings_service as _get_settings  # 引入设置服务
    try:
        payload_all = _jwt.decode(payload.refresh, _get_settings().settings.jwt_secret, algorithms=["HS256"])  # 解码 payload
        if payload_all.get("type") != "refresh":  # 必须是 refresh 类型
            raise HTTPException(status_code=401, detail="Invalid token type")  # 类型错误
    except _jwt.ExpiredSignatureError:  # 过期错误
        raise HTTPException(status_code=401, detail="Expired refresh token")  # 401 刷新过期

    # 生成新的 access
    from datetime import timedelta  # 导入时间差
    settings = get_settings_service().settings  # 读取配置
    access = create_access_token({"sub": str(user_id), "type": "access"}, timedelta(minutes=settings.access_expire_min))  # 新访问令牌
    return AccessOnly(access=access)  # 返回新的 access


@router.post("/logout", status_code=204)  # 登出接口：简版，前端清空令牌
async def logout(_: RefreshPayload | None = None):
    # 简化策略：不持久化 refresh，服务端不做黑名单；前端收到 204 即清空本地
    return None  # 返回空响应体，HTTP 204
