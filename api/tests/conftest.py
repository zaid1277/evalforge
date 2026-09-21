"""
Shared test setup.

Tests must never touch the developer's normal database. Instead of the
`DATABASE_URL` the app uses at runtime, tests connect to a separate
database (same server, name with a `_test` suffix) and override FastAPI's
`get_db` dependency to use it. Each test gets a clean set of tables so
tests can't leak state into one another.

One-time local setup: `createdb evalforge_test` (same server as the main
`evalforge` database).
"""

import hashlib
import re

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.database import Base, get_db
from app.main import app
from app.services import duplicate_service, evaluation_service, grounding_service


def _test_database_url() -> str:
    """Swap the configured database name for a dedicated test database."""
    return re.sub(r"/([^/]+)$", r"/\1_test", settings.DATABASE_URL)


test_engine = create_engine(_test_database_url())
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def _clean_test_database():
    """Give every test a fresh, empty set of tables in the test database."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def client():
    return TestClient(app)


def _fast_fake_embed(texts):
    """Deterministic stand-in for the real MiniLM model: identical text
    always produces an identical vector, so identical questions still
    score as exact duplicates -- without ever loading a real model."""
    vectors = [
        np.frombuffer(hashlib.md5(text.encode()).digest(), dtype=np.uint8).astype(np.float64)
        for text in texts
    ]
    return np.array(vectors)


@pytest.fixture(autouse=True)
def _no_real_embedding_model_by_default(monkeypatch):
    """Applies to every test in the suite by default, so generating or
    editing cases never loads the real MiniLM model (slow, and would
    need network access the first time). Tests that need precise control
    over similarity scores (test_duplicate_service.py,
    test_duplicate_integration.py, test_grounding_service.py,
    test_grounding_integration.py, test_evaluation_service.py) override
    this locally with their own monkeypatch.setattr call, which simply
    takes effect afterwards. The real model is only ever exercised by the
    tests explicitly marked `real_model`, which call
    embedding_service.embed_texts directly rather than through here.

    Grounding (M7) needs this just as much as duplicate detection (M6):
    generating even a single answerable case triggers a grounding
    calculation, so without this fake, most of the generation test suite
    would silently start loading the real model too. Evaluation (M9)
    needs it for the same reason -- scoring even one answerable result
    calls embed_texts via services/evaluation_service.py.
    """
    monkeypatch.setattr(duplicate_service, "embed_texts", _fast_fake_embed)
    monkeypatch.setattr(grounding_service, "embed_texts", _fast_fake_embed)
    monkeypatch.setattr(evaluation_service, "embed_texts", _fast_fake_embed)


@pytest.fixture()
def db_session():
    """A direct session against the test database, for tests that need to
    assert on rows (e.g. confirming a cascade delete) or set up state the
    API has no route for (e.g. a pre-M3 source with no chunks)."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
