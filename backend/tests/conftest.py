import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base, get_db
from app.llm.client import get_llm_client
from app.main import app
from app.storage import get_backup_storage_dependency
from app.storage.local import LocalStorage
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
def client(db_session, tmp_path, monkeypatch):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # No test may require a real Ollama (SPEC.md §9.1). Endpoints that need
    # specific canned responses override this again themselves.
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient([])
    # SPEC.md §9.1: LocalStorage (real filesystem, via tmp_path) is used in
    # all tests — never a real Azure account. /api/health still resolves
    # storage via this dependency (unchanged); /api/backup's own endpoints
    # construct storage per-request (routers/backup.py, to support picking
    # local vs. azure per call), reading local_backup_dir from get_settings()
    # directly, so that's monkeypatched to the same tmp_path here too.
    app.dependency_overrides[get_backup_storage_dependency] = lambda: LocalStorage(str(tmp_path))
    monkeypatch.setattr("app.routers.backup.get_settings", lambda: Settings(local_backup_dir=str(tmp_path)))
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
