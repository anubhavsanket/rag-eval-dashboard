from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
_engine_url: Optional[str] = None


def _rebuild() -> None:
    """Create the engine/factory bound to the *current* settings.

    The engine is built lazily (and rebuilt when DATABASE_URL changes) so
    tests can monkeypatch the environment without a stale import-time engine
    leaking into the wrong database.
    """
    global _engine, _session_factory, _engine_url
    settings = get_settings()
    _engine_url = settings.DATABASE_URL
    _engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def get_engine() -> AsyncEngine:
    global _engine
    url = get_settings().DATABASE_URL
    if _engine is None or _engine_url != url:
        old = _engine
        _rebuild()
        if old is not None:
            old.sync_engine.dispose()
    assert _engine is not None
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise