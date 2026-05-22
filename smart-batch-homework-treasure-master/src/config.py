import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
_dotenv_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_dotenv_path)

class Config:
    # 阿里云百炼 API 配置（优先使用环境变量，否则使用硬编码值）
    MODEL_API_KEY = os.getenv("MODEL_API_KEY", "sk-10c2d9b02f9a4fe1ad7a800d31f8cc2d")
    MODEL_NAME = os.getenv("MODEL_NAME", "qwen-vl-max-latest")
    MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    # 应用配置
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "8000"))
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"

    # SQLite 数据库配置
    SQLITE_PATH = os.getenv("SQLITE_PATH", str(Path(__file__).resolve().parent.parent / "data" / "homework.db"))

    @classmethod
    def database_url(cls) -> str:
        db_path = Path(cls.SQLITE_PATH)
        if not db_path.is_absolute():
            db_path = Path(__file__).resolve().parent.parent / db_path
        return f"sqlite+aiosqlite:///{str(db_path).replace(chr(92), '/')}"

    # OCR 配置
    OCR_ENABLED = os.getenv("OCR_ENABLED", "True").lower() == "true"

    # 文件上传配置
    UPLOAD_DIR = "uploads"
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

    # 性能优化配置
    MODEL_MAX_TOKENS = int(os.getenv("MODEL_MAX_TOKENS", "2048"))  # 限制输出长度
    MODEL_STREAMING = os.getenv("MODEL_STREAMING", "True").lower() == "true"  # 启用流式输出

config = Config()





