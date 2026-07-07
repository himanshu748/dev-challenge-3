import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from app.schemas.hireiq import (
    CandidateState,
    JobState,
    OfferState,
    RuntimeLogEntry,
    RuntimeState,
)


PIPELINE_STAGES = ("Applied", "Screening", "Interview", "Offer")
LOG_LIMIT = 200
OFFER_LIMIT = 100


class RuntimeStore:
    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self._lock = Lock()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self._write(RuntimeState())

    def snapshot(self) -> RuntimeState:
        with self._lock:
            return self._read()

    def update_workspace(self, **updates: object) -> RuntimeState:
        with self._lock:
            state = self._read()
            merged = state.workspace.model_copy(
                update={
                    **updates,
                    "setup_complete": True,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            state.workspace = merged
            self._write(state)
            return state

    def upsert_job(
        self,
        *,
        title: str,
        department: str,
        headcount: int,
        jd: str,
        highlights: Optional[dict[str, Any]] = None,
        status: str = "Open",
    ) -> JobState:
        with self._lock:
            state = self._read()
            job = JobState(
                title=title,
                department=department,
                headcount=headcount,
                status=status,
                jd=jd,
                highlights=highlights or {},
                updated_at=datetime.now(timezone.utc),
            )
            state.jobs[self._job_key(title)] = job
            self._write(state)
            return job

    def find_job(self, *, title: str) -> Optional[JobState]:
        with self._lock:
            state = self._read()
            return state.jobs.get(self._job_key(title))

    def upsert_candidate(
        self,
        *,
        name: str,
        email: str,
        job_title: str,
        stage: str,
        score: Optional[int] = None,
        resume_summary: str = "",
        ai_notes: str = "",
    ) -> RuntimeState:
        with self._lock:
            state = self._read()
            key = self._candidate_key(name=name, email=email, job_title=job_title)
            state.candidates[key] = CandidateState(
                name=name,
                email=email,
                job_title=job_title,
                stage=stage,
                score=score,
                resume_summary=resume_summary,
                ai_notes=ai_notes,
                updated_at=datetime.now(timezone.utc),
            )
            self._write(state)
            return state

    def record_offer(
        self,
        *,
        candidate_name: str,
        job_title: str,
        title: str,
        letter_body: str,
        key_terms: list[str],
        salary: str,
        start_date: str,
    ) -> OfferState:
        with self._lock:
            state = self._read()
            offer = OfferState(
                candidate_name=candidate_name,
                job_title=job_title,
                title=title,
                letter_body=letter_body,
                key_terms=key_terms,
                salary=salary,
                start_date=start_date,
                created_at=datetime.now(timezone.utc),
            )
            state.offers.append(offer)
            state.offers = state.offers[-OFFER_LIMIT:]
            self._write(state)
            return offer

    def append_log(self, *, operation: str, message: str) -> RuntimeLogEntry:
        with self._lock:
            state = self._read()
            entry = RuntimeLogEntry(
                timestamp=datetime.now(timezone.utc),
                operation=operation,
                message=message,
                pipeline_counts=self.pipeline_counts(state),
            )
            state.logs.append(entry)
            state.logs = state.logs[-LOG_LIMIT:]
            self._write(state)
            return entry

    def find_candidate(self, *, name: str, job_title: str) -> Optional[CandidateState]:
        with self._lock:
            state = self._read()
            key = self._find_candidate_key(state=state, name=name, job_title=job_title)
            if not key:
                return None
            return state.candidates.get(key)

    @staticmethod
    def pipeline_counts(state: RuntimeState) -> dict[str, int]:
        counts = {stage: 0 for stage in PIPELINE_STAGES}
        for candidate in state.candidates.values():
            if candidate.stage in counts:
                counts[candidate.stage] += 1
        return counts

    @staticmethod
    def _job_key(title: str) -> str:
        return title.strip().lower()

    @staticmethod
    def _candidate_key(*, name: str, email: str, job_title: str) -> str:
        email_or_name = email.strip().lower() or name.strip().lower()
        safe_name = email_or_name.replace(" ", "-")
        return f"{job_title.strip().lower()}::{safe_name}"

    @staticmethod
    def _find_candidate_key(*, state: RuntimeState, name: str, job_title: str) -> Optional[str]:
        normalized_name = name.strip().lower()
        normalized_job_title = job_title.strip().lower()
        for key, candidate in state.candidates.items():
            if candidate.name.strip().lower() == normalized_name and candidate.job_title.strip().lower() == normalized_job_title:
                return key
        return None

    def _read(self) -> RuntimeState:
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        return RuntimeState.model_validate(payload)

    def _write(self, state: RuntimeState) -> None:
        self.state_path.write_text(
            json.dumps(state.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
