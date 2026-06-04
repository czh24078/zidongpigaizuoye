from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── ORM Models ──────────────────────────────────────────────────────────────

class Exam(Base):
    __tablename__ = "exams"

    id = Column(String(36), primary_key=True)
    filename = Column(String(500), nullable=False)
    source = Column(String(20), nullable=False, default="ai")
    created_at = Column(DateTime, nullable=False)

    questions = relationship("Question", back_populates="exam",
                             cascade="all, delete-orphan", lazy="selectin")
    corrections = relationship("Correction", back_populates="exam",
                               foreign_keys="Correction.exam_id", lazy="selectin")
    bank_items = relationship("QuestionBankItem", back_populates="exam", lazy="selectin",
                              foreign_keys="QuestionBankItem.exam_id")

    def to_pydantic(self) -> "ExamResponse":
        from src.models.schemas import ExamResponse
        return ExamResponse(
            id=self.id,
            filename=self.filename,
            questions=[q.to_pydantic() for q in self.questions] if self.questions else [],
            source=self.source,
            created_at=self.created_at,
        )


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(String(36), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    question_no = Column(String(50), nullable=False)
    question_text = Column(Text, nullable=False)
    standard_answer = Column(Text, nullable=False)
    options = Column(Text, nullable=True)
    analysis = Column(Text, nullable=True)
    subject = Column(String(20), nullable=False, default="其他")

    exam = relationship("Exam", back_populates="questions")

    @classmethod
    def from_pydantic(cls, data: "QuestionItem") -> "Question":
        return cls(
            question_no=data.question_no,
            question_text=data.question_text,
            standard_answer=data.standard_answer,
            options=data.options,
            analysis=data.analysis,
            subject=data.subject,
        )

    def to_pydantic(self) -> "QuestionItem":
        from src.models.schemas import QuestionItem
        return QuestionItem(
            question_no=self.question_no,
            question_text=self.question_text,
            standard_answer=self.standard_answer,
            options=self.options,
            analysis=self.analysis,
            subject=self.subject,
        )


class Correction(Base):
    __tablename__ = "corrections"

    id = Column(String(36), primary_key=True)
    filename = Column(String(500), nullable=False)
    result = Column(Text, nullable=True)
    score = Column(Integer, nullable=True)
    summary = Column(String(500), nullable=True)
    exam_id = Column(String(36), ForeignKey("exams.id", ondelete="SET NULL"), nullable=True)
    record_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False)

    exam = relationship("Exam", back_populates="corrections",
                        foreign_keys=[exam_id])
    details = relationship("CorrectionDetail", back_populates="correction",
                           cascade="all, delete-orphan", lazy="selectin")

    def to_pydantic(self) -> "CorrectionResponse":
        from src.models.schemas import CorrectionResponse
        return CorrectionResponse(
            id=self.id,
            filename=self.filename,
            result=self.result or "",
            score=self.score,
            exam_id=self.exam_id,
            details=[d.to_pydantic() for d in self.details] if self.details else None,
            record_path=self.record_path,
            created_at=self.created_at,
        )

    def to_history_item(self) -> "HistoryItem":
        from src.models.schemas import HistoryItem
        return HistoryItem(
            id=self.id,
            filename=self.filename,
            score=self.score,
            summary=self.summary or "",
            result=self.result,
            exam_id=self.exam_id,
            details=[d.to_pydantic() for d in self.details] if self.details else None,
            record_path=self.record_path,
            created_at=self.created_at,
        )


class CorrectionDetail(Base):
    __tablename__ = "correction_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    correction_id = Column(String(36), ForeignKey("corrections.id", ondelete="CASCADE"), nullable=False)
    question_no = Column(String(50), nullable=False)
    question_text = Column(Text, nullable=False)
    student_answer = Column(Text, nullable=False)
    standard_answer = Column(Text, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    score = Column(Float, nullable=True)
    full_score = Column(Float, nullable=True)
    analysis = Column(Text, nullable=False)

    correction = relationship("Correction", back_populates="details")

    @classmethod
    def from_pydantic(cls, data: "CorrectionDetail") -> "CorrectionDetail":
        return cls(
            question_no=data.question_no,
            question_text=data.question_text,
            student_answer=data.student_answer,
            standard_answer=data.standard_answer,
            is_correct=data.is_correct,
            score=data.score,
            full_score=data.full_score,
            analysis=data.analysis,
        )

    def to_pydantic(self) -> "CorrectionDetail":
        from src.models.schemas import CorrectionDetail
        return CorrectionDetail(
            question_no=self.question_no,
            question_text=self.question_text,
            student_answer=self.student_answer,
            standard_answer=self.standard_answer,
            is_correct=self.is_correct,
            score=self.score,
            full_score=self.full_score,
            analysis=self.analysis,
        )


class QuestionBankItem(Base):
    __tablename__ = "question_bank"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(String(36), ForeignKey("exams.id", ondelete="SET NULL"), nullable=True)
    question_no = Column(String(50), nullable=False)
    question_text = Column(Text, nullable=False)
    standard_answer = Column(Text, nullable=False)
    analysis = Column(Text, nullable=True)
    exam_filename = Column(String(500), nullable=False)
    bank_no = Column(Integer, nullable=True)
    subject = Column(String(20), nullable=False, default="其他")
    added_at = Column(DateTime, nullable=False, default=datetime.now)

    exam = relationship("Exam", back_populates="bank_items")

    def to_pydantic(self) -> "QuestionBankItemSchema":
        from src.models.schemas import QuestionBankItemSchema
        return QuestionBankItemSchema(
            id=self.id,
            exam_id=self.exam_id,
            question_no=self.question_no,
            question_text=self.question_text,
            standard_answer=self.standard_answer,
            analysis=self.analysis,
            exam_filename=self.exam_filename,
            bank_no=self.bank_no,
            subject=self.subject,
            added_at=self.added_at,
        )
