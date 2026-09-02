from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.public_access import SESSION_HEADER, decode_session, encode_session
from app.services import studio_store as store
from app.studio_models import ProjectInput, RunInput
from uuid import uuid4


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SCIENCE_POSTER_DATA_DIR", str(tmp_path))


def payload(topic: str) -> dict:
    return {"topic": topic, "audience": "普通公众", "sources": [], "auto_sources": True}


def test_signed_anonymous_session_rejects_tampering():
    secret = "s" * 32
    session_id = "a" * 32
    encoded = encode_session(session_id, secret)
    assert decode_session(encoded, secret) == session_id
    assert decode_session(encoded[:-1] + ("0" if encoded[-1] != "0" else "1"), secret) is None
    assert decode_session("not-a-session", secret) is None


def test_public_clients_automatically_receive_isolated_project_lists(monkeypatch):
    from app import main, studio_routes
    configured = replace(settings, public_access_enabled=True, public_session_secret="s" * 32)
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(studio_routes, "settings", configured)
    with TestClient(app) as first, TestClient(app) as second:
        created_first = first.post("/api/studio/projects", json=payload("第一位用户的问题"))
        created_second = second.post("/api/studio/projects", json=payload("第二位用户的问题"))
        assert created_first.status_code == created_second.status_code == 201
        first_id = created_first.json()["id"]
        assert [p["topic"] for p in first.get("/api/studio/projects").json()] == ["第一位用户的问题"]
        assert [p["topic"] for p in second.get("/api/studio/projects").json()] == ["第二位用户的问题"]
        assert second.get(f"/api/studio/projects/{first_id}").status_code == 404
        cookie = created_first.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie


def test_signed_header_preserves_cross_origin_session(monkeypatch):
    from app import main, studio_routes
    configured = replace(settings, public_access_enabled=True, public_session_secret="h" * 32)
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(studio_routes, "settings", configured)
    with TestClient(app) as first:
        created = first.post("/api/studio/projects", json=payload("跨域页面的问题"))
        token = created.headers[SESSION_HEADER]
    with TestClient(app) as separate_browser_request:
        listed = separate_browser_request.get("/api/studio/projects", headers={SESSION_HEADER: token})
        assert [project["topic"] for project in listed.json()] == ["跨域页面的问题"]
        assert listed.headers[SESSION_HEADER] == token


def test_signed_query_preserves_session_for_media_links(monkeypatch):
    from app import main, studio_routes
    configured = replace(settings, public_access_enabled=True, public_session_secret="m" * 32)
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(studio_routes, "settings", configured)
    with TestClient(app) as first:
        created = first.post("/api/studio/projects", json=payload("媒体链接的问题"))
        token = created.headers[SESSION_HEADER]
        project_id = created.json()["id"]
    with TestClient(app) as separate_browser_request:
        response = separate_browser_request.get(
            f"/api/studio/projects/{project_id}?_scivis_session={token}"
        )
        assert response.status_code == 200


def test_public_project_quota_is_transparent_and_atomic(monkeypatch):
    from app import main, studio_routes
    configured = replace(settings, public_access_enabled=True, public_session_secret="q" * 32,
                         public_usage_limits_enabled=True, public_projects_per_day=1)
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(studio_routes, "settings", configured)
    with TestClient(app) as client:
        assert client.post("/api/studio/projects", json=payload("第一次创建" )).status_code == 201
        blocked = client.post("/api/studio/projects", json=payload("第二次创建"))
        assert blocked.status_code == 429
        assert "已有项目和视频不会丢失" in blocked.json()["detail"]
        assert len(store.list_projects()) == 1


def test_zero_public_quota_disables_usage_counter(monkeypatch):
    from app import main, studio_routes
    configured = replace(settings, public_access_enabled=True, public_session_secret="u" * 32,
                         public_usage_limits_enabled=False, public_projects_per_day=1,
                         public_runs_per_hour=1, public_media_per_hour=1)
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(studio_routes, "settings", configured)
    with TestClient(app) as client:
        assert client.post("/api/studio/projects", json=payload("不限次数项目一")).status_code == 201
        assert client.post("/api/studio/projects", json=payload("不限次数项目二")).status_code == 201
        assert len(store.list_projects()) == 2


def test_run_quota_and_request_reservation_are_one_transaction():
    project = store.create_project(ProjectInput(
        topic="透明额度原子测试", audience="普通公众", auto_sources=True))
    first = RunInput(request_id=uuid4(), expected_version=0)
    quota = ("session", "run", "2026-09-02T12", 1)
    assert store.reserve(project["id"], first, quota)
    assert not store.reserve(project["id"], first, quota)  # idempotent retry does not consume twice
    store.stage(first.request_id, "done", "succeeded")
    with pytest.raises(store.PublicQuotaExceeded):
        store.reserve(project["id"], RunInput(request_id=uuid4(), expected_version=0), quota)
    assert len(store.get_project(project["id"])["runs"]) == 1


def test_public_release_closes_legacy_paid_endpoints(monkeypatch):
    from app import main, studio_routes
    configured = replace(settings, public_access_enabled=True, public_session_secret="l" * 32)
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(studio_routes, "settings", configured)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/config/public").status_code == 200
        assert client.get("/api/studio/projects").status_code == 200
        blocked = client.post("/api/posters/plan", json={})
        assert blocked.status_code == 404
        assert blocked.json()["detail"] == "该旧版接口不在公开版本中"


def test_production_release_fails_closed_without_operator_only_settings(tmp_path):
    configured = replace(settings, app_env="production", mock_ai=False, dashscope_api_key="test-only",
                         public_access_enabled=False, runtime_data_dir=str(tmp_path))
    with pytest.raises(RuntimeError, match="PUBLIC_ACCESS_ENABLED"):
        configured.validate_for_public_release()

    configured = replace(configured, public_access_enabled=True, public_session_secret="short")
    with pytest.raises(RuntimeError, match="32"):
        configured.validate_for_public_release()

    configured = replace(configured, public_session_secret="x" * 32,
                         public_max_active_jobs=1, public_max_queued_jobs=4)
    configured.validate_for_public_release()
