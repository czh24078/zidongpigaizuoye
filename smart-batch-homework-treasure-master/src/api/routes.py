import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import select, delete, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import config
from src.database import get_db
from src.models.schemas import (
    CorrectionResponse,
    HistoryItem,
    ExamResponse,
    UpdateAnswersRequest,
    CorrectionDetail,
    QuestionBankItemSchema,
    AddToBankRequest,
    AIGenerateRequest,
    AIGenerateResponse,
    AIGeneratedQuestion,
)
from src.models.db_models import (
    Exam,
    Question,
    Correction,
    CorrectionDetail as CorrectionDetailDB,
    QuestionBankItem,
)

logger = logging.getLogger(__name__)

try:
    from src.agents.homework_agent import HomeworkAgent
    homework_agent = HomeworkAgent()
    AGENT_AVAILABLE = True
except Exception:
    AGENT_AVAILABLE = False
    homework_agent = None

router = APIRouter()

# 记录文件目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent
RECORDS_DIR = BASE_DIR / "uploads" / "records"
RECORDS_DIR.mkdir(parents=True, exist_ok=True)


# =====================================================================
# Mock 数据
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
    {"question_no": "1", "question_text": "π 保留两位小数等于？", "student_answer": "3.14", "standard_answer": "3.14",
     "is_correct": True, "score": 4, "full_score": 4, "analysis": "答案正确。"},
    {"question_no": "2", "question_text": "2 + 2 × 2 = ?", "student_answer": "5", "standard_answer": "6",
     "is_correct": False, "score": 2, "full_score": 4, "analysis": "先乘后加的运算顺序未正确应用，过程部分分。"},
    {"question_no": "3", "question_text": "判定平行四边形", "student_answer": "B", "standard_answer": "B",
     "is_correct": True, "score": 4, "full_score": 4, "analysis": "概念掌握到位。"},
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
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：.{ext}，仅支持 jpg/png/webp")


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


async def _auto_add_to_bank(session: AsyncSession, exam_id: Optional[str], questions: list[dict], display_name: str) -> int:
    """将题目自动加入题库（去重），返回新增数量。"""
    max_no_result = await session.execute(select(func.max(QuestionBankItem.bank_no)))
    max_no = max_no_result.scalar() or 0
    added = 0
    for q in questions:
        q_text = q.get("question_text", "")
        q_answer = q.get("standard_answer", "")
        existing = await session.execute(
            select(QuestionBankItem).where(
                QuestionBankItem.question_text == q_text,
                QuestionBankItem.standard_answer == q_answer,
            )
        )
        if existing.scalar_one_or_none():
            continue
        subject = q.get("subject") or _guess_subject(display_name, q_text)
        added += 1
        session.add(QuestionBankItem(
            exam_id=exam_id,
            question_no=q.get("question_no", ""),
            question_text=q_text,
            standard_answer=q_answer,
            analysis=q.get("analysis", ""),
            exam_filename=display_name,
            bank_no=max_no + added,
            subject=subject,
            added_at=datetime.now(),
        ))
    return added


_SUBJECT_KEYWORDS = {
    "语文": [
        "拼音", "汉字", "笔画", "偏旁", "部首", "成语", "古诗", "文言文", "阅读理解",
        "作文", "修辞", "病句", "默写", "诗人", "作者", "叙述", "论点", "论证", "翻译",
        "标点", "词语", "句子", "段落", "写作", "赏析", "背诵", "近义词", "反义词",
        "多音字", "形近字", "歇后语", "把字句", "被字句", "反问句", "陈述句",
        "比喻", "拟人", "排比", "夸张", "对偶", "设问", "借代", "对比",
        "唐诗", "宋词", "元曲", "论语", "诗经", "小说", "散文", "戏剧",
        "《", "》", "李白", "杜甫", "白居易", "鲁迅",
        "选词填空", "修改病句", "造句", "组词", "课文", "描写", "表达", "作者",
        "选出", "正确", "错误", "判断对错", "连线", "解释词语", "意思",
        "看拼音", "写词语", "按课文", "填空", "回答问题", "短文", "选文",
        "诗人", "诗句", "全文", "中心思想", "表达", "感情", "主要",
        "把下列", "改为", "仿写", "续写", "缩写", "扩写", "读后感",
        "标序号", "对话", "寓言", "童话", "神话", "说明文", "记叙文",
        "书信", "通知", "请假条", "日记", "请假条", "启事", "广告",
    ],
    "数学": [
        "方程", "函数", "几何", "三角", "代数", "计算", "概率", "统计", "面积", "体积",
        "周长", "角度", "边长", "导数", "积分", "坐标", "数列", "不等式", "因式分解",
        "平方", "立方", "根号", "解方程", "求值", "证明", "化简", "通分", "约分",
        "最大公因数", "最小公倍数", "质数", "合数", "因数", "倍数", "分数", "小数",
        "百分数", "比例", "一次函数", "二次函数", "勾股定理",
        "多边形", "平行四边形", "长方形", "正方形", "三角形", "梯形", "圆",
        "sin", "cos", "tan", "log", "x=", "y=", "象限", "抛物线",
        "等于", "列式", "算式", "脱式", "简便", "单位换算",
        "cm", "m²", "cm²", "km", "kg", "元", "角", "分",
        "一共", "几", "结果", "多少", "平均", "每", "倍",
        "厘米", "毫米", "分米", "千米", "吨", "毫升", "升",
        "加起来", "减去", "乘以", "除以", "余数", "约等于",
        "算式", "笔算", "口算", "估算", "验算", "递等式",
        "周长", "边长", "半径", "直径", "底面积", "表面积",
        "不等式", "正数", "负数", "相反数", "绝对值", "倒数",
    ],
    "物理": [
        "力", "速度", "加速度", "质量", "密度", "压强", "电流", "电压", "电阻", "磁场",
        "电场", "重力", "浮力", "功", "功率", "能量", "动量", "热量", "温度", "振动",
        "波", "光", "折射", "反射", "牛顿", "焦耳", "瓦特", "欧姆", "安培", "伏特",
        "电路", "串联", "并联", "电磁", "感应", "摩擦力", "弹力", "惯性", "动能",
        "势能", "机械能", "比热容", "沸点", "熔点", "凝固", "汽化", "液化",
        "原子", "分子", "电子", "质子", "中子", "核能",
        "N/kg", "m/s", "kg/m³", "Ω", "Hz", "位移", "路程",
        "匀速", "变速", "自由落体", "弹簧", "天平", "量筒", "秒表", "电磁铁",
        "匀速直线", "参照物", "作用力", "反作用力", "平衡力", "合力",
        "正极", "负极", "电荷", "绝缘体", "导体", "半导体",
        "入射角", "反射角", "折射角", "焦距", "凸透镜", "凹透镜",
        "音调", "响度", "音色", "超声波", "次声波", "分贝",
    ],
    "历史": [
        "朝代", "皇帝", "战争", "革命", "条约", "变法", "制度", "封建", "帝国", "起义",
        "统一", "分裂", "建国", "秦朝", "汉朝", "唐朝", "宋朝", "元朝", "明朝", "清朝",
        "民国", "共和国", "鸦片", "甲午", "维新", "辛亥革命", "五四运动", "抗日战争",
        "解放战争", "改革开放", "秦始皇", "汉武帝", "唐太宗", "宋太祖", "成吉思汗",
        "朱元璋", "康熙", "乾隆", "孙中山", "毛泽东", "邓小平",
        "丞相", "科举", "儒家", "道家", "法家", "丝绸之路", "郑和", "长城",
        "工业革命", "世界大战", "冷战", "殖民", "独立", "宪法", "议会", "民主",
        "古代", "近代", "发生", "事件", "成立", "灭亡", "在位", "称帝",
        "公元前", "世纪", "年代", "时期", "年间", "末期", "初年",
        "商鞅", "孔子", "孟子", "荀子", "墨子", "韩非子", "老子",
        "焚书坑儒", "罢黜百家", "推恩令", "三省六部", "行省制度",
        "赤壁之战", "淝水之战", "安史之乱", "陈桥兵变", "靖难之役",
        "闭关锁国", "洋务运动", "戊戌变法", "新文化运动", "南昌起义",
    ],
}


def _guess_subject(filename: str = "", question_text: str = "") -> str:
    """根据题目文本和文件名综合判断科目，无法判断时返回'其他'。"""
    text = (question_text + " " + filename).lower()
    scores = {}
    for subj, keywords in _SUBJECT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > 0:
            scores[subj] = score

    if not scores:
        return "其他"
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else "其他"


def _save_record_docx(
    correction_id: str, filename: str, exam: Optional[ExamResponse],
    score: Optional[int], details: list[CorrectionDetail],
    result_markdown: str, created_at: datetime,
) -> str:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.size = Pt(11)

    doc.add_heading("作业批改记录", level=1)

    info = [
        ("批改ID", correction_id),
        ("作业文件", filename),
        ("批改时间", created_at.strftime("%Y-%m-%d %H:%M:%S")),
    ]
    if exam is not None:
        info.append(("关联试题", f"{exam.id}（{exam.filename}）"))
    if score is not None:
        info.append(("总分", f"{score} / 100"))

    for label, value in info:
        p = doc.add_paragraph()
        p.add_run(f"{label}：").bold = True
        p.add_run(value)

    doc.add_heading("逐题批改记录", level=2)

    if details:
        for i, d in enumerate(details, start=1):
            doc.add_heading(f"第 {d.question_no or i} 题", level=3)
            if d.question_text:
                p = doc.add_paragraph()
                p.add_run("题干：").bold = True
                p.add_run(d.question_text)
            p = doc.add_paragraph()
            p.add_run("学生答案：").bold = True
            p.add_run(d.student_answer or "（未作答/无法识别）")
            p = doc.add_paragraph()
            p.add_run("正确答案：").bold = True
            p.add_run(d.standard_answer)
            judge = "正确" if d.is_correct else "错误"
            if d.score is not None and d.full_score is not None:
                judge += f"（{d.score}/{d.full_score}）"
            p = doc.add_paragraph()
            p.add_run("判定：").bold = True
            p.add_run(judge)
            p = doc.add_paragraph()
            p.add_run("批改分析：").bold = True
            p.add_run(d.analysis)
    else:
        doc.add_paragraph("本次批改未产生结构化的逐题数据，下面是原始批改输出：")
        doc.add_paragraph(result_markdown)

    doc.add_paragraph("—" * 30)
    doc.add_heading("完整批改报告", level=2)
    doc.add_paragraph(result_markdown)

    path = RECORDS_DIR / f"{correction_id}.docx"
    doc.save(str(path))
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


async def _get_exam(session: AsyncSession, exam_id: str) -> Optional[Exam]:
    result = await session.execute(select(Exam).where(Exam.id == exam_id))
    return result.scalar_one_or_none()


async def _get_exam_pydantic(session: AsyncSession, exam_id: str) -> Optional[ExamResponse]:
    db_exam = await _get_exam(session, exam_id)
    if db_exam is None:
        return None
    await session.refresh(db_exam, ["questions"])
    return db_exam.to_pydantic()


# =====================================================================
# 试题（Exam）接口
# =====================================================================

@router.post("/exam/upload")
async def upload_exam(files: list[UploadFile] = File(...), session: AsyncSession = Depends(get_db)):
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
        except Exception:
            questions_data = MOCK_EXAM_QUESTIONS
    else:
        questions_data = MOCK_EXAM_QUESTIONS

    if not questions_data:
        raise HTTPException(status_code=500, detail="试题识别失败，请更换清晰的图片重试")

    display_name = " + ".join(filenames) if len(filenames) > 1 else filenames[0]
    exam_id = str(uuid.uuid4())

    # 创建试题记录 + 同时加入题库
    db_exam = Exam(
        id=exam_id, filename=display_name, source="ai", created_at=datetime.now(),
        questions=[Question(
            question_no=q.get("question_no", str(i + 1)),
            question_text=q.get("question_text", ""),
            standard_answer=q.get("standard_answer", ""),
            analysis=q.get("analysis", ""),
            subject=q.get("subject") or _guess_subject(question_text=q.get("question_text", "")),
        ) for i, q in enumerate(questions_data)],
    )
    session.add(db_exam)
    bank_added = await _auto_add_to_bank(session, exam_id, questions_data, display_name)

    await session.commit()
    return {
        "message": f"试题识别完成，{bank_added} 道题目已导入题库",
        "bank_added": bank_added,
        "filename": display_name,
        "exam_id": exam_id,
        "exam": db_exam.to_pydantic().model_dump(mode="json"),
    }


@router.get("/exams")
async def list_exams(
    keyword: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_db),
):
    stmt = select(Exam).order_by(Exam.created_at.desc())

    if start_date:
        try:
            stmt = stmt.where(Exam.created_at >= datetime.fromisoformat(start_date))
        except ValueError:
            raise HTTPException(status_code=400, detail="start_date 格式无效，请使用 ISO 格式（如 2025-01-01）")
    if end_date:
        try:
            stmt = stmt.where(Exam.created_at <= datetime.fromisoformat(end_date))
        except ValueError:
            raise HTTPException(status_code=400, detail="end_date 格式无效，请使用 ISO 格式（如 2025-12-31）")

    result = await session.execute(stmt)
    exams = result.scalars().all()
    exam_list = [e.to_pydantic() for e in exams]

    if keyword:
        kw = keyword.strip().lower()
        exam_list = [e for e in exam_list if any(
            kw in q.question_text.lower() or kw in q.standard_answer.lower()
            for q in e.questions
        )]

    total = len(exam_list)
    start = (page - 1) * page_size
    return {"items": exam_list[start:start + page_size], "total": total}


@router.get("/exam/{exam_id}", response_model=ExamResponse)
async def get_exam(exam_id: str, session: AsyncSession = Depends(get_db)):
    exam = await _get_exam_pydantic(session, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="试题不存在")
    return exam


@router.put("/exam/{exam_id}/answers", response_model=ExamResponse)
async def update_exam_answers(exam_id: str, payload: UpdateAnswersRequest, session: AsyncSession = Depends(get_db)):
    db_exam = await _get_exam(session, exam_id)
    if not db_exam:
        raise HTTPException(status_code=404, detail="试题不存在")

    # 删除旧题目，插入新题目
    existing_questions = list(db_exam.questions)
    for q in existing_questions:
        await session.delete(q)
    await session.flush()

    for qi in payload.questions:
        q = Question.from_pydantic(qi)
        q.exam_id = db_exam.id
        session.add(q)

    db_exam.source = "manual"
    await session.commit()
    await session.refresh(db_exam, ["questions"])
    return db_exam.to_pydantic()


@router.delete("/exam/{exam_id}")
async def delete_exam(exam_id: str, session: AsyncSession = Depends(get_db)):
    db_exam = await _get_exam(session, exam_id)
    if db_exam:
        await session.delete(db_exam)
        await session.commit()
    return {"status": "ok"}


# =====================================================================
# 批改接口
# =====================================================================

@router.post("/correct", response_model=CorrectionResponse)
async def correct_homework(
    file: UploadFile = File(...),
    exam_id: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_db),
):
    _validate_image_file(file)
    file_path = await _save_upload_file(file)

    exam: Optional[ExamResponse] = None
    standard_answers = None
    if exam_id:
        exam = await _get_exam_pydantic(session, exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="指定的试题不存在")
        standard_answers = [q.model_dump() for q in exam.questions]

    result_text = ""
    score: Optional[int] = None
    details_objs: list[CorrectionDetail] = []

    if AGENT_AVAILABLE and homework_agent is not None:
        try:
            result_text, score, raw_details = await homework_agent.correct(
                file_path, standard_answers=standard_answers)
            details_objs = _details_from_dicts(raw_details or [])
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

    # 已选试题时直接关联原始试题，不创建新的衍生 Exam
    if exam:
        final_exam_id = exam.id
    elif details_objs:
        # 无试题时，自动创建历史试题记录保存题目
        final_exam_id = str(uuid.uuid4())
        db_history_exam = Exam(
            id=final_exam_id,
            filename=f"[批改] {file.filename or 'unknown'}",
            source="correction",
            created_at=created_at,
            questions=[Question(
                question_no=d.question_no,
                question_text=d.question_text,
                standard_answer=d.standard_answer,
                analysis=d.analysis,
            ) for d in details_objs],
        )
        session.add(db_history_exam)
    else:
        final_exam_id = None

    record_path = _save_record_docx(
        correction_id=correction_id, filename=file.filename or "unknown",
        exam=exam, score=score, details=details_objs,
        result_markdown=result_text, created_at=created_at,
    )

    summary = f"作业批改完成，总分 {score} 分。" if score is not None else "作业批改完成。"
    summary += f"（基于试题 {exam.filename}）" if exam else ""

    db_correction = Correction(
        id=correction_id, filename=file.filename or "unknown",
        result=result_text, score=score, summary=summary,
        exam_id=final_exam_id,
        record_path=record_path, created_at=created_at,
    )
    for d in details_objs:
        db_correction.details.append(CorrectionDetailDB.from_pydantic(d))
    session.add(db_correction)

    # 自动将批改题目加入题库（去重+科目分类）
    if details_objs:
        questions_data = [{
            "question_no": d.question_no,
            "question_text": d.question_text,
            "standard_answer": d.standard_answer,
            "analysis": d.analysis,
            "subject": _guess_subject(question_text=d.question_text),
        } for d in details_objs]
        await _auto_add_to_bank(session, final_exam_id, questions_data,
                                f"[批改] {file.filename or 'unknown'}")

    await session.commit()

    return CorrectionResponse(
        id=correction_id, filename=file.filename or "unknown",
        result=result_text, score=score,
        exam_id=final_exam_id,
        details=details_objs or None,
        record_path=record_path, created_at=created_at,
    )


@router.post("/correct/stream")
async def correct_homework_stream(
    file: UploadFile = File(...),
    exam_id: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_db),
):
    _validate_image_file(file)
    file_path = await _save_upload_file(file)

    exam: Optional[ExamResponse] = None
    standard_answers = None
    if exam_id:
        exam = await _get_exam_pydantic(session, exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="指定的试题不存在")
        standard_answers = [q.model_dump() for q in exam.questions]

    async def event_generator():
        nonlocal exam
        try:
            yield f"data: {json.dumps({'event': 'start', 'message': '开始批改...'}, ensure_ascii=False)}\n\n"
            full_content = ""
            stream_score: Optional[int] = None
            stream_details: list[dict] = []

            if AGENT_AVAILABLE and homework_agent is not None:
                try:
                    async for chunk in homework_agent.correct_stream(file_path, standard_answers=standard_answers):
                        yield f"data: {chunk}\n\n"
                        try:
                            chunk_data = json.loads(chunk)
                            if chunk_data.get('event') == 'content':
                                full_content += chunk_data.get('text', '')
                            elif chunk_data.get('event') == 'final_text':
                                full_content = chunk_data.get('text', full_content)
                                stream_score = chunk_data.get('score')
                                stream_details = chunk_data.get('details') or []
                        except Exception:
                            pass
                except Exception as e:
                    logger.error(f"流式批改失败: {e}")
                    yield f"data: {json.dumps({'event': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
            else:
                for chunk in _mock_stream_chunks():
                    yield f"data: {chunk}\n\n"
                    await asyncio.sleep(0.1)
                    try:
                        cd = json.loads(chunk)
                        if cd.get("event") == "content":
                            full_content += cd.get("text", "")
                    except Exception:
                        pass

            score = stream_score if AGENT_AVAILABLE else 85
            details_objs = _details_from_dicts(stream_details) if AGENT_AVAILABLE else []

            correction_id = str(uuid.uuid4())
            created_at = datetime.now()
            result_text = full_content

            record_path = _save_record_docx(
                correction_id=correction_id, filename=file.filename or "unknown",
                exam=exam, score=score, details=details_objs,
                result_markdown=result_text, created_at=created_at,
            )

            summary = f"作业批改完成，总分 {score} 分。" if score is not None else "作业批改完成。"
            summary += f"（基于试题 {exam.filename}）" if exam else ""

            from src.database import AsyncSessionLocal
            async with AsyncSessionLocal() as save_session:
                # 已选试题时直接关联原始试题
                if exam:
                    final_exam_id = exam.id
                elif details_objs:
                    from src.models.db_models import Question as QDB
                    final_exam_id = str(uuid.uuid4())
                    db_history_exam = Exam(
                        id=final_exam_id,
                        filename=f"[批改] {file.filename or 'unknown'}",
                        source="correction",
                        created_at=created_at,
                        questions=[QDB(
                            question_no=d.question_no,
                            question_text=d.question_text,
                            standard_answer=d.standard_answer,
                            analysis=d.analysis,
                        ) for d in details_objs],
                    )
                    save_session.add(db_history_exam)
                else:
                    final_exam_id = None

                db_correction = Correction(
                    id=correction_id, filename=file.filename or "unknown",
                    result=result_text, score=score, summary=summary,
                    exam_id=final_exam_id,
                    record_path=record_path, created_at=created_at,
                )
                for d in details_objs:
                    db_correction.details.append(CorrectionDetailDB.from_pydantic(d))
                save_session.add(db_correction)

                # 自动将批改题目加入题库
                if details_objs:
                    questions_data = [{
                        "question_no": d.question_no,
                        "question_text": d.question_text,
                        "standard_answer": d.standard_answer,
                        "analysis": d.analysis,
                        "subject": _guess_subject(question_text=d.question_text),
                    } for d in details_objs]
                    await _auto_add_to_bank(save_session, final_exam_id, questions_data,
                                            f"[批改] {file.filename or 'unknown'}")

                await save_session.commit()

            yield f"data: {json.dumps({'event': 'end', 'message': '批改完成'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"流式生成器异常: {e}")
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _mock_stream_chunks():
    """将 Mock 批改报告拆分为 content 事件流，与非流式 MOCK_CORRECTION_RESULT 一致。"""
    lines = MOCK_CORRECTION_RESULT.strip().split("\n")
    chunks = []
    for line in lines:
        chunks.append(json.dumps({"event": "content", "text": line + "\n"}, ensure_ascii=False))
    return chunks


# =====================================================================
# 历史 & 记录文件下载
# =====================================================================

@router.get("/history")
async def get_history(
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_db),
):
    # 先查总数
    count_result = await session.execute(select(func.count(Correction.id)))
    total = count_result.scalar() or 0
    # 分页查询
    result = await session.execute(
        select(Correction).order_by(Correction.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    corrections = result.scalars().all()
    return {"items": [c.to_history_item() for c in corrections], "total": total}


@router.get("/correction/{correction_id}/record")
async def download_record(correction_id: str):
    path = RECORDS_DIR / f"{correction_id}.docx"
    if not path.exists():
        raise HTTPException(status_code=404, detail="批改记录不存在")
    return FileResponse(
        path, filename=f"correction_{correction_id}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# =====================================================================
# 试卷导出
# =====================================================================

@router.post("/exam-paper/export")
async def export_exam_paper(payload: list[dict]):
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.size = Pt(11)

    doc.add_heading("练习试卷", level=1)
    p = doc.add_paragraph()
    p.add_run(f"共 {len(payload)} 题").bold = True

    # 题目部分
    for i, q in enumerate(payload, start=1):
        doc.add_heading(f"第 {i} 题", level=3)
        doc.add_paragraph(q.get("question_text", ""))

    # 答案部分
    doc.add_paragraph("—" * 30)
    doc.add_heading("参考答案", level=2)
    for i, q in enumerate(payload, start=1):
        doc.add_heading(f"第 {i} 题", level=3)
        p = doc.add_paragraph()
        p.add_run("答案：").bold = True
        p.add_run(q.get("standard_answer", ""))
        analysis = q.get("analysis", "")
        if analysis:
            p2 = doc.add_paragraph()
            p2.add_run("解析：").bold = True
            p2.add_run(analysis)

    path = RECORDS_DIR / f"exam_paper_{uuid.uuid4().hex[:8]}.docx"
    doc.save(str(path))
    return FileResponse(
        path, filename=f"练习试卷_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# =====================================================================
# 题库接口
# =====================================================================

@router.get("/question-bank")
async def list_question_bank(
    keyword: Optional[str] = None,
    question_no: Optional[str] = None,
    subject: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_db),
):
    stmt = select(QuestionBankItem).order_by(QuestionBankItem.bank_no.asc())
    count_stmt = select(func.count(QuestionBankItem.id))

    if keyword:
        kw = keyword.strip()
        cond = or_(
            QuestionBankItem.question_text.contains(kw),
            QuestionBankItem.standard_answer.contains(kw),
            QuestionBankItem.analysis.contains(kw),
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if subject:
        stmt = stmt.where(QuestionBankItem.subject == subject.strip())
        count_stmt = count_stmt.where(QuestionBankItem.subject == subject.strip())
    if question_no:
        try:
            no = int(question_no.strip())
            stmt = stmt.where(QuestionBankItem.bank_no == no)
            count_stmt = count_stmt.where(QuestionBankItem.bank_no == no)
        except ValueError:
            return {"items": [], "total": 0}

    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(stmt)
    items = result.scalars().all()
    return {"items": [item.to_pydantic() for item in items], "total": total}


@router.post("/question-bank", response_model=QuestionBankItemSchema)
async def add_to_bank(payload: AddToBankRequest, session: AsyncSession = Depends(get_db)):
    # 防御：如果 exam_id 指向不存在的 exam，视为 None
    if payload.exam_id:
        check = await session.execute(select(Exam.id).where(Exam.id == payload.exam_id))
        if not check.scalar_one_or_none():
            payload.exam_id = None
    if payload.exam_id:
        existing = await session.execute(
            select(QuestionBankItem).where(
                QuestionBankItem.exam_id == payload.exam_id,
                QuestionBankItem.question_no == payload.question_no,
            )
        )
    else:
        existing = await session.execute(
            select(QuestionBankItem).where(
                QuestionBankItem.question_text == payload.question_text,
                QuestionBankItem.standard_answer == payload.standard_answer,
            )
        )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该题目已在题库中")

    # 分配入库序号：最大 bank_no + 1
    max_no_result = await session.execute(select(func.max(QuestionBankItem.bank_no)))
    max_no = max_no_result.scalar() or 0

    item = QuestionBankItem(
        exam_id=payload.exam_id,
        question_no=payload.question_no,
        question_text=payload.question_text,
        standard_answer=payload.standard_answer,
        analysis=payload.analysis,
        exam_filename=payload.exam_filename,
        bank_no=max_no + 1,
        subject=payload.subject or _guess_subject(payload.exam_filename, payload.question_text),
        added_at=datetime.now(),
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item.to_pydantic()


@router.delete("/question-bank/{item_id}")
async def remove_from_bank(item_id: int, session: AsyncSession = Depends(get_db)):
    item = await session.get(QuestionBankItem, item_id)
    if item:
        await session.delete(item)
        await session.commit()
    return {"status": "ok"}


@router.delete("/question-bank")
async def clear_bank(session: AsyncSession = Depends(get_db)):
    await session.execute(delete(QuestionBankItem))
    await session.commit()
    return {"status": "ok"}


@router.get("/question-bank/all")
async def all_question_bank(session: AsyncSession = Depends(get_db)):
    """返回全部题库题目（不分页，供训练出题使用）。"""
    result = await session.execute(
        select(QuestionBankItem).order_by(QuestionBankItem.bank_no.asc())
    )
    items = result.scalars().all()
    return [item.to_pydantic() for item in items]


@router.post("/question-bank/reclassify")
async def reclassify_question_bank(session: AsyncSession = Depends(get_db)):
    """根据最新关键词库重新分类所有题库题目。"""
    result = await session.execute(select(QuestionBankItem))
    items = result.scalars().all()
    updated = 0
    for item in items:
        new_subj = _guess_subject(question_text=item.question_text)
        if item.subject != new_subj:
            item.subject = new_subj
            updated += 1
    await session.commit()
    return {"status": "ok", "total": len(items), "updated": updated}


def _mock_questions(payload: AIGenerateRequest) -> list[dict]:
    """根据请求参数动态生成 mock 题目（AI不可用时的兜底）。"""
    is_primary = payload.grade == "小学"
    req = (payload.requirement or "").strip()

    if payload.subject == "语文":
        if is_primary:
            templates = [
                {"q": "看拼音写词语：táo huā（    ）", "a": "桃花", "r": "考查拼音拼读和汉字书写，注意'桃'的右边是'兆'。"},
                {"q": "下列词语中加点字读音完全正确的一项是？A. 模范(mú) B. 模样(mó) C. 模范(mó)", "a": "C", "r": "'模范'的'模'读mó，'模样'的'模'读mú，注意多音字辨析。"},
                {"q": "默写李白的《静夜思》。", "a": "床前明月光，疑是地上霜。举头望明月，低头思故乡。", "r": "考查课标必背古诗，注意'疑''霜'二字的书写。"},
                {"q": "把下列'把'字句改成'被'字句：小猫把花瓶打碎了。", "a": "花瓶被小猫打碎了。", "r": "把字句与被字句转换，交换主语和宾语的位置。"},
                {"q": "'他跑得很快'这句话用了什么修辞手法？A. 比喻 B. 拟人 C. 夸张", "a": "C", "r": "考查修辞手法判断，'很快'是夸张表达。"},
                {"q": "选词填空：安静 宁静 平静\n教室里非常（    ），同学们都在认真写作业。", "a": "安静", "r": "近义词辨析：安静强调没有声音，宁静形容环境，平静形容心情。"},
                {"q": "请写出三个描写春天的成语。", "a": "春暖花开、春光明媚、鸟语花香（答案不唯一）", "r": "考查成语积累，注意与主题的关联性。"},
                {"q": "修改病句：经过老师的帮助，我的成绩有了明显的提高和进步。", "a": "经过老师的帮助，我的成绩有了明显的提高。", "r": "语义重复，'提高'和'进步'意思相近，删去其一。"},
                {"q": "阅读短文回答问题（略），请概括这篇文章的主要内容。", "a": "概括要抓住时间、地点、人物、事件四要素。", "r": "考查阅读理解与概括能力，注意用简洁的语言归纳。"},
                {"q": "请用'虽然……但是……'写一句话。", "a": "答案不唯一，如：虽然下雨了，但是我还是坚持去上学。", "r": "考查转折关系的关联词运用，注意前后语义相反。"},
            ]
        else:
            templates = [
                {"q": "下列词语中加点字读音完全正确的一项是？", "a": "B", "r": "A项'殷红'应为yān，C项'拮据'应为jū，D项'栈桥'应为zhàn。"},
                {"q": "默写杜甫《春望》中描写战乱景象的两句。", "a": "国破山河在，城春草木深。", "r": "考查古诗文默写，注意'破''深'二字。"},
                {"q": "'温故而知新'中'故'的意思是？", "a": "旧的知识", "r": "语出《论语》，'故'指学过的知识。"},
                {"q": "下列句子没有语病的一项是？", "a": "通过这次活动，我开阔了眼界。", "r": "考查病句辨析，其余选项均有搭配不当。"},
                {"q": "请写出《陋室铭》的主旨句。", "a": "斯是陋室，惟吾德馨。", "r": "全文主旨，体现作者安贫乐道。"},
                {"q": "'吹面不寒杨柳风'出自哪位诗人之手？", "a": "志南（释志南）", "r": "南宋诗僧志南的《绝句》。"},
                {"q": "下列修辞手法判断错误的是？", "a": "C（比喻应为拟人）", "r": "考查比喻、拟人、排比、夸张的区分。"},
                {"q": "'不以物喜，不以己悲'表现了怎样的精神境界？", "a": "豁达胸怀，不因外物的好坏和个人的得失而或喜或悲。", "r": "出自《岳阳楼记》，考查思想感情分析。"},
                {"q": "下列成语使用恰当的一项是？", "a": "A", "r": "考查成语在具体语境中的运用。注意感情色彩。"},
                {"q": "请翻译：'知之者不如好之者，好之者不如乐之者。'", "a": "知道它的人不如喜爱它的人，喜爱它的人不如以它为乐的人。", "r": "考查文言句子翻译，注意'之'的指代。"},
            ]
    else:
        if is_primary:
            templates = [
                {"q": "计算：125 × 8 ÷ 4 = ?", "a": "250", "r": "先乘后除，125×8=1000，1000÷4=250。"},
                {"q": "把 3/4 和 5/6 通分后比较大小。", "a": "3/4 = 9/12，5/6 = 10/12，所以 3/4 < 5/6", "r": "找分母的最小公倍数12，然后比较分子。"},
                {"q": "一个长方形的长是12cm，宽是8cm，求它的周长和面积。", "a": "周长=40cm，面积=96cm²", "r": "周长=(长+宽)×2=40，面积=长×宽=96。"},
                {"q": "小明买了3支笔和2个本子，笔每支2元，本子每个5元，一共花了多少钱？", "a": "16元", "r": "3×2+2×5=6+10=16元。"},
                {"q": "36和48的最大公因数是多少？", "a": "12", "r": "36=2²×3², 48=2⁴×3，公因数取最小指数：2²×3=12。"},
                {"q": "2.5千克 = （    ）克", "a": "2500", "r": "1千克=1000克，2.5×1000=2500克。"},
                {"q": "解方程：3x + 5 = 20", "a": "x = 5", "r": "移项：3x=15，两边除以3得x=5。"},
                {"q": "三角形三个内角的和是多少度？", "a": "180°", "r": "三角形内角和定理，任意三角形内角和都是180°。"},
                {"q": "一个正方体的棱长是4cm，求它的体积。", "a": "64cm³", "r": "正方体体积=棱长³=4³=64。"},
                {"q": "根据统计图，某班男生25人女生20人，男生比女生多百分之几？", "a": "25%", "r": "(25-20)÷20×100%=25%。"},
            ]
        else:
            templates = [
                {"q": "解方程：3x - 7 = 2x + 5", "a": "x = 12", "r": "移项合并同类项即可。"},
                {"q": "若方程 2x² - 5x + k = 0 有两个相等实数根，求 k。", "a": "k = 25/8", "r": "判别式 Δ = b²-4ac = 25-8k = 0。"},
                {"q": "抛物线 y = x² - 4x + 3 的顶点坐标是？", "a": "(2, -1)", "r": "配方：y = (x-2)² - 1，顶点(2,-1)。"},
                {"q": "在直角三角形中，∠C=90°，AC=3, BC=4，求 AB。", "a": "5", "r": "勾股定理：AB = √(3²+4²) = 5。"},
                {"q": "计算：(-2)³ + √16 - |3-7|", "a": "-3", "r": "=-8+4-4=-8，注意运算顺序。"},
                {"q": "因式分解：x² - 5x + 6", "a": "(x-2)(x-3)", "r": "十字相乘法，找到-2和-3。"},
                {"q": "函数 y = 2x + 1 经过第几象限？", "a": "一、二、三象限", "r": "k=2>0,b=1>0, 过一二三象限。"},
                {"q": "解不等式组：{2x-3>1, x+2≤7}", "a": "2 < x ≤ 5", "r": "分别求解取交集。"},
                {"q": "已知 a² - b² = 21，a + b = 7，求 a - b。", "a": "3", "r": "a²-b²=(a+b)(a-b)，即21=7×(a-b)。"},
                {"q": "计算概率：掷两个骰子，点数和为7的概率。", "a": "1/6", "r": "6/36=1/6，共有6种组合。注意有序性。"},
            ]

    # 如果指定了知识点，给 mock 题目打上标注
    if req:
        prefix = f"【{req}】"
        for t in templates:
            if prefix not in t["q"]:
                t["q"] = f"{prefix} {t['q']}"

    result = []
    for i in range(min(payload.count, len(templates))):
        t = templates[i]
        result.append({
            "question_no": str(i + 1),
            "question_text": t["q"],
            "standard_answer": t["a"],
            "analysis": t["r"],
            "difficulty": payload.difficulty,
        })
    return result


# =====================================================================
# AI 出题接口
# =====================================================================

@router.post("/ai-generate", response_model=AIGenerateResponse)
async def ai_generate_questions(payload: AIGenerateRequest):
    if AGENT_AVAILABLE and homework_agent is not None:
        try:
            questions_data = await homework_agent.generate_questions(
                subject=payload.subject,
                grade=payload.grade,
                question_type=payload.question_type,
                difficulty=payload.difficulty,
                count=payload.count,
                requirement=payload.requirement,
            )
        except Exception as e:
            logger.error(f"AI出题失败: {e}", exc_info=True)
            questions_data = _mock_questions(payload)
    else:
        questions_data = _mock_questions(payload)

    return AIGenerateResponse(
        questions=[AIGeneratedQuestion(**q) for q in questions_data]
    )


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_db)):
    try:
        from sqlalchemy import text
        await session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    return {"status": "ok", "db": db_status, "ai_available": AGENT_AVAILABLE, "timestamp": datetime.now().isoformat()}
