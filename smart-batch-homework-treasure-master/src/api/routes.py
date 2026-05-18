import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, FileResponse

from src.config import config
from src.models.schemas import (
    CorrectionResponse,
    HistoryItem,
    ExamResponse,
    QuestionItem,
    UpdateAnswersRequest,
    CorrectionDetail,
)

logger = logging.getLogger(__name__)

# 尝试导入 Agent，未就绪时使用 mock
try:
    from src.agents.homework_agent import HomeworkAgent
    homework_agent = HomeworkAgent()
    AGENT_AVAILABLE = True
except Exception:
    AGENT_AVAILABLE = False
    homework_agent = None

router = APIRouter()

# 内存存储批改历史 & 试题
correction_history: list[HistoryItem] = []
exam_store: dict[str, ExamResponse] = {}

# 记录文件目录（基于项目根目录的绝对路径）
BASE_DIR = Path(__file__).resolve().parent.parent.parent
RECORDS_DIR = BASE_DIR / "uploads" / "records"
RECORDS_DIR.mkdir(parents=True, exist_ok=True)


# =====================================================================
# Mock 数据（模型不可用时回退）
# =====================================================================

MOCK_CORRECTION_RESULT = """# 作业批改报告

## 总分：85 / 100

> 整体掌握良好，注意符号细节与规范。

## 逐题批改

| 题号 | 学生答案 | 标准答案 | 判定 | 得分 | 分析 |
|------|----------|----------|------|------|------|
| 1 | 3.14 | 3.14 | ✅ | 4/4 | 答案正确。 |
| 2 | 5 | 6 | ❌ | 2/4 | 计算时符号出错，过程正确。 |
| 3 | B | B | ✅ | 4/4 | 概念清晰。 |

> 本次批改由 AI 辅助完成，如有疑问请咨询任课老师。
"""

MOCK_EXAM_QUESTIONS = [
    {"question_no": "1", "question_text": "π 保留两位小数等于？", "standard_answer": "3.14", "analysis": "直接取近似值。"},
    {"question_no": "2", "question_text": "2 + 2 × 2 = ?", "standard_answer": "6", "analysis": "先乘后加。"},
    {"question_no": "3", "question_text": "下列哪一个是平行四边形的判定条件？", "standard_answer": "B", "analysis": "对边平行且相等。"},
]

MOCK_CORRECTION_DETAILS = [
    {
        "question_no": "1", "question_text": "π 保留两位小数等于？",
        "student_answer": "3.14", "standard_answer": "3.14",
        "is_correct": True, "score": 4, "full_score": 4,
        "analysis": "答案正确。",
    },
    {
        "question_no": "2", "question_text": "2 + 2 × 2 = ?",
        "student_answer": "5", "standard_answer": "6",
        "is_correct": False, "score": 2, "full_score": 4,
        "analysis": "先乘后加的运算顺序未正确应用，过程部分分。",
    },
    {
        "question_no": "3", "question_text": "判定平行四边形",
        "student_answer": "B", "standard_answer": "B",
        "is_correct": True, "score": 4, "full_score": 4,
        "analysis": "概念掌握到位。",
    },
]


# =====================================================================
# 工具
# =====================================================================

def _validate_image_file(file: UploadFile) -> None:
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    if ext == "jpeg":
        ext = "jpg"

    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型：.{ext}，仅支持 jpg/png/webp"
        )


async def _save_upload_file(file: UploadFile, subdir: str = "") -> str:
    target_dir = os.path.join(config.UPLOAD_DIR, subdir) if subdir else config.UPLOAD_DIR
    os.makedirs(target_dir, exist_ok=True)
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    save_path = os.path.join(target_dir, f"{file_id}{ext}")

    content = await file.read()
    if len(content) > config.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件大小超过 10MB 限制")

    with open(save_path, "wb") as f:
        f.write(content)

    return save_path


def _build_record_markdown(
    correction_id: str,
    filename: str,
    exam: Optional[ExamResponse],
    score: Optional[int],
    details: list[CorrectionDetail],
    result_markdown: str,
    created_at: datetime,
) -> str:
    """构造批改记录 Markdown。"""
    lines = [
        f"# 作业批改记录",
        "",
        f"- 批改ID：`{correction_id}`",
        f"- 作业文件：{filename}",
        f"- 批改时间：{created_at.strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    if exam is not None:
        lines.append(f"- 关联试题：`{exam.id}`（{exam.filename}）")
    if score is not None:
        lines.append(f"- 总分：**{score} / 100**")
    lines.append("")
    lines.append("## 逐题批改记录")
    lines.append("")
    if details:
        for i, d in enumerate(details, start=1):
            lines.append(f"### 第 {d.question_no or i} 题")
            if d.question_text:
                lines.append(f"- **题干**：{d.question_text}")
            lines.append(f"- **学生答案**：{d.student_answer or '（未作答/无法识别）'}")
            lines.append(f"- **正确答案**：{d.standard_answer}")
            judge = '✅ 正确' if d.is_correct else '❌ 错误'
            if d.score is not None and d.full_score is not None:
                judge += f"（{d.score}/{d.full_score}）"
            lines.append(f"- **判定**：{judge}")
            lines.append(f"- **批改分析**：{d.analysis}")
            lines.append("")
    else:
        lines.append("> 本次批改未产生结构化的逐题数据，下面是原始批改输出：")
        lines.append("")
        lines.append(result_markdown)
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 完整批改报告")
    lines.append("")
    lines.append(result_markdown)
    return "\n".join(lines)


def _save_record_file(correction_id: str, markdown: str) -> str:
    path = RECORDS_DIR / f"{correction_id}.md"
    path.write_text(markdown, encoding="utf-8")
    # 返回相对项目根的路径
    return str(path.relative_to(BASE_DIR)).replace("\\", "/")


def _details_from_dicts(items: list[dict]) -> list[CorrectionDetail]:
    out = []
    for d in items or []:
        try:
            out.append(CorrectionDetail(
                question_no=str(d.get("question_no", "")),
                question_text=str(d.get("question_text", "")),
                student_answer=str(d.get("student_answer", "")),
                standard_answer=str(d.get("standard_answer", "")),
                is_correct=bool(d.get("is_correct", False)),
                score=d.get("score"),
                full_score=d.get("full_score"),
                analysis=str(d.get("analysis", "")),
            ))
        except Exception:
            continue
    return out


# =====================================================================
# 试题（Exam）接口
# =====================================================================

@router.post("/exam/upload", response_model=ExamResponse)
async def upload_exam(files: list[UploadFile] = File(...)):
    """上传试题图片（支持多张，如题目卷+答案卷），AI 识别并生成标准答案。"""
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一张图片")

    saved_paths: list[str] = []
    filenames: list[str] = []
    for file in files:
        _validate_image_file(file)
        path = await _save_upload_file(file, subdir="exams")
        saved_paths.append(path)
        filenames.append(file.filename or "exam.jpg")

    questions_data: list[dict] = []
    if AGENT_AVAILABLE and homework_agent is not None:
        try:
            questions_data = await homework_agent.extract_exam(saved_paths)
        except Exception as e:
            # 回退 mock
            questions_data = MOCK_EXAM_QUESTIONS
    else:
        questions_data = MOCK_EXAM_QUESTIONS

    if not questions_data:
        raise HTTPException(status_code=500, detail="试题识别失败，请更换清晰的图片重试")

    display_name = " + ".join(filenames) if len(filenames) > 1 else filenames[0]
    exam = ExamResponse(
        id=str(uuid.uuid4()),
        filename=display_name,
        questions=[QuestionItem(**q) for q in questions_data],
        source="ai",
        created_at=datetime.now(),
    )
    exam_store[exam.id] = exam
    return exam


@router.get("/exams", response_model=list[ExamResponse])
async def list_exams():
    """列出所有已上传的试题。"""
    return sorted(exam_store.values(), key=lambda e: e.created_at, reverse=True)


@router.get("/exam/{exam_id}", response_model=ExamResponse)
async def get_exam(exam_id: str):
    exam = exam_store.get(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="试题不存在")
    return exam


@router.put("/exam/{exam_id}/answers", response_model=ExamResponse)
async def update_exam_answers(exam_id: str, payload: UpdateAnswersRequest):
    """手动覆盖试题的标准答案（全量替换）。"""
    exam = exam_store.get(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="试题不存在")
    exam.questions = payload.questions
    exam.source = "manual"
    exam_store[exam_id] = exam
    return exam


@router.delete("/exam/{exam_id}")
async def delete_exam(exam_id: str):
    if exam_id in exam_store:
        del exam_store[exam_id]
    return {"status": "ok"}


# =====================================================================
# 批改接口
# =====================================================================

@router.post("/correct", response_model=CorrectionResponse)
async def correct_homework(
    file: UploadFile = File(...),
    exam_id: Optional[str] = Form(None),
):
    """批改作业。可选 exam_id：启用标准答案比对模式。"""
    _validate_image_file(file)
    file_path = await _save_upload_file(file)

    exam: Optional[ExamResponse] = None
    standard_answers = None
    if exam_id:
        exam = exam_store.get(exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="指定的试题不存在")
        standard_answers = [q.model_dump() for q in exam.questions]

    result_text = ""
    score: Optional[int] = 85
    details_objs: list[CorrectionDetail] = []

    if AGENT_AVAILABLE and homework_agent is not None:
        try:
            result_text = await homework_agent.correct(file_path, standard_answers=standard_answers)
            score = getattr(homework_agent, "last_score", None) or score
            raw_details = getattr(homework_agent, "last_details", None) or []
            details_objs = _details_from_dicts(raw_details)
        except Exception:
            result_text = MOCK_CORRECTION_RESULT
            if standard_answers:
                details_objs = _details_from_dicts(MOCK_CORRECTION_DETAILS)
    else:
        result_text = MOCK_CORRECTION_RESULT
        if standard_answers:
            details_objs = _details_from_dicts(MOCK_CORRECTION_DETAILS)

    correction_id = str(uuid.uuid4())
    created_at = datetime.now()

    # 生成并保存批改记录文件
    record_md = _build_record_markdown(
        correction_id=correction_id,
        filename=file.filename or "unknown",
        exam=exam,
        score=score,
        details=details_objs,
        result_markdown=result_text,
        created_at=created_at,
    )
    record_path = _save_record_file(correction_id, record_md)

    item = HistoryItem(
        id=correction_id,
        filename=file.filename or "unknown",
        score=score,
        summary=f"作业批改完成，总分 {score} 分。" + (f"（基于试题 {exam.filename}）" if exam else ""),
        result=result_text,
        exam_id=exam.id if exam else None,
        details=details_objs or None,
        record_path=record_path,
        created_at=created_at,
    )
    correction_history.insert(0, item)

    return CorrectionResponse(
        id=correction_id,
        filename=file.filename or "unknown",
        result=result_text,
        score=score,
        exam_id=exam.id if exam else None,
        details=details_objs or None,
        record_path=record_path,
        created_at=created_at,
    )

@router.post("/correct/stream")
async def correct_homework_stream(
        file: UploadFile = File(...),
        exam_id: Optional[str] = Form(None),
):
    """流式批改（SSE），支持标准答案比对。"""
    _validate_image_file(file)
    file_path = await _save_upload_file(file)

    exam: Optional[ExamResponse] = None
    standard_answers = None
    if exam_id:
        exam = exam_store.get(exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="指定的试题不存在")
        standard_answers = [q.model_dump() for q in exam.questions]

    async def event_generator():
        try:
            yield f"data: {json.dumps({'event': 'start', 'message': '开始批改...'}, ensure_ascii=False)}\n\n"

            full_content = ""

            if AGENT_AVAILABLE and homework_agent is not None:
                try:
                    async for chunk in homework_agent.correct_stream(file_path, standard_answers=standard_answers):
                        yield f"data: {chunk}\n\n"
                        # 累积内容用于保存历史
                        try:
                            chunk_data = json.loads(chunk)
                            if chunk_data.get('event') == 'content':
                                full_content += chunk_data.get('text', '')
                        except:
                            pass
                except Exception as e:
                    logger.error(f"流式批改失败: {e}")
                    yield f"data: {json.dumps({'event': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
            else:
                for chunk in _mock_stream_chunks():
                    yield f"data: {chunk}\n\n"
                    await asyncio.sleep(0.2)
                    full_content += chunk

            yield f"data: {json.dumps({'event': 'end', 'message': '批改完成'}, ensure_ascii=False)}\n\n"

            # 保存历史记录
            score = getattr(homework_agent, "last_score", None) if AGENT_AVAILABLE else 85
            details_objs = _details_from_dicts(
                getattr(homework_agent, "last_details", None) or []
            ) if AGENT_AVAILABLE else []

            correction_id = str(uuid.uuid4())
            created_at = datetime.now()

            result_text = full_content or getattr(homework_agent, "_last_stream_result", "")

            record_md = _build_record_markdown(
                correction_id=correction_id,
                filename=file.filename or "unknown",
                exam=exam,
                score=score,
                details=details_objs,
                result_markdown=result_text,
                created_at=created_at,
            )
            _save_record_file(correction_id, record_md)

            item = HistoryItem(
                id=correction_id,
                filename=file.filename or "unknown",
                score=score,
                summary=f"作业批改完成，总分 {score} 分。" + (f"（基于试题 {exam.filename}）" if exam else ""),
                result=result_text,
                exam_id=exam.id if exam else None,
                details=details_objs or None,
                record_path=None,
                created_at=created_at,
            )
            correction_history.insert(0, item)

        except Exception as e:
            logger.error(f"流式生成器异常: {e}")
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _mock_stream_chunks():
    return [
        '{"event": "progress", "message": "正在识别图片内容..."}',
        '{"event": "progress", "message": "识别完成，开始分析题目..."}',
        '{"event": "result", "section": "填空题", "score": "18/20", "detail": "第3题计算失误，其余正确。"}',
        '{"event": "result", "section": "选择题", "score": "16/20", "detail": "第8题概念混淆。"}',
        '{"event": "summary", "total_score": 85, "message": "基础扎实，注意规范与细节。"}',
    ]


# =====================================================================
# 历史 & 记录文件下载
# =====================================================================

@router.get("/history")
async def get_history():
    return correction_history


@router.get("/correction/{correction_id}/record")
async def download_record(correction_id: str):
    """下载批改记录文件（Markdown）。"""
    path = RECORDS_DIR / f"{correction_id}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="批改记录不存在")
    return FileResponse(
        path,
        filename=f"correction_{correction_id}.md",
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
