import base64
import os
import uuid

from src.config import config


def validate_image(filename: str, file_size: int) -> bool:
    """校验图片格式和大小"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in config.ALLOWED_EXTENSIONS:
        return False
    if file_size > config.MAX_FILE_SIZE:
        return False
    return True


def save_image(content: bytes, filename: str) -> str:
    """保存图片到uploads目录，返回保存路径"""
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    ext = filename.rsplit(".", 1)[-1].lower()
    saved_name = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(config.UPLOAD_DIR, saved_name)
    with open(path, "wb") as f:
        f.write(content)
    return path


def image_to_base64(content: bytes) -> str:
    """将图片内容转为base64字符串"""
    return base64.b64encode(content).decode("utf-8")


def get_image_media_type(filename: str) -> str:
    """根据文件名获取MIME类型"""
    ext = filename.rsplit(".", 1)[-1].lower()
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    return mime_map.get(ext, "image/jpeg")
