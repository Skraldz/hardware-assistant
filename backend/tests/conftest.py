import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.llm.client import get_llm_client
from app.main import app
from tests.fixtures.fake_llm import FakeLLMClient


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # No test may require a real Ollama (SPEC.md §9.1). Endpoints that need
    # specific canned responses override this again themselves.
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient([])
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
