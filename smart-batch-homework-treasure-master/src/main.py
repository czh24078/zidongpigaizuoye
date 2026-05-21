import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 项目根目录：main.py 的上一级
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = BASE_DIR / "uploads"

# 确保项目根目录在 sys.path，兼容直接运行和模块运行两种方式
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# 先用相对导入尝试，失败则直接导入（兼容直接运行 python main.py）
try:
    from .api.routes import router as api_router
    from .database import init_db, engine
except ImportError:
    from src.api.routes import router as api_router
    from src.database import init_db, engine

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    yield
    await engine.dispose()


app = FastAPI(
    title="智能作业批改系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
