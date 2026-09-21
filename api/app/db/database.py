"""
SQLAlchemy engine/session setup for PostgreSQL.

Database models (Project, SourceDocument, etc.) are added in later
milestones. For M0 this module only needs to prove that the app can
connect to PostgreSQL using the configured DATABASE_URL.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# `pool_pre_ping` checks that a pooled connection is still alive before
# handing it out, which avoids confusing errors after the DB restarts.
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class that all future SQLAlchemy models will inherit from."""


def get_db():
    """FastAPI dependency that yields a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
