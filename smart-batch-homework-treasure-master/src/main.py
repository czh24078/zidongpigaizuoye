import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# 添加项目根目录到 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.routes import router as api_router

# 项目根目录（src/main.py 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = BASE_DIR / "uploads"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：初始化数据库和 uploads 目录
    from src.database import init_db, engine
    await init_db()
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    yield
    # 关闭：释放数据库连接池
    await engine.dispose()


app = FastAPI(
    title="智能作业批改系统",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由
app.include_router(api_router, prefix="/api")

# 静态文件
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# 根路径返回前端页面
@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
