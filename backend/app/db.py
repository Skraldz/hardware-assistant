"""Database engine, session factory, and the per-request session dependency."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base all ORM models inherit from."""

    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for one request, closing it afterwards.

    Yields:
        Session: A SQLAlchemy session scoped to the request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
