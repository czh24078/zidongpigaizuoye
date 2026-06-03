"""
OCR 服务 —— 基于 RapidOCR (PaddleOCR ONNX 推理) 提取图片中的文字。

RapidOCR 使用 PaddleOCR 的模型权重但通过 ONNX Runtime 推理，
无需安装 PaddlePaddle 框架，更轻量且跨平台兼容性好。
"""

import logging

logger = logging.getLogger(__name__)

# 延迟导入，避免未安装时直接报错
_engine = None


def _get_engine():
    """懒加载 RapidOCR 引擎（单例）。"""
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
            logger.info("RapidOCR 引擎初始化成功")
        except ImportError:
            logger.warning(
                "rapidocr-onnxruntime 未安装，OCR 功能不可用。"
                "请执行: uv add rapidocr-onnxruntime"
            )
            raise
    return _engine


def ocr_image(image_path: str) -> str:
    """
    对单张图片执行 OCR，返回识别出的全部文字（按阅读顺序拼接）。

    Args:
        image_path: 图片文件的绝对/相对路径

    Returns:
        识别出的文字内容，若无文字则返回空字符串
    """
    engine = _get_engine()
    result, _ = engine(image_path)

    if not result:
        logger.warning(f"OCR 未识别到任何文字: {image_path}")
        return ""

    # result 是 list of [bbox, text, confidence]
    lines = [item[1] for item in result]
    text = "\n".join(lines)
    logger.info(f"OCR 识别完成: {image_path} -> {len(lines)} 行文字")
    return text

def ocr_available() -> bool:
    """检测 OCR 引擎是否可用。"""
    try:
        _get_engine()
        return True
    except (ImportError, Exception):
        return False
