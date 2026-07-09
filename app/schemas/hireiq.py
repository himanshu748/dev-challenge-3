from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


PipelineStage = Literal["Applied", "Screening", "Interview", "Offer", "Rejected"]
JobStatus = Literal["Open", "Closed"]


class SetupRequest(BaseModel):
    workspace_name: str = Field(default="HireIQ Recruiting Hub", min_length=3, max_length=120)

    model_config = ConfigDict(str_strip_whitespace=True)


class AddJobRequest(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    department: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=20, max_length=12000)
    headcount: int = Field(default=1, ge=1, le=1000)

    model_config = ConfigDict(str_strip_whitespace=True)


class ScreenCandidateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=320)
    resume_text: str = Field(min_length=40, max_length=30000)
    job_title: str = Field(min_length=2, max_length=160)

    model_config = ConfigDict(str_strip_whitespace=True)


class GenerateOfferRequest(BaseModel):
    candidate_name: str = Field(min_length=2, max_length=160)
    job_title: str = Field(min_length=2, max_length=160)
    salary: str = Field(min_length=2, max_length=120)
    start_date: str = Field(min_length=4, max_length=40)

    model_config = ConfigDict(str_strip_whitespace=True)


class WorkspaceState(BaseModel):
    setup_complete: bool = False
    workspace_name: Optional[str] = None
    updated_at: Optional[datetime] = None


class JobState(BaseModel):
    title: str
    department: str
    headcount: int
    status: JobStatus = "Open"
    jd: str = ""
    highlights: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime


class CandidateState(BaseModel):
    name: str
    email: str
    job_title: str
    stage: PipelineStage
    score: Optional[int] = Field(default=None, ge=1, le=10)
    resume_summary: str = ""
    ai_notes: str = ""
    updated_at: datetime


class OfferState(BaseModel):
    candidate_name: str
    job_title: str
    title: str
    letter_body: str
    key_terms: list[str] = Field(default_factory=list)
    salary: str = ""
    start_date: str = ""
    created_at: datetime


class RuntimeLogEntry(BaseModel):
    timestamp: datetime
    operation: str
    message: str
    pipeline_counts: dict[str, int]


class RuntimeState(BaseModel):
    workspace: WorkspaceState = Field(default_factory=WorkspaceState)
    jobs: dict[str, JobState] = Field(default_factory=dict)
    candidates: dict[str, CandidateState] = Field(default_factory=dict)
    offers: list[OfferState] = Field(default_factory=list)
    logs: list[RuntimeLogEntry] = Field(default_factory=list)


class OperationResponse(BaseModel):
    operation: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    log_output: list[str] = Field(default_factory=list)
    pipeline_counts: dict[str, int] = Field(default_factory=dict)


class LogsResponse(BaseModel):
    logs: list[RuntimeLogEntry]
    pipeline_counts: dict[str, int]
    workspace: WorkspaceState


class CandidatesResponse(BaseModel):
    candidates: list[CandidateState]
    pipeline_counts: dict[str, int]


class JobsResponse(BaseModel):
    jobs: list[JobState]
