from fastapi import APIRouter

from app.api.v1 import test_router
from app.api.v1 import hello_router
from app.api.v1 import finance_router
from app.api.v1.auth import router as auth_router  # 引入认证路由

router_v1 = APIRouter(prefix="/v1")
router_v1.include_router(test_router)
router_v1.include_router(hello_router)
router_v1.include_router(auth_router)  # 注册 /api/v1/auth 路由
router_v1.include_router(finance_router)  # 注册 /api/v1/finance 路由

router = APIRouter(prefix="/api")

router.include_router(router_v1)
