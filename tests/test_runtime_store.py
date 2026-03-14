import json

from app.services.hireiq import HireIQService
from app.services.runtime_store import RuntimeStore


def test_runtime_store_updates_pipeline_counts(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.json")
    store.upsert_candidate(
        name="Ada Lovelace",
        email="ada@example.com",
        job_title="AI Engineer",
        stage="Screening",
        notion_url="https://notion.so/candidate",
        score=8,
    )
    snapshot = store.snapshot()
    assert store.pipeline_counts(snapshot) == {
        "Applied": 0,
        "Screening": 1,
        "Interview": 0,
        "Offer": 0,
    }


def test_json_extraction_requires_hireiq_wrapper():
    parsed = HireIQService._extract_json("<hireiq_json>{\"summary\":\"ok\"}</hireiq_json>")
    assert parsed["summary"] == "ok"


def test_log_storage_round_trips(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.json")
    store.append_log(operation="setup", message="[SETUP] done")
    payload = json.loads((tmp_path / "runtime.json").read_text(encoding="utf-8"))
    assert payload["logs"][0]["message"] == "[SETUP] done"
