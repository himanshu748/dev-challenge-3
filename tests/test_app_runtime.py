import asyncio

from fastapi.testclient import TestClient

import app.main as main_module
from app.core.settings import Settings
from app.main import app
from app.schemas.hireiq import AddJobRequest, ScreenCandidateRequest, SetupRequest
from app.services.hf_client import HFService, HireIQError
from app.services.hireiq import HireIQService, _parse_json
from app.services.runtime_store import RuntimeStore


class FakeHFClient:
    """Deterministic stand-in for HFService in workflow tests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    async def generate_text(self, system, user_msg, *, max_tokens=4096):
        self.prompts.append(user_msg)
        return self.responses.pop(0)


def make_service(tmp_path, hf_client=None):
    settings = Settings(_env_file=None, runtime_state_path=tmp_path / "runtime.json")
    return HireIQService(
        settings=settings,
        hf_client=hf_client or HFService(settings),
        runtime_store=RuntimeStore(settings.runtime_state_path),
    )


def test_app_imports_and_serves_static_without_tokens(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
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
    assert "model" in health.json()
    assert index.status_code == 200
    assert "HireIQ" in index.text


def test_settings_load_without_provider_secrets(monkeypatch):
    monkeypatch.delenv("HF_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    settings = Settings(_env_file=None)
    assert settings.hf_api_key == ""
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


def test_setup_initializes_local_workspace_without_tokens(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    service = make_service(tmp_path)

    response = asyncio.run(service.setup_workspace(SetupRequest()))

    assert response.operation == "setup"
    assert service.runtime_store.snapshot().workspace.setup_complete is True


def test_job_routes_require_setup_first(tmp_path):
    service = make_service(tmp_path)

    try:
        asyncio.run(
            service.add_job(
                AddJobRequest(
                    title="AI Engineer",
                    department="Engineering",
                    description="Build and ship AI recruiting workflows.",
                )
            )
        )
    except HireIQError as exc:
        assert exc.status_code == 409
        assert "/api/setup" in exc.detail
    else:
        raise AssertionError("Expected missing workspace to raise HireIQError")


def test_ai_routes_report_missing_hf_key(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    service = make_service(tmp_path)
    asyncio.run(service.setup_workspace(SetupRequest()))

    try:
        asyncio.run(
            service.add_job(
                AddJobRequest(
                    title="AI Engineer",
                    department="Engineering",
                    description="Build and ship AI recruiting workflows.",
                )
            )
        )
    except HireIQError as exc:
        assert exc.status_code == 400
        assert "HF_API_KEY" in exc.detail
    else:
        raise AssertionError("Expected missing HF key to raise HireIQError")


def test_add_job_stores_job_locally(tmp_path):
    fake = FakeHFClient(
        [
            '{"summary": "Great role", "jd": "Full JD text", '
            '"highlights": {"requirements": ["Python"]}}'
        ]
    )
    service = make_service(tmp_path, hf_client=fake)
    asyncio.run(service.setup_workspace(SetupRequest()))

    response = asyncio.run(
        service.add_job(
            AddJobRequest(
                title="AI Engineer",
                department="Engineering",
                description="Build and ship AI recruiting workflows.",
            )
        )
    )

    assert response.summary == "Great role"
    stored = service.runtime_store.find_job(title="AI Engineer")
    assert stored is not None
    assert stored.jd == "Full JD text"
    assert service.get_jobs().jobs[0].title == "AI Engineer"


def test_screen_candidate_uses_local_jd_and_stores_candidate(tmp_path):
    fake = FakeHFClient(
        [
            '{"summary": "ok", "jd": "Needs Python and LLM experience", "highlights": {}}',
            '{"summary": "Strong fit", "score": 8, "stage": "Screening", '
            '"resume_summary": "Senior engineer", "ai_notes": "Solid", "screening": {}}',
        ]
    )
    service = make_service(tmp_path, hf_client=fake)
    asyncio.run(service.setup_workspace(SetupRequest()))
    asyncio.run(
        service.add_job(
            AddJobRequest(
                title="AI Engineer",
                department="Engineering",
                description="Build and ship AI recruiting workflows.",
            )
        )
    )

    response = asyncio.run(
        service.screen_candidate(
            ScreenCandidateRequest(
                name="Jane Doe",
                email="jane@example.com",
                job_title="AI Engineer",
                resume_text="Ten years of Python, ML systems, and LLM evaluation work.",
            )
        )
    )

    assert "Needs Python and LLM experience" in fake.prompts[-1]
    assert response.details["candidate"]["score"] == 8
    assert response.pipeline_counts["Screening"] == 1


def test_candidates_endpoint_lists_screened_candidates(tmp_path):
    service = make_service(tmp_path)
    service.runtime_store.upsert_candidate(
        name="Jane Doe",
        email="jane@example.com",
        job_title="Senior AI Engineer",
        stage="Screening",
        score=8,
    )

    response = service.get_candidates()

    assert len(response.candidates) == 1
    assert response.candidates[0].name == "Jane Doe"
    assert response.candidates[0].score == 8
    assert response.pipeline_counts["Screening"] == 1


def test_candidates_route_serves_empty_state_without_tokens(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    test_settings = Settings(
        _env_file=None,
        runtime_state_path=tmp_path / "runtime.json",
    )
    monkeypatch.setattr(main_module, "get_settings", lambda: test_settings)

    with TestClient(app) as client:
        response = client.get("/api/candidates")

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidates"] == []
    assert set(payload["pipeline_counts"]) == {
        "Applied",
        "Screening",
        "Interview",
        "Offer",
    }


def test_json_parse_failure_does_not_expose_raw_model_output():
    try:
        _parse_json("not json and maybe private provider output")
    except HireIQError as exc:
        assert exc.status_code == 502
        assert exc.extra == {}
        assert "private provider output" not in exc.detail
    else:
        raise AssertionError("Expected invalid model output to raise HireIQError")


def test_generate_json_retries_once_on_unparseable_output(tmp_path):
    fake = FakeHFClient(["sorry, no JSON here", '{"summary": "recovered"}'])
    service = make_service(tmp_path, hf_client=fake)

    result = asyncio.run(service._generate_json("prompt", max_tokens=100))

    assert result == {"summary": "recovered"}
    assert len(fake.prompts) == 2
