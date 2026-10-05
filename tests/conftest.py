"""Shared test fixtures."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from app.database import create_db_engine
from app.models import Base


@pytest.fixture()
def db_session():
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
