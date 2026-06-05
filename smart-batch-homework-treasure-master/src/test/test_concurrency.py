"""
并发测试脚本

使用方式:
    uv run python src/test/test_concurrency.py              # 默认: L1 health 接口, 并发5, 请求20
    uv run python src/test/test_concurrency.py L1           # 仅 health 接口
    uv run python src/test/test_concurrency.py L2           # health + correct (Mock)
    uv run python src/test/test_concurrency.py L3           # 全部端点 (含 AI 出题)
    uv run python src/test/test_concurrency.py --help       # 查看参数

环境要求: 服务已启动 (默认 http://127.0.0.1:8000)
"""

import argparse
import concurrent.futures
import functools
import http.client
import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_BASE = "http://127.0.0.1:8000"

# 测试用图片（确保存在）
TEST_IMAGE = PROJECT_ROOT / "src" / "test" / "resources" / "ans1.jpg"


@dataclass
class RequestResult:
    index: int
    endpoint: str
    status: int
    elapsed: float        # 秒
    body_size: int
    error: Optional[str] = None


@dataclass
class Report:
    name: str
    results: list[RequestResult] = field(default_factory=list)

    @property
    def success(self) -> list[RequestResult]:
        return [r for r in self.results if r.error is None]

    @property
    def failed(self) -> list[RequestResult]:
        return [r for r in self.results if r.error is not None]

    @property
    def times(self) -> list[float]:
        return sorted(r.elapsed for r in self.success)

    def percentile(self, p: float) -> float:
        if not self.times:
            return 0.0
        idx = int(len(self.times) * p / 100)
        return self.times[min(idx, len(self.times) - 1)]

    def print(self):
        total = len(self.results)
        ok = len(self.success)
        fail = len(self.failed)
        print(f"\n{'='*60}")
        print(f"  {self.name}")
        print(f"{'='*60}")
        print(f"  总请求: {total}    成功: {ok}    失败: {fail}")
        if fail:
            for r in self.failed[:5]:
                print(f"    [FAIL #{r.index}] {r.endpoint} — {r.error}")
            if fail > 5:
                print(f"    ... 共 {fail} 个失败")
        if not self.times:
            print("  无成功请求，跳过统计")
            return
        t = self.times
        print(f"  响应时间 (秒)")
        print(f"    Min     {min(t):.3f}")
        print(f"    Avg     {sum(t)/len(t):.3f}")
        print(f"    P50     {self.percentile(50):.3f}")
        print(f"    P95     {self.percentile(95):.3f}")
        print(f"    P99     {self.percentile(99):.3f}")
        print(f"    Max     {max(t):.3f}")
        if len(t) >= 2:
            print(f"    StdDev  {statistics.stdev(t):.3f}")
        status_codes = {}
        for r in self.success:
            status_codes[r.status] = status_codes.get(r.status, 0) + 1
        print(f"  HTTP 状态码: {status_codes}")
        total_bytes = sum(r.body_size for r in self.success)
        print(f"  总流量: {total_bytes / 1024:.1f} KB")
        throughput = ok / (max(t) if t else 1)
        print(f"  吞吐量: {throughput:.1f} req/s")


# ---------------------------------------------------------------------------
# HTTP 请求（stdlib，零依赖）
# ---------------------------------------------------------------------------

def _request(method: str, path: str, base: str, body: Optional[bytes] = None,
             headers: Optional[dict] = None, timeout: int = 60) -> tuple[int, bytes]:
    url = urllib.parse.urlparse(base)
    conn = http.client.HTTPConnection(url.hostname, url.port, timeout=timeout)
    h = headers or {}
    if body:
        h.setdefault("Content-Type", "application/json")
    conn.request(method, path, body=body, headers=h)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def _multipart_request(path: str, base: str, file_path: str, fields: dict,
                       timeout: int = 120) -> tuple[int, bytes]:
    """构造 multipart/form-data 请求（stdlib 实现）。"""
    boundary = "----ConcurrencyTestBoundary"
    body_lines = []
    for name, value in fields.items():
        body_lines.append(f"--{boundary}")
        body_lines.append(f'Content-Disposition: form-data; name="{name}"')
        body_lines.append("")
        body_lines.append(value)
    body_lines.append(f"--{boundary}")
    fname = os.path.basename(file_path)
    body_lines.append(f'Content-Disposition: form-data; name="file"; filename="{fname}"')
    body_lines.append("Content-Type: image/jpeg")
    body_lines.append("")
    body_parts = "\r\n".join(body_lines).encode("utf-8")
    with open(file_path, "rb") as f:
        file_content = f.read()
    body = body_parts + b"\r\n" + file_content + f"\r\n--{boundary}--\r\n".encode()

    url = urllib.parse.urlparse(base)
    conn = http.client.HTTPConnection(url.hostname, url.port, timeout=timeout)
    conn.request("POST", path, body=body,
                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

def req_health(base: str, index: int) -> RequestResult:
    t0 = time.perf_counter()
    try:
        status, data = _request("GET", "/api/health", base)
        return RequestResult(index, "GET /api/health", status,
                             time.perf_counter() - t0, len(data))
    except Exception as e:
        return RequestResult(index, "GET /api/health", 0,
                             time.perf_counter() - t0, 0, str(e))


def req_question_bank(base: str, index: int) -> RequestResult:
    t0 = time.perf_counter()
    try:
        status, data = _request("GET", "/api/question-bank", base)
        return RequestResult(index, "GET /api/question-bank", status,
                             time.perf_counter() - t0, len(data))
    except Exception as e:
        return RequestResult(index, "GET /api/question-bank", 0,
                             time.perf_counter() - t0, 0, str(e))


def req_correct_mock(base: str, index: int, image: Path) -> RequestResult:
    """批改接口（Mock 模式，不需要 AI Key）。"""
    if not image.exists():
        return RequestResult(index, "POST /api/correct", 0, 0, 0,
                             f"测试图片不存在: {image}")
    t0 = time.perf_counter()
    try:
        status, data = _multipart_request("/api/correct", base,
                                          str(image), {})
        return RequestResult(index, "POST /api/correct", status,
                             time.perf_counter() - t0, len(data))
    except Exception as e:
        return RequestResult(index, "POST /api/correct", 0,
                             time.perf_counter() - t0, 0, str(e))


def req_ai_generate(base: str, index: int) -> RequestResult:
    body = json.dumps({
        "subject": "数学", "grade": "初中", "difficulty": "中等",
        "count": 3, "requirement": "勾股定理",
    }).encode()
    t0 = time.perf_counter()
    try:
        status, data = _request("POST", "/api/ai-generate", base, body)
        return RequestResult(index, "POST /api/ai-generate", status,
                             time.perf_counter() - t0, len(data))
    except Exception as e:
        return RequestResult(index, "POST /api/ai-generate", 0,
                             time.perf_counter() - t0, 0, str(e))


# ---------------------------------------------------------------------------
# 执行引擎
# ---------------------------------------------------------------------------

def run_concurrent(fn, base: str, total: int, workers: int, label: str) -> Report:
    report = Report(name=label)
    print(f"\n  运行: {label}  (并发={workers}, 总请求={total})")
    t0 = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fn, base, i) for i in range(total)]
        for future in concurrent.futures.as_completed(futures):
            report.results.append(future.result())

    elapsed = time.perf_counter() - t0
    print(f"  耗时: {elapsed:.1f}s")
    return report


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="智能作业批改系统 — 并发测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                    L1 级别, 并发5, 请求20
  %(prog)s L2                 L2 级别 (health + correct)
  %(prog)s L3 --workers 10    并发10, L3 全端点
  %(prog)s --base http://localhost:8080  指定服务地址
        """,
    )
    parser.add_argument(
        "level", nargs="?", default="L1", choices=["L1", "L2", "L3"],
        help="测试级别: L1=health 轻量, L2=+correct(Mock), L3=全部 (默认 L1)",
    )
    parser.add_argument(
        "-w", "--workers", type=int, default=5,
        help="并发线程数 (默认 5)",
    )
    parser.add_argument(
        "-n", "--requests", type=int, default=20,
        help="总请求数 (默认 20)",
    )
    parser.add_argument(
        "--base", default=DEFAULT_BASE,
        help=f"服务地址 (默认 {DEFAULT_BASE})",
    )
    parser.add_argument(
        "--image", default=None,
        help="批改测试用的图片路径",
    )
    args = parser.parse_args()

    # 允许外部覆盖测试图片
    image_path = Path(args.image) if args.image else TEST_IMAGE

    base = args.base.rstrip("/")
    workers = args.workers
    total = args.requests

    print(f"{'='*60}")
    print(f"  并发测试 — 智能作业批改系统")
    print(f"{'='*60}")
    print(f"  地址: {base}")
    print(f"  级别: {args.level}")
    print(f"  并发: {workers}    总请求: {total}")
    print(f"  图片: {TEST_IMAGE}")

    # 先检查服务可达
    try:
        status, data = _request("GET", "/api/health", base, timeout=5)
        info = json.loads(data)
        print(f"  状态: {'AI可用' if info.get('ai_available') else 'Mock模式'}"
              f"  DB={info.get('db', '?')}")
    except Exception as e:
        print(f"\n  [FATAL] 无法连接服务: {e}")
        print(f"  请确保服务已启动: uv run python -m src.main\n")
        sys.exit(1)

    reports: list[Report] = []

    # ---- L1: Health + 题库 ----
    reports.append(run_concurrent(req_health, base, total, workers,
                                  "L1-a: GET /api/health"))
    reports.append(run_concurrent(req_question_bank, base, total, workers,
                                  "L1-b: GET /api/question-bank"))

    if args.level in ("L2", "L3"):
        # ---- L2: 批改（Mock） ----
        correct_fn = functools.partial(req_correct_mock, image=image_path)
        reports.append(run_concurrent(
            correct_fn, base, max(total // 2, 1), workers,
            "L2: POST /api/correct (Mock 模式)",
        ))

    if args.level == "L3":
        reports.append(run_concurrent(
            req_ai_generate, base, max(total // 2, 1), workers,
            "L3: POST /api/ai-generate",
        ))

    # ---- 总览 ----
    print(f"\n{'='*60}")
    print(f"  总览")
    print(f"{'='*60}")
    for r in reports:
        r.print()

    # 底线: 任一报告失败率 > 20% 返回非零退出码
    for r in reports:
        if len(r.failed) / max(len(r.results), 1) > 0.2:
            print(f"\n  [WARN] {r.name} 失败率过高，请检查服务状态")
            sys.exit(1)

    print("\n  完成。")


if __name__ == "__main__":
    main()
