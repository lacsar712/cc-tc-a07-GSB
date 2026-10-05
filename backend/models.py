import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54401/tunnelconv")
engine = create_engine(DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BlastingWindow(Base):
    """掌子面爆破封锁窗：某断面 [starts_at, ends_at] 时段内测缝报送整体锁死。"""

    __tablename__ = "blasting_windows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BlockadeLog(Base):
    """真实拒收留痕：每次落在爆破窗内被挡住的报送都写一条。"""

    __tablename__ = "blockade_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    window_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    blocked_by: Mapped[str] = mapped_column(String, nullable=False)
    server_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)


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


def window_dict(row: BlastingWindow) -> dict:
    return {
        "id": row.id,
        "chainage": row.chainage,
        "starts_at": row.starts_at.isoformat() if row.starts_at else None,
        "ends_at": row.ends_at.isoformat() if row.ends_at else None,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def blockade_dict(row: BlockadeLog) -> dict:
    return {
        "id": row.id,
        "window_id": row.window_id,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "blocked_by": row.blocked_by,
        "server_time": row.server_time.isoformat() if row.server_time else None,
        "reason": row.reason,
    }
