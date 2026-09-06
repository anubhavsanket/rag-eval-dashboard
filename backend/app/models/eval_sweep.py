from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db_types import JSONVariant as JSONB

from app.db import Base


class EvalSweep(Base):
    """A sweep benchmarks multiple RAG configurations against one dataset.

    Each configuration becomes its own EvalRun (linked via ``sweep_id``) so
    every result stays comparable with single-run evaluations. The sweep's
    ``summary`` caches the leaderboard payload computed when all runs finish.
    """

    __tablename__ = "eval_sweeps"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|completed|failed
    run_ids: Mapped[list] = mapped_column(JSONB, default=list)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    runs: Mapped[list["EvalRun"]] = relationship(back_populates="sweep")