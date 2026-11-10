"""
FastAPI 应用入口
CORS 全开、路由注册、startup/shutdown 事件
"""
import sys
import os
import asyncio
import hmac
import time
from pathlib import Path
from contextlib import asynccontextmanager, suppress

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pymongo.errors import PyMongoError

from .api.chat import router as chat_router
from .api.history import router as history_router
from .api.observability import router as observability_router
from .web_config import close_mongo_client
from ..agent.log_utils import web_logger
from ..agent.backends.sandbox_manager import sandbox_manager
from ..agent.config import SANDBOX_MAINTENANCE_INTERVAL_SECONDS


async def _sandbox_maintenance(stop_event: asyncio.Event) -> None:
    """后台补齐预热池、回收空闲容器。

    主请求中的 HealthMiddleware 才负责“重建 + Proxy 热替换 + 文件回填”；此处
    绝不直接调用 ``health_check_all``，否则 Agent 仍会持有旧后端引用。
    """
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(sandbox_manager.cleanup_idle_sandboxes)
            await asyncio.to_thread(sandbox_manager.ensure_warm_pool)
        except Exception as exc:
            web_logger.warning(f"Sandbox maintenance iteration failed: {exc}")

        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=SANDBOX_MAINTENANCE_INTERVAL_SECONDS
            )
        except TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    web_logger.info("Starting ERP Agent Web Server...")
    stop_event = asyncio.Event()
    maintenance_task = None
    try:
        # 预热失败不阻止 Web 服务启动；首个请求仍会按需创建并回退到 LocalShell。
        await asyncio.to_thread(sandbox_manager.ensure_warm_pool)
        maintenance_task = asyncio.create_task(
            _sandbox_maintenance(stop_event), name="sandbox-maintenance"
        )
        yield
    finally:
        web_logger.info("Shutting down ERP Agent Web Server...")
        stop_event.set()
        if maintenance_task is not None:
            maintenance_task.cancel()
            with suppress(asyncio.CancelledError):
                await maintenance_task
        # 不销毁已认领容器：Manager 会把 user → container 映射持久化，重启后可恢复。
        await close_mongo_client()


app = FastAPI(
    title="DeepAgent 智能采购助手",
    description="基于 Harness Engineering 架构的制造企业智能采购助手 API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(PyMongoError)
async def mongo_unavailable_handler(request: Request, exc: PyMongoError):
    """Mongo 不可用时返回可重试的 503，而不是裸 500。"""
    web_logger.error(f"MongoDB unavailable on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=503,
        content={
            "detail": "会话存储暂时不可用，请稍后重试",
            "code": "DEPENDENCY_UNAVAILABLE",
            "dependency": "mongodb",
            "retryable": True,
        },
    )

# CORS 全开（开发环境）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_RATE: dict[str, list[float]] = {}
_RATE_LOCK = asyncio.Lock()

@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """按用户限制对话接口频率，避免单一调用方打满模型与工具。"""
    if request.url.path.startswith("/api/chat"):
        limit = int(os.getenv("AGENT_RATE_LIMIT_PER_MINUTE", "30"))
        user = request.headers.get("X-User-Id", "anonymous")
        now = time.monotonic()
        async with _RATE_LOCK:
            bucket = [t for t in _RATE.get(user, []) if now - t < 60]
            if len(bucket) >= limit:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "too many requests", "retryAfter": 60},
                )
            bucket.append(now)
            _RATE[user] = bucket
    return await call_next(request)


@app.middleware("http")
async def require_internal_token(request: Request, call_next):
    """配置共享令牌后，仅接受业务后端发起的内部 API 调用。"""
    expected = os.getenv("AGENT_INTERNAL_TOKEN", "").strip()
    if expected and request.url.path.startswith("/api/"):
        supplied = request.headers.get("X-Internal-Token", "")
        if not hmac.compare_digest(expected, supplied):
            return JSONResponse(status_code=401, content={"detail": "invalid internal token"})
    return await call_next(request)

# 注册路由
app.include_router(chat_router)
app.include_router(history_router)
app.include_router(observability_router)

# 文件下载目录（图表等生成文件）
DOWNLOAD_DIR = Path(__file__).resolve().parents[2] / "data" / "download"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """提供生成文件（图表PNG等）的HTTP下载"""
    file_path = DOWNLOAD_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
    )


@app.get("/")
async def root():
    return {"message": "DeepAgent 智能采购助手 API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
