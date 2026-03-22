from __future__ import annotations

import json
import re
from textwrap import dedent
from typing import Any, Optional

from app.core.settings import Settings
from app.schemas.hireiq import (
    AddJobRequest,
    GenerateOfferRequest,
    LogsResponse,
    OperationResponse,
    ScreenCandidateRequest,
    SetupRequest,
)
from app.services.hf_mcp import (
    HFMCPService,
    HireIQError,
    _bullet,
    _heading,
    _para,
    _rt,
)
from app.services.runtime_store import RuntimeStore


# ─── JSON extraction helpers ────────────────────────────────────────────────

JSON_BLOCK_RE = re.compile(r"<hireiq_json>\s*(\{.*?\})\s*</hireiq_json>", re.DOTALL)
FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

# System prompt for content generation (no Notion ops — that's handled by MCP)
HIREIQ_SYSTEM = dedent(
    """
    You are HireIQ, an expert AI recruiting operations assistant.
    Generate structured JSON responses for recruiting workflows.
    Return valid JSON only — no markdown fences, no commentary outside the JSON.
    Do not attempt any Notion operations — just generate the requested content.
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
        extra={"model_output": raw},
    )


# ─── Service ─────────────────────────────────────────────────────────────────


class HireIQService:
    def __init__(
        self,
        *,
        settings: Settings,
        hf_client: HFMCPService,
        runtime_store: RuntimeStore,
    ) -> None:
        self.settings = settings
        self.hf_client = hf_client
        self.runtime_store = runtime_store

    # ── Setup Workspace ──────────────────────────────────────────────────

    async def setup_workspace(self, request: SetupRequest) -> OperationResponse:
        parent_id = self.settings.notion_parent_page_id

        # Step 1: HF generates workspace description
        prompt = dedent(
            f"""
            Generate a JSON description for an HR recruiting workspace called
            "{request.workspace_name}".
            Include a brief summary and any notes about the workspace structure.

            JSON format:
            {{
              "summary": "One-line summary of the workspace",
              "notes": ["note about structure", "note about databases"]
            }}
            """
        ).strip()

        raw = await self.hf_client.generate_text(
            HIREIQ_SYSTEM, prompt, max_tokens=800
        )
        hf_data = _parse_json(raw)

        # Step 2: Create everything in Notion via MCP
        async with self.hf_client.notion_session() as mcp:
            # Hub page
            hub_children = [
                _heading(request.workspace_name),
                _para(hf_data.get("summary", "HireIQ Recruiting Hub")),
                _heading("Databases", level=2),
                _bullet("📋 Jobs — Open positions and job descriptions"),
                _bullet("👤 Candidates — Candidate tracking and screening"),
                _bullet("📅 Interviews — Interview scheduling and feedback"),
            ]
            hub = await self.hf_client.mcp_create_page(
                mcp, parent_id, request.workspace_name, hub_children
            )
            hub_id = hub["id"]
            hub_url = hub.get("url", "")

            # Jobs database
            jobs_db = await self.hf_client.mcp_create_database(
                mcp,
                hub_id,
                "📋 Jobs",
                {
                    "Title": {"title": {}},
                    "Department": {"rich_text": {}},
                    "Status": {
                        "select": {
                            "options": [
                                {"name": "Open", "color": "green"},
                                {"name": "Closed", "color": "red"},
                            ]
                        }
                    },
                    "Headcount": {"number": {}},
                    "JD": {"rich_text": {}},
                },
            )
            jobs_db_id = jobs_db["id"]
            jobs_db_url = jobs_db.get("url", "")

            # Candidates database
            candidates_db = await self.hf_client.mcp_create_database(
                mcp,
                hub_id,
                "👤 Candidates",
                {
                    "Name": {"title": {}},
                    "Role Applied": {"rich_text": {}},
                    "Email": {"email": {}},
                    "Resume Summary": {"rich_text": {}},
                    "Stage": {
                        "select": {
                            "options": [
                                {"name": "Applied", "color": "default"},
                                {"name": "Screening", "color": "blue"},
                                {"name": "Interview", "color": "yellow"},
                                {"name": "Offer", "color": "green"},
                                {"name": "Rejected", "color": "red"},
                            ]
                        }
                    },
                    "Score": {"number": {}},
                    "AI Notes": {"rich_text": {}},
                },
            )
            candidates_db_id = candidates_db["id"]
            candidates_db_url = candidates_db.get("url", "")

            # Interviews database (relation → Candidates)
            interviews_db = await self.hf_client.mcp_create_database(
                mcp,
                hub_id,
                "📅 Interviews",
                {
                    "Title": {"title": {}},
                    "Candidate": {
                        "relation": {
                            "database_id": candidates_db_id,
                            "single_property": {},
                        }
                    },
                    "Date": {"date": {}},
                    "Interviewer": {"rich_text": {}},
                    "Format": {"rich_text": {}},
                    "Feedback": {"rich_text": {}},
                    "Decision": {
                        "select": {
                            "options": [
                                {"name": "Pass", "color": "green"},
                                {"name": "Fail", "color": "red"},
                                {"name": "Pending", "color": "yellow"},
                            ]
                        }
                    },
                },
            )
            interviews_db_url = interviews_db.get("url", "")
            interviews_db_id = interviews_db["id"]

        # Step 3: Persist workspace info
        notion_urls = {
            "hub_page": hub_url,
            "jobs_database": jobs_db_url,
            "candidates_database": candidates_db_url,
            "interviews_database": interviews_db_url,
        }

        self.runtime_store.update_workspace(
            workspace_name=request.workspace_name,
            hub_page_url=hub_url,
            hub_page_id=hub_id,
            jobs_database_url=jobs_db_url,
            jobs_database_id=jobs_db_id,
            candidates_database_url=candidates_db_url,
            candidates_database_id=candidates_db_id,
            interviews_database_url=interviews_db_url,
            interviews_database_id=interviews_db_id,
        )

        log_output, pipeline_counts = self._record_logs(
            "setup",
            f"[SETUP] HireIQ workspace scaffolded in Notion. Hub: {hub_url}",
        )

        return OperationResponse(
            operation="setup",
            summary=str(hf_data.get("summary", "HireIQ workspace created.")),
            notion_urls=notion_urls,
            details={"notes": hf_data.get("notes", [])},
            log_output=log_output,
            pipeline_counts=pipeline_counts,
        )

    # ── Add Job ──────────────────────────────────────────────────────────

    async def add_job(self, request: AddJobRequest) -> OperationResponse:
        workspace = self._require_workspace_with_ids()

        # Step 1: HF generates a polished JD
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

        raw = await self.hf_client.generate_text(
            HIREIQ_SYSTEM, prompt, max_tokens=1800
        )
        hf_data = _parse_json(raw)
        jd_text = hf_data.get("jd", request.description)

        # Step 2: Write row to Jobs database via MCP
        async with self.hf_client.notion_session() as mcp:
            job_row = await self.hf_client.mcp_add_database_row(
                mcp,
                workspace.jobs_database_id,
                {
                    "Title": {"title": _rt(request.title)},
                    "Department": {"rich_text": _rt(request.department)},
                    "Status": {"select": {"name": "Open"}},
                    "Headcount": {"number": request.headcount},
                    "JD": {"rich_text": _rt(jd_text[:2000])},
                },
            )
            job_url = job_row.get("url", "")

        notion_urls = {
            "job": job_url,
            "jobs_database": workspace.jobs_database_url or "",
        }
        notion_urls = {k: v for k, v in notion_urls.items() if v}
        if "job" not in notion_urls:
            raise HireIQError(
                "The job was created, but its Notion URL was not returned.",
                status_code=502,
                extra={"model_output": hf_data},
            )

        log_output, pipeline_counts = self._record_logs(
            "add-job",
            f"[JOB] Opened requisition for {request.title} in {request.department}.",
        )

        return OperationResponse(
            operation="add-job",
            summary=str(hf_data.get("summary", f"Job {request.title} created.")),
            notion_urls=notion_urls,
            details={
                "job": {
                    "title": request.title,
                    "department": request.department,
                    "status": "Open",
                    "headcount": request.headcount,
                    "url": job_url,
                },
                "highlights": hf_data.get("highlights", {}),
            },
            log_output=log_output,
            pipeline_counts=pipeline_counts,
        )

    # ── Screen Candidate ─────────────────────────────────────────────────

    async def screen_candidate(
        self, request: ScreenCandidateRequest
    ) -> OperationResponse:
        workspace = self._require_workspace_with_ids()

        async with self.hf_client.notion_session() as mcp:
            # Step 1: Read the matching job from Notion
            job_rows = await self.hf_client.mcp_query_database(
                mcp,
                workspace.jobs_database_id,
                {
                    "property": "Title",
                    "title": {"equals": request.job_title},
                },
            )
            job_jd = ""
            if job_rows:
                job_props = job_rows[0].get("properties", {})
                jd_prop = job_props.get("JD", {})
                if jd_prop.get("rich_text"):
                    job_jd = "".join(
                        t.get("plain_text", "") for t in jd_prop["rich_text"]
                    )

            # Step 2: HF generates screening evaluation
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

            raw = await self.hf_client.generate_text(
                HIREIQ_SYSTEM, prompt, max_tokens=2200
            )
            hf_data = _parse_json(raw)

            score = self._coerce_score(hf_data.get("score"))
            stage = "Screening" if score >= 6 else "Rejected"
            resume_summary = hf_data.get("resume_summary", "")[:2000]
            ai_notes = hf_data.get("ai_notes", "")[:2000]

            # Step 3: Write candidate to Notion via MCP
            candidate_row = await self.hf_client.mcp_add_database_row(
                mcp,
                workspace.candidates_database_id,
                {
                    "Name": {"title": _rt(request.name)},
                    "Role Applied": {"rich_text": _rt(request.job_title)},
                    "Email": {"email": request.email},
                    "Resume Summary": {"rich_text": _rt(resume_summary)},
                    "Stage": {"select": {"name": stage}},
                    "Score": {"number": score},
                    "AI Notes": {"rich_text": _rt(ai_notes)},
                },
            )
            candidate_url = candidate_row.get("url", "")

        if not candidate_url:
            raise HireIQError(
                "Candidate was screened, but their Notion URL was not returned.",
                status_code=502,
                extra={"model_output": hf_data},
            )

        self.runtime_store.upsert_candidate(
            name=request.name,
            email=request.email,
            job_title=request.job_title,
            stage=stage,
            notion_url=candidate_url,
            score=score,
        )

        log_output, pipeline_counts = self._record_logs(
            "screen-candidate",
            f"[SCREEN] {request.name} scored {score}/10 for {request.job_title} "
            f"and moved to {stage}.",
        )

        notion_urls = {
            "candidate": candidate_url,
            "candidates_database": workspace.candidates_database_url or "",
        }
        notion_urls = {k: v for k, v in notion_urls.items() if v}

        return OperationResponse(
            operation="screen-candidate",
            summary=str(
                hf_data.get(
                    "summary",
                    f"{request.name} screened for {request.job_title}.",
                )
            ),
            notion_urls=notion_urls,
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
        workspace = self._require_workspace_with_ids()

        async with self.hf_client.notion_session() as mcp:
            # Step 1: HF generates offer letter content
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

            raw = await self.hf_client.generate_text(
                HIREIQ_SYSTEM, prompt, max_tokens=2200
            )
            hf_data = _parse_json(raw)

            offer_title = hf_data.get(
                "offer_title",
                f"Offer - {request.candidate_name} - {request.job_title}",
            )
            letter_body = hf_data.get("letter_body", "")
            key_terms = hf_data.get("key_terms", [])

            # Step 2: Build and create offer page in Notion
            offer_blocks = [
                _heading(offer_title),
                _heading("Offer Details", level=3),
            ]
            for term in key_terms:
                offer_blocks.append(_bullet(str(term)))
            offer_blocks.append(_heading("Offer Letter", level=3))
            for paragraph in letter_body.split("\n\n"):
                paragraph = paragraph.strip()
                if paragraph:
                    offer_blocks.append(_para(paragraph))

            offer_page = await self.hf_client.mcp_create_page(
                mcp,
                workspace.hub_page_id,
                offer_title,
                offer_blocks,
            )
            offer_url = offer_page.get("url", "")

            # Step 3: Find candidate in Notion and update stage to "Offer"
            candidate_url = ""
            candidate_rows = await self.hf_client.mcp_query_database(
                mcp,
                workspace.candidates_database_id,
                {
                    "property": "Name",
                    "title": {"equals": request.candidate_name},
                },
            )
            if candidate_rows:
                candidate_page_id = candidate_rows[0]["id"]
                candidate_url = candidate_rows[0].get("url", "")
                await self.hf_client.mcp_patch_page(
                    mcp,
                    candidate_page_id,
                    {"Stage": {"select": {"name": "Offer"}}},
                )

        if not offer_url:
            raise HireIQError(
                "Offer was generated, but Notion URLs were missing.",
                status_code=502,
                extra={"model_output": hf_data},
            )

        # Update runtime store
        existing = self.runtime_store.find_candidate(
            name=request.candidate_name, job_title=request.job_title
        )
        self.runtime_store.upsert_candidate(
            name=request.candidate_name,
            email=existing.email if existing else "",
            job_title=request.job_title,
            stage="Offer",
            notion_url=candidate_url or (existing.notion_url if existing else None),
            score=existing.score if existing else None,
        )

        log_output, pipeline_counts = self._record_logs(
            "generate-offer",
            f"[OFFER] Generated offer for {request.candidate_name} "
            f"({request.job_title}).",
        )

        notion_urls = {"offer_letter": offer_url}
        if candidate_url:
            notion_urls["candidate"] = candidate_url

        return OperationResponse(
            operation="generate-offer",
            summary=str(
                hf_data.get(
                    "summary",
                    f"Offer created for {request.candidate_name}.",
                )
            ),
            notion_urls=notion_urls,
            details={
                "candidate": {
                    "name": request.candidate_name,
                    "job_title": request.job_title,
                    "stage": "Offer",
                    "url": candidate_url,
                },
                "offer": {
                    "title": offer_title,
                    "url": offer_url,
                    "salary": request.salary,
                    "start_date": request.start_date,
                },
            },
            log_output=log_output,
            pipeline_counts=pipeline_counts,
        )

    # ── Logs ─────────────────────────────────────────────────────────────

    def get_logs(self) -> LogsResponse:
        snapshot = self.runtime_store.snapshot()
        return LogsResponse(
            logs=snapshot.logs,
            pipeline_counts=self.runtime_store.pipeline_counts(snapshot),
            workspace=snapshot.workspace,
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    def _require_workspace(self):
        snapshot = self.runtime_store.snapshot()
        if not snapshot.workspace.setup_complete:
            raise HireIQError(
                "Run /api/setup first so HireIQ knows where the Notion workspace lives.",
                status_code=409,
            )
        return snapshot.workspace

    def _require_workspace_with_ids(self):
        ws = self._require_workspace()
        if (
            not ws.hub_page_id
            or not ws.jobs_database_id
            or not ws.candidates_database_id
        ):
            raise HireIQError(
                "Workspace database IDs are missing. Please run /api/setup again.",
                status_code=409,
            )
        return ws

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
