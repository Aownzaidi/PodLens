import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import get_db
from app.main import app
from app.models.database_models import Base


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_analyze_rejects_invalid_url(client):
    response = client.post("/api/analyze", json={"url": "not a youtube url"})
    assert response.status_code == 422  # pydantic validation error


def test_status_returns_404_for_unknown_analysis(client):
    response = client.get("/api/analysis/9999/status")
    assert response.status_code == 404


def test_dashboard_returns_404_for_unknown_analysis(client):
    response = client.get("/api/analysis/9999/dashboard")
    assert response.status_code == 404


def test_report_returns_404_for_unknown_analysis(client):
    response = client.get("/api/analysis/9999/report")
    assert response.status_code == 404


def test_comments_returns_404_for_unknown_analysis(client):
    response = client.get("/api/analysis/9999/comments")
    assert response.status_code == 404


def test_analyze_without_youtube_key_returns_503(client, monkeypatch):
    from app import config

    config.get_settings.cache_clear()
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    response = client.post(
        "/api/analyze", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    )
    assert response.status_code == 503
    config.get_settings.cache_clear()


def test_comments_filter_query_validation(client):
    response = client.get("/api/analysis/1/comments?spam=invalid_value")
    assert response.status_code == 422
