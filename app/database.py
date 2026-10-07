"""Database engine and session lifecycle helpers."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.models import Base


def create_db_engine(database_url: str) -> Engine:
    options: dict[str, object] = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            options["poolclass"] = StaticPool
    return create_engine(database_url, **options)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Build the engine on first use so importing this module has no side effects.

    The result is cached, so it outlives ``get_settings.cache_clear()``; a process
    that changes settings at runtime keeps the engine it already built.
    """

    return create_db_engine(get_settings().database_url)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


@contextmanager
def open_session(
    factory: sessionmaker[Session] | None = None,
) -> Generator[Session, None, None]:
    """Yield a session that is closed on exit without an implicit commit.

    Callers commit explicitly, so a failed operation can roll back and still exit
    the block without persisting partial work.
    """

    with (factory or get_session_factory())() as session:
        yield session


def init_db(db_engine: Engine | None = None) -> None:
    Base.metadata.create_all(bind=db_engine or get_engine())


def get_db() -> Generator[Session, None, None]:
    with open_session() as session:
        yield session
