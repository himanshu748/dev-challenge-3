from __future__ import annotations

import json
import re
from textwrap import dedent
from typing import Any

from app.core.settings import Settings
from app.schemas.hireiq import (
    AddJobRequest,
    CandidatesResponse,
    GenerateOfferRequest,
    JobsResponse,
    LogsResponse,
    OperationResponse,
    ScreenCandidateRequest,
    SetupRequest,
)
from app.services.hf_client import HFService, HireIQError
from app.services.runtime_store import RuntimeStore


# ─── JSON extraction helpers ────────────────────────────────────────────────

JSON_BLOCK_RE = re.compile(r"<hireiq_json>\s*(\{.*?\})\s*</hireiq_json>", re.DOTALL)
FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

HIREIQ_SYSTEM = dedent(
    """
    You are HireIQ, an expert AI recruiting operations assistant.
    Generate structured JSON responses for recruiting workflows.
    Return valid JSON only — no markdown fences, no commentary outside the JSON.
    """
).strip()


def _parse_json(raw: str) -> dict[str, Any]:
    """Extract JSON from model output (tries XML tags, fenced blocks, bare JSON)."""
    # XML-wrapped JSON (backwards compat)
    match = JSON_BLOCK_RE.search(raw)
    if match:
        return json.loads(match.group(1))
    # Fenced code block
    match = FENCED_JSON_RE.search(raw)
    if match:
        return json.loads(match.group(1))
    # Bare JSON
    s, e = raw.find("{"), raw.rfind("}") + 1
    if s != -1 and e > s:
        return json.loads(raw[s:e])
    raise HireIQError(
        "The model response could not be parsed into structured JSON.",
        status_code=502,
    )


# ─── Service ─────────────────────────────────────────────────────────────────


class HireIQService:
    _extract_json = staticmethod(_parse_json)

    def __init__(
        self,
        *,
        settings: Settings,
        hf_client: HFService,
        runtime_store: RuntimeStore,
    ) -> None:
        self.settings = settings
        self.hf_client = hf_client
        self.runtime_store = runtime_store

    async def _generate_json(
        self, prompt: str, *, max_tokens: int
    ) -> dict[str, Any]:
        """Generate structured JSON, retrying once if the model output
        cannot be parsed."""
        raw = await self.hf_client.generate_text(
            HIREIQ_SYSTEM, prompt, max_tokens=max_tokens
        )
        try:
            return _parse_json(raw)
        except (HireIQError, json.JSONDecodeError):
            retry_prompt = (
                f"{prompt}\n\n"
                "Your previous response was not valid JSON. "
                "Respond again with a single valid JSON object and nothing else."
            )
            raw = await self.hf_client.generate_text(
                HIREIQ_SYSTEM, retry_prompt, max_tokens=max_tokens
            )
            return _parse_json(raw)

    # ── Setup Workspace ──────────────────────────────────────────────────

    async def setup_workspace(self, request: SetupRequest) -> OperationResponse:
        """Initialize the local workspace. Instant — no external services."""
        self.runtime_store.update_workspace(workspace_name=request.workspace_name)

        log_output, pipeline_counts = self._record_logs(
            "setup",
            f"[SETUP] Workspace '{request.workspace_name}' initialized.",
        )

        return OperationResponse(
            operation="setup",
            summary=f"Workspace '{request.workspace_name}' is ready. "
            "Add a job to start the pipeline.",
            details={
                "workspace": {
                    "name": request.workspace_name,
                    "storage": "local",
                }
            },
            log_output=log_output,
            pipeline_counts=pipeline_counts,
        )

    # ── Add Job ──────────────────────────────────────────────────────────

    async def add_job(self, request: AddJobRequest) -> OperationResponse:
        self._require_workspace()

        prompt = dedent(
            f"""
            Generate a polished job description JSON for:
            - Title: {request.title}
            - Department: {request.department}
            - Headcount: {request.headcount}
            - Raw description: {request.description}

            JSON format:
            {{
              "summary": "Short summary of the job posting",
              "jd": "Full polished job description text with responsibilities, requirements, and nice-to-haves",
              "highlights": {{
                "responsibilities": ["item1", "item2"],
                "requirements": ["item1", "item2"],
                "nice_to_haves": ["item1", "item2"]
              }}
            }}
            """
        ).strip()

        hf_data = await self._generate_json(prompt, max_tokens=1800)
        jd_text = str(hf_data.get("jd", request.description))
        highlights = hf_data.get("highlights", {})
        if not isinstance(highlights, dict):
            highlights = {}

        job = self.runtime_store.upsert_job(
            title=request.title,
            department=request.department,
            headcount=request.headcount,
            jd=jd_text,
            highlights=highlights,
        )

        log_output, pipeline_counts = self._record_logs(
            "add-job",
            f"[JOB] Opened requisition for {request.title} in {request.department}.",
        )

        return OperationResponse(
            operation="add-job",
            summary=str(hf_data.get("summary", f"Job {request.title} created.")),
            details={
                "job": {
                    "title": job.title,
                    "department": job.department,
                    "status": job.status,
                    "headcount": job.headcount,
                    "jd": job.jd,
                },
                "highlights": highlights,
            },
            log_output=log_output,
            pipeline_counts=pipeline_counts,
        )

    # ── Screen Candidate ─────────────────────────────────────────────────

    async def screen_candidate(
        self, request: ScreenCandidateRequest
    ) -> OperationResponse:
        self._require_workspace()

        job = self.runtime_store.find_job(title=request.job_title)
        job_jd = job.jd if job else ""

        prompt = dedent(
            f"""
            Screen this candidate against a job opening.

            Job Title: {request.job_title}
            Job Description: {job_jd or "Not available"}

            Candidate:
            - Name: {request.name}
            - Email: {request.email}
            - Resume: {request.resume_text}

            Score the candidate from 1 to 10 based on fit.
            Set stage to "Screening" if score >= 6, otherwise "Rejected".

            JSON format:
            {{
              "summary": "Short screening summary",
              "score": 7,
              "stage": "Screening",
              "resume_summary": "Brief resume summary for the database",
              "ai_notes": "Detailed screening notes",
              "screening": {{
                "strengths": ["strength1", "strength2"],
                "gaps": ["gap1"],
                "recommendation": "Recommend for next round because..."
              }}
            }}
            """
        ).strip()

        hf_data = await self._generate_json(prompt, max_tokens=2200)

        score = self._coerce_score(hf_data.get("score"))
        stage = "Screening" if score >= 6 else "Rejected"
        resume_summary = str(hf_data.get("resume_summary", ""))[:2000]
        ai_notes = str(hf_data.get("ai_notes", ""))[:2000]

        self.runtime_store.upsert_candidate(
            name=request.name,
            email=request.email,
            job_title=request.job_title,
            stage=stage,
            score=score,
            resume_summary=resume_summary,
            ai_notes=ai_notes,
        )

        log_output, pipeline_counts = self._record_logs(
            "screen-candidate",
            f"[SCREEN] {request.name} scored {score}/10 for {request.job_title} "
            f"and moved to {stage}.",
        )

        return OperationResponse(
            operation="screen-candidate",
            summary=str(
                hf_data.get(
                    "summary",
                    f"{request.name} screened for {request.job_title}.",
                )
            ),
            details={
                "candidate": {
                    "name": request.name,
                    "email": request.email,
                    "job_title": request.job_title,
                    "score": score,
                    "stage": stage,
                },
                "screening": hf_data.get("screening", {}),
            },
            log_output=log_output,
            pipeline_counts=pipeline_counts,
        )

    # ── Generate Offer ───────────────────────────────────────────────────

    async def generate_offer(
        self, request: GenerateOfferRequest
    ) -> OperationResponse:
        self._require_workspace()

        prompt = dedent(
            f"""
            Generate a professional offer letter for:
            - Candidate: {request.candidate_name}
            - Job Title: {request.job_title}
            - Salary: {request.salary}
            - Start Date: {request.start_date}

            JSON format:
            {{
              "summary": "Short summary of the offer",
              "offer_title": "Offer - {request.candidate_name} - {request.job_title}",
              "letter_body": "Full professional offer letter text",
              "key_terms": [
                "Position: {request.job_title}",
                "Salary: {request.salary}",
                "Start Date: {request.start_date}"
              ]
            }}
            """
        ).strip()

        hf_data = await self._generate_json(prompt, max_tokens=2200)

        offer_title = str(
            hf_data.get(
                "offer_title",
                f"Offer - {request.candidate_name} - {request.job_title}",
            )
        )
        letter_body = str(hf_data.get("letter_body", ""))
        key_terms = [str(term) for term in hf_data.get("key_terms", [])]

        offer = self.runtime_store.record_offer(
            candidate_name=request.candidate_name,
            job_title=request.job_title,
            title=offer_title,
            letter_body=letter_body,
            key_terms=key_terms,
            salary=request.salary,
            start_date=request.start_date,
        )

        existing = self.runtime_store.find_candidate(
            name=request.candidate_name, job_title=request.job_title
        )
        self.runtime_store.upsert_candidate(
            name=request.candidate_name,
            email=existing.email if existing else "",
            job_title=request.job_title,
            stage="Offer",
            score=existing.score if existing else None,
            resume_summary=existing.resume_summary if existing else "",
            ai_notes=existing.ai_notes if existing else "",
        )

        log_output, pipeline_counts = self._record_logs(
            "generate-offer",
            f"[OFFER] Generated offer for {request.candidate_name} "
            f"({request.job_title}).",
        )

        return OperationResponse(
            operation="generate-offer",
            summary=str(
                hf_data.get(
                    "summary",
                    f"Offer created for {request.candidate_name}.",
                )
            ),
            details={
                "candidate": {
                    "name": request.candidate_name,
                    "job_title": request.job_title,
                    "stage": "Offer",
                },
                "offer": {
                    "title": offer.title,
                    "letter_body": offer.letter_body,
                    "key_terms": offer.key_terms,
                    "salary": offer.salary,
                    "start_date": offer.start_date,
                },
            },
            log_output=log_output,
            pipeline_counts=pipeline_counts,
        )

    # ── Reads ────────────────────────────────────────────────────────────

    def get_logs(self) -> LogsResponse:
        snapshot = self.runtime_store.snapshot()
        return LogsResponse(
            logs=snapshot.logs,
            pipeline_counts=self.runtime_store.pipeline_counts(snapshot),
            workspace=snapshot.workspace,
        )

    def get_candidates(self) -> CandidatesResponse:
        snapshot = self.runtime_store.snapshot()
        candidates = sorted(
            snapshot.candidates.values(),
            key=lambda c: c.updated_at,
            reverse=True,
        )
        return CandidatesResponse(
            candidates=candidates,
            pipeline_counts=self.runtime_store.pipeline_counts(snapshot),
        )

    def get_jobs(self) -> JobsResponse:
        snapshot = self.runtime_store.snapshot()
        jobs = sorted(
            snapshot.jobs.values(),
            key=lambda j: j.updated_at,
            reverse=True,
        )
        return JobsResponse(jobs=jobs)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _require_workspace(self):
        snapshot = self.runtime_store.snapshot()
        if not snapshot.workspace.setup_complete:
            raise HireIQError(
                "Run /api/setup first to initialize the HireIQ workspace.",
                status_code=409,
            )
        return snapshot.workspace

    def _record_logs(
        self, operation: str, action_message: str
    ) -> tuple[list[str], dict[str, int]]:
        event_entry = self.runtime_store.append_log(
            operation=operation, message=action_message
        )
        pipeline_message = (
            f"[PIPELINE] {json.dumps(event_entry.pipeline_counts, sort_keys=True)}"
        )
        pipeline_entry = self.runtime_store.append_log(
            operation=operation, message=pipeline_message
        )
        return (
            [event_entry.message, pipeline_entry.message],
            pipeline_entry.pipeline_counts,
        )

    @staticmethod
    def _coerce_score(value: Any) -> int:
        try:
            score = int(value)
        except (TypeError, ValueError) as exc:
            raise HireIQError(
                "The candidate score returned by the model was not a valid integer.",
                status_code=502,
            ) from exc
        if score < 1 or score > 10:
            raise HireIQError(
                "The candidate score returned by the model was outside the 1-10 range.",
                status_code=502,
            )
        return score
