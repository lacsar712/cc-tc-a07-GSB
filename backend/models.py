import os
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54401/tunnelconv")
engine = create_engine(DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


class UTCDateTime(TypeDecorator):
    """统一以 UTC 存取；读回保证带时区，避免裸时间与带时区时间混比。"""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    pass


class ConvergenceLog(Base):
    __tablename__ = "convergence_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(timezone=True), nullable=True)


class BlastWindow(Base):
    """掌子面爆破封锁窗：某断面在 [starts_at, ends_at] 内整体锁死测缝报送。"""

    __tablename__ = "blast_windows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class BlastBlock(Base):
    """封锁日志：窗内报送被真实拒收的流水，与拒收动作同事务落库。"""

    __tablename__ = "blast_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blocked_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), nullable=False)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    submitted_by: Mapped[str] = mapped_column(String, nullable=False)
    window_id: Mapped[int | None] = mapped_column(
        ForeignKey("blast_windows.id", ondelete="SET NULL"), nullable=True
    )
    # 命中窗口的时刻快照，窗口事后被解除也不影响日志
    window_start: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    # 客户端自己声称的时间（若有）只留档，绝不参与是否在窗内的判定
    client_clock: Mapped[str | None] = mapped_column(String, nullable=True)


def row_dict(row: ConvergenceLog) -> dict:
    return {
        "id": row.id,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "status": row.status,
        "verdict": row.verdict,
        "reason": row.reason,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }


def window_dict(row: BlastWindow, now: datetime | None = None) -> dict:
    state = "pending"
    if now is not None:
        if row.starts_at <= now <= row.ends_at:
            state = "blocking"
        elif now > row.ends_at:
            state = "ended"
        else:
            state = "pending"
    return {
        "id": row.id,
        "chainage": row.chainage,
        "starts_at": row.starts_at.isoformat() if row.starts_at else None,
        "ends_at": row.ends_at.isoformat() if row.ends_at else None,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "state": state,
    }


def block_dict(row: BlastBlock) -> dict:
    return {
        "id": row.id,
        "blocked_at": row.blocked_at.isoformat() if row.blocked_at else None,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "submitted_by": row.submitted_by,
        "window_id": row.window_id,
        "window_start": row.window_start.isoformat() if row.window_start else None,
        "window_end": row.window_end.isoformat() if row.window_end else None,
        "reason": row.reason,
        "client_clock": row.client_clock,
    }
