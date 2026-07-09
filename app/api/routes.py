from typing import Optional

from fastapi import APIRouter, Depends, Request

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
from app.services.hireiq import HireIQService


router = APIRouter()


def get_hireiq_service(request: Request) -> HireIQService:
    return request.app.state.hireiq_service


@router.get("/health")
async def health(
    service: HireIQService = Depends(get_hireiq_service),
) -> dict:
    return {
        "status": "ok",
        "hf_key": bool(service.settings.hf_api_key),
        "model": service.settings.hf_model,
    }


@router.get("/logs", response_model=LogsResponse)
async def get_logs(service: HireIQService = Depends(get_hireiq_service)) -> LogsResponse:
    return service.get_logs()


@router.get("/candidates", response_model=CandidatesResponse)
async def get_candidates(
    service: HireIQService = Depends(get_hireiq_service),
) -> CandidatesResponse:
    return service.get_candidates()


@router.get("/jobs", response_model=JobsResponse)
async def get_jobs(
    service: HireIQService = Depends(get_hireiq_service),
) -> JobsResponse:
    return service.get_jobs()


@router.post("/setup", response_model=OperationResponse)
async def setup(
    request: Optional[SetupRequest] = None,
    service: HireIQService = Depends(get_hireiq_service),
) -> OperationResponse:
    return await service.setup_workspace(request or SetupRequest())


@router.post("/add-job", response_model=OperationResponse)
async def add_job(
    request: AddJobRequest,
    service: HireIQService = Depends(get_hireiq_service),
) -> OperationResponse:
    return await service.add_job(request)


@router.post("/screen-candidate", response_model=OperationResponse)
async def screen_candidate(
    request: ScreenCandidateRequest,
    service: HireIQService = Depends(get_hireiq_service),
) -> OperationResponse:
    return await service.screen_candidate(request)


@router.post("/generate-offer", response_model=OperationResponse)
async def generate_offer(
    request: GenerateOfferRequest,
    service: HireIQService = Depends(get_hireiq_service),
) -> OperationResponse:
    return await service.generate_offer(request)
