import asyncio

from fastapi.testclient import TestClient

import app.main as main_module
from app.core.settings import Settings
from app.main import app
from app.services.hf_mcp import HFMCPService, HireIQError
from app.services.hireiq import HireIQService, _parse_json
from app.services.runtime_store import RuntimeStore
from app.schemas.hireiq import SetupRequest


def test_app_imports_and_serves_static_without_tokens(tmp_path, monkeypatch):
    test_settings = Settings(
        _env_file=None,
        runtime_state_path=tmp_path / "runtime.json",
    )
    monkeypatch.setattr(main_module, "get_settings", lambda: test_settings)

    with TestClient(app) as client:
        health = client.get("/api/health")
        index = client.get("/")

    assert health.status_code == 200
    assert health.json()["hf_key"] is False
    assert health.json()["notion_token"] is False
    assert index.status_code == 200
    assert "HireIQ" in index.text


def test_settings_load_without_provider_secrets():
    settings = Settings(_env_file=None)
    assert settings.hf_api_key == ""
    assert settings.notion_token == ""
    assert settings.notion_parent_page_id == ""
    assert "http://127.0.0.1:8000" in settings.cors_origins


def test_cors_is_limited_to_configured_origins():
    with TestClient(app) as client:
        allowed = client.options(
            "/api/health",
            headers={
                "Origin": "http://127.0.0.1:8000",
                "Access-Control-Request-Method": "GET",
            },
        )
        blocked = client.options(
            "/api/health",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:8000"
    assert "access-control-allow-origin" not in blocked.headers


def test_oversized_json_request_is_rejected_before_provider_call():
    with TestClient(app) as client:
        response = client.post(
            "/api/add-job",
            content=b"{}",
            headers={
                "Content-Type": "application/json",
                "Content-Length": "160001",
            },
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "Request body is too large."


def test_provider_routes_report_missing_parent_page(tmp_path):
    settings = Settings(_env_file=None, runtime_state_path=tmp_path / "runtime.json")
    service = HireIQService(
        settings=settings,
        hf_client=HFMCPService(settings),
        runtime_store=RuntimeStore(settings.runtime_state_path),
    )

    try:
        asyncio.run(service.setup_workspace(SetupRequest()))
    except HireIQError as exc:
        assert exc.status_code == 400
        assert "NOTION_PARENT_PAGE_ID" in exc.detail
    else:
        raise AssertionError("Expected missing parent page id to raise HireIQError")


def test_json_parse_failure_does_not_expose_raw_model_output():
    try:
        _parse_json("not json and maybe private provider output")
    except HireIQError as exc:
        assert exc.status_code == 502
        assert exc.extra == {}
        assert "private provider output" not in exc.detail
    else:
        raise AssertionError("Expected invalid model output to raise HireIQError")
