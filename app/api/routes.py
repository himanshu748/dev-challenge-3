from typing import Optional

from fastapi import APIRouter, Depends, Request

from app.schemas.hireiq import (
    AddJobRequest,
    GenerateOfferRequest,
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
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/logs", response_model=LogsResponse)
async def get_logs(service: HireIQService = Depends(get_hireiq_service)) -> LogsResponse:
    return service.get_logs()


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
