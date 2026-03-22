from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


PipelineStage = Literal["Applied", "Screening", "Interview", "Offer", "Rejected"]


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
    hub_page_url: Optional[str] = None
    hub_page_id: Optional[str] = None
    jobs_database_url: Optional[str] = None
    jobs_database_id: Optional[str] = None
    candidates_database_url: Optional[str] = None
    candidates_database_id: Optional[str] = None
    interviews_database_url: Optional[str] = None
    interviews_database_id: Optional[str] = None
    updated_at: Optional[datetime] = None


class CandidateState(BaseModel):
    name: str
    email: str
    job_title: str
    stage: PipelineStage
    notion_url: Optional[str] = None
    score: Optional[int] = Field(default=None, ge=1, le=10)
    updated_at: datetime


class RuntimeLogEntry(BaseModel):
    timestamp: datetime
    operation: str
    message: str
    pipeline_counts: dict[str, int]


class RuntimeState(BaseModel):
    workspace: WorkspaceState = Field(default_factory=WorkspaceState)
    candidates: dict[str, CandidateState] = Field(default_factory=dict)
    logs: list[RuntimeLogEntry] = Field(default_factory=list)


class OperationResponse(BaseModel):
    operation: str
    summary: str
    notion_urls: dict[str, str] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)
    log_output: list[str] = Field(default_factory=list)
    pipeline_counts: dict[str, int] = Field(default_factory=dict)


class LogsResponse(BaseModel):
    logs: list[RuntimeLogEntry]
    pipeline_counts: dict[str, int]
    workspace: WorkspaceState
