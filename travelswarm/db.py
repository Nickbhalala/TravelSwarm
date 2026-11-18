"""PostgreSQL persistence (SQLite works for tests and quick local runs)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, create_engine, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .models import Itinerary, TripRequest, TripStatus, TripView


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TripRow(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    itinerary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


def make_engine(url: str) -> Engine:
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


class TripRepository:
    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    @classmethod
    def from_url(cls, url: str, create_schema: bool = True) -> TripRepository:
        engine = make_engine(url)
        if create_schema:
            Base.metadata.create_all(engine)
        return cls(engine)

    def create(self, request: TripRequest) -> TripView:
        row = TripRow(
            id=str(uuid.uuid4()),
            status=TripStatus.QUEUED,
            request=request.model_dump(mode="json"),
        )
        with self._sessions.begin() as s:
            s.add(row)
        return _view(row)

    def get(self, trip_id: str) -> TripView | None:
        with self._sessions() as s:
            row = s.get(TripRow, trip_id)
            return _view(row) if row else None

    def claim(self, trip_id: str, attempt: int) -> bool:
        """Atomically move a queued trip to PLANNING. False if another worker has it or it's done.

        This makes redelivered messages safe: only one worker plans a trip at a time.
        """
        with self._sessions.begin() as s:
            result = s.execute(
                update(TripRow)
                .where(TripRow.id == trip_id, TripRow.status == TripStatus.QUEUED)
                .values(status=TripStatus.PLANNING, attempts=attempt, updated_at=_now())
            )
            return result.rowcount == 1

    def complete(self, trip_id: str, itinerary: Itinerary) -> None:
        self._set(
            trip_id, status=TripStatus.DONE, itinerary=itinerary.model_dump(mode="json"), error=None
        )

    def requeue(self, trip_id: str, error: str) -> None:
        self._set(trip_id, status=TripStatus.QUEUED, error=error)

    def fail(self, trip_id: str, error: str) -> None:
        self._set(trip_id, status=TripStatus.FAILED, error=error)

    def list_recent(self, limit: int = 20) -> list[TripView]:
        with self._sessions() as s:
            rows = s.scalars(select(TripRow).order_by(TripRow.created_at.desc()).limit(limit))
            return [_view(r) for r in rows]

    def _set(self, trip_id: str, **values: Any) -> None:
        with self._sessions.begin() as s:
            s.execute(
                update(TripRow).where(TripRow.id == trip_id).values(updated_at=_now(), **values)
            )


def _view(row: TripRow) -> TripView:
    return TripView(
        id=row.id,
        status=TripStatus(row.status),
        request=TripRequest.model_validate(row.request),
        itinerary=Itinerary.model_validate(row.itinerary) if row.itinerary else None,
        attempts=row.attempts or 0,
        error=row.error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
