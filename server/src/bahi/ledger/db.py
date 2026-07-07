"""Engine/session plumbing. DATABASE_URL decides SQLite (sovereign default)
vs Postgres (deployment) — nothing else in the codebase knows the dialect."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from bahi.config import get_settings
from bahi.ledger.models import Base

_engines: dict[str, Engine] = {}


def get_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    if url not in _engines:
        _engines[url] = create_engine(url)
    return _engines[url]


def init_db(engine: Engine | None = None) -> None:
    """Create tables directly (tests/dev). Deployments run `alembic upgrade head`."""
    Base.metadata.create_all(engine or get_engine())


@contextmanager
def session_scope(database_url: str | None = None) -> Iterator[Session]:
    factory = sessionmaker(bind=get_engine(database_url), expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
