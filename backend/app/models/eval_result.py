from __future__ import annotations
from datetime import datetime
from sqlalchemy import ForeignKey, Text, Integer, String, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db_types import JSONVariant as JSONB

from app.db import Base


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("eval_runs.id", ondelete="CASCADE"))
    test_case_id: Mapped[int] = mapped_column(ForeignKey("test_cases.id"))
    query: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_chunks: Mapped[list] = mapped_column(JSONB, default=list)
    scores: Mapped[dict] = mapped_column(JSONB, nullable=False)
    failure_category: Mapped[str] = mapped_column(
        String(40), nullable=False, default="none", server_default="none"
    )
    root_cause: Mapped[str] = mapped_column(Text, nullable=False, default="none", server_default="none")
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    run: Mapped["EvalRun"] = relationship(back_populates="results")
    test_case: Mapped["TestCase"] = relationship()
