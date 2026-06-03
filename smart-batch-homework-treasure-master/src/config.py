import os
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv

# 加载 .env 文件
_dotenv_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_dotenv_path)

class Config:
    # LLM API 配置（通过 .env 设置）
    MODEL_API_KEY = os.getenv("MODEL_API_KEY", "")
    MODEL_NAME = os.getenv("MODEL_NAME", "")
    MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "")

    # 应用配置
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "8000"))
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"

    # MySQL 配置
    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "homework123")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "homework")

    @classmethod
    def database_url(cls) -> str:
        return (
            f"mysql+aiomysql://{quote_plus(cls.MYSQL_USER)}:{quote_plus(cls.MYSQL_PASSWORD)}"
            f"@{cls.MYSQL_HOST}:{cls.MYSQL_PORT}/{cls.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )

    # OCR 配置
    OCR_ENABLED = os.getenv("OCR_ENABLED", "True").lower() == "true"

    # 文件上传配置
    UPLOAD_DIR = "uploads"
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

config = Config()





