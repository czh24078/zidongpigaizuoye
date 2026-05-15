"""
OCR 功能本地测试脚本

使用方式：在下方 IMAGE_PATHS 列表中填入要测试的图片路径，然后执行：
    uv run python src/test/test_ocr.py
"""

import sys
import os
import time

# 确保项目根目录在 sys.path 中（test_ocr.py 位于 src/test/ 下，需往上两级）
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

# ===== 在这里填入要测试的图片路径 =====
IMAGE_PATHS = [
    "src/test/resources/ans1.jpg",
    # "src/uploads/exams/0eb8049c-4992-4177-a35b-894bf2ec2f41.jpg",
    # "C:/absolute/path/to/image.png",
]
# ======================================

from src.services.ocr_service import ocr_image

for path in IMAGE_PATHS:
    full_path = path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)
    if not os.path.exists(full_path):
        print(f"[跳过] 文件不存在: {path}")
        continue

    start = time.time()
    text = ocr_image(full_path)
    elapsed = time.time() - start

    print(f"\n📄 {os.path.basename(path)}  ({elapsed:.2f}s)")
    print("-" * 40)
    print(text if text.strip() else "(未识别到文字)")
    print("-" * 40)
