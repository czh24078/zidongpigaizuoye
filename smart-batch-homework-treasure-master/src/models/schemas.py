from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class QuestionItem(BaseModel):
    """试题中的一道题及其标准答案。"""
    question_no: str                       # 题号，如 "1"、"第一大题-1"
    question_text: str                     # 题干
    standard_answer: str                   # 标准答案
    analysis: Optional[str] = None         # 解题分析（可选）


class ExamResponse(BaseModel):
    """试题对象。"""
    id: str
    filename: str
    questions: List[QuestionItem]
    source: str = "ai"                     # ai / manual，标注标准答案来源
    created_at: datetime


class UpdateAnswersRequest(BaseModel):
    """用户手动更新标准答案的请求体。"""
    questions: List[QuestionItem]


class CorrectionDetail(BaseModel):
    """单题批改详情。"""
    question_no: str
    question_text: str
    student_answer: str
    standard_answer: str
    is_correct: bool
    score: Optional[float] = None          # 本题得分
    full_score: Optional[float] = None     # 本题满分
    analysis: str                          # 批改分析


class CorrectionResponse(BaseModel):
    id: str
    filename: str
    result: str                            # Markdown 格式的批改结果
    score: Optional[int] = None
    exam_id: Optional[str] = None
    details: Optional[List[CorrectionDetail]] = None
    record_path: Optional[str] = None      # 记录文件相对路径
    created_at: datetime


class HistoryItem(BaseModel):
    id: str
    filename: str
    score: Optional[int] = None
    summary: str
    result: Optional[str] = None
    exam_id: Optional[str] = None
    details: Optional[List[CorrectionDetail]] = None
    record_path: Optional[str] = None
    created_at: datetime


class QuestionBankItemSchema(BaseModel):
    """题库中的一道题目。"""
    id: int
    exam_id: Optional[str] = None
    question_no: str
    question_text: str
    standard_answer: str
    analysis: Optional[str] = None
    exam_filename: str
    bank_no: Optional[int] = None
    added_at: datetime


class AddToBankRequest(BaseModel):
    """添加到题库的请求体。"""
    exam_id: Optional[str] = None
    question_no: str
    question_text: str
    standard_answer: str
    analysis: Optional[str] = None
    exam_filename: str


class AIGenerateRequest(BaseModel):
    """AI出题请求体。"""
    subject: str = "数学"                      # 科目
    grade: str = "初中"                        # 年级
    question_type: str = "混合"                # 题型：单选/多选/填空/解答/混合
    difficulty: str = "中等"                   # 难度：简单/中等/困难
    count: int = 5                             # 题目数量
    requirement: Optional[str] = None          # 额外要求/知识点


class AIGeneratedQuestion(BaseModel):
    """AI生成的一道题目。"""
    question_no: str
    question_text: str
    standard_answer: str
    analysis: Optional[str] = None
    difficulty: Optional[str] = None


class AIGenerateResponse(BaseModel):
    """AI出题响应。"""
    questions: List[AIGeneratedQuestion]
