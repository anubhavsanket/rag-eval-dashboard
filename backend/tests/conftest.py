"""Pytest configuration: fresh SQLite DB per test function."""
import os
import tempfile
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db import Base, get_engine, get_session_factory
from app import models  # noqa: F401 — import models so tables are registered


@pytest.fixture(autouse=True, scope="function")
def isolated_db(monkeypatch):
    """Each test gets its own SQLite DB so schemas and state never leak."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{path}")
    # Force get_settings to re-read the environment on next call
    from app.config import get_settings
    get_settings.cache_clear()
    # Rebuild the module-level engine to point at the new URL
    import app.db as db_mod
    db_mod._engine = None
    db_mod._session_factory = None
    db_mod._engine_url = None
    yield
    try:
        os.remove(path)
    except OSError:
        pass
    get_settings.cache_clear()


@pytest.fixture
async def db_session() -> AsyncSession:
    """Yield a fresh async session bound to the isolated SQLite DB."""
    from app.config import get_settings
    from app.db import get_engine, get_session_factory

    # Ensure engine picks up the monkeypatched URL
    settings = get_settings()
    eng = create_async_engine(settings.DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    session = factory()
    yield session
    await session.rollback()
    await session.close()
    await eng.dispose()


@pytest.fixture
def mock_judge(monkeypatch):
    """Replace the live judge with a deterministic MockJudge."""
    from app.services.judge import MockJudge
    from app.services import evaluation_engine as engine_mod

    monkeypatch.setattr(engine_mod, "MockJudge", MockJudge)
    return MockJudge()