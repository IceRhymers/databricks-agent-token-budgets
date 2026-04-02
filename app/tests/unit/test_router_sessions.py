"""Tests for routers/sessions.py — Session mapping endpoint."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import app
from deps import get_db, get_current_user


@pytest.fixture
def test_client(mock_session, admin_identity):
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: admin_identity
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def non_admin_client(mock_session, non_admin_identity):
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: non_admin_identity
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.mark.unit
class TestRegisterSession:
    def test_registers_session_successfully(self, test_client, mock_session):
        response = test_client.post("/api/sessions/register", json={
            "session_id": "sess-abc-123",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["user_email"] == "admin@example.com"
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_non_admin_can_register(self, non_admin_client, mock_session):
        response = non_admin_client.post("/api/sessions/register", json={
            "session_id": "sess-def-456",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["user_email"] == "user@example.com"

    def test_returns_422_when_session_id_missing(self, test_client):
        response = test_client.post("/api/sessions/register", json={})
        assert response.status_code == 422

    def test_returns_401_without_auth(self, mock_session):
        app.dependency_overrides[get_db] = lambda: mock_session
        # No get_current_user override — uses real dep which raises 401
        app.dependency_overrides.pop(get_current_user, None)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/api/sessions/register", json={
            "session_id": "sess-no-auth",
        })
        assert response.status_code == 401

        app.dependency_overrides.clear()

    def test_upsert_executes_insert_on_conflict(self, test_client, mock_session):
        """Verify the upsert statement is executed (ON CONFLICT DO UPDATE)."""
        # Call twice with same session_id — both should succeed
        for _ in range(2):
            response = test_client.post("/api/sessions/register", json={
                "session_id": "sess-duplicate",
            })
            assert response.status_code == 200
        assert mock_session.execute.call_count == 2
        assert mock_session.commit.call_count == 2
