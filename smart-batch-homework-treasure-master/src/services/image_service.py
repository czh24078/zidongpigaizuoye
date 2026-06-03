import base64


def image_to_base64(content: bytes) -> str:
    """将图片内容转为base64字符串"""
    return base64.b64encode(content).decode("utf-8")


def get_image_media_type(filename: str) -> str:
    """根据文件名获取MIME类型"""
    ext = filename.rsplit(".", 1)[-1].lower()
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    return mime_map.get(ext, "image/jpeg")
