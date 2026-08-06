import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.context import UnitOfWork
from app.copilot import service as copilot_service
from app.db import get_uow
from app.graphs.schemas import GraphFlowRead

router = APIRouter(prefix="/copilot", tags=["copilot"])


class CopilotInitiateRequest(BaseModel):
    prompt: str


class CopilotDecisionRequest(BaseModel):
    approved: bool


class CopilotStatusResponse(BaseModel):
    graph_id: str
    status: str
    plan: list[dict[str, Any]] | None = None
    operations: list[dict[str, Any]] | None = None
    validation_error: str | None = None
    applied: bool
    flow_data: GraphFlowRead | None = None


@router.post("/{graph_id}/initiate", response_model=CopilotStatusResponse)
async def initiate_copilot_endpoint(
    graph_id: uuid.UUID,
    payload: CopilotInitiateRequest,
    uow: UnitOfWork = Depends(get_uow),
) -> CopilotStatusResponse:
    async with uow:
        result = await copilot_service.initiate_copilot_workflow(
            uow=uow,
            graph_id=graph_id,
            prompt=payload.prompt,
        )
    return CopilotStatusResponse.model_validate(result)


@router.post("/{graph_id}/approve-plan", response_model=CopilotStatusResponse)
async def approve_plan_endpoint(
    graph_id: uuid.UUID,
    payload: CopilotDecisionRequest,
    uow: UnitOfWork = Depends(get_uow),
) -> CopilotStatusResponse:
    async with uow:
        result = await copilot_service.approve_copilot_plan(
            uow=uow,
            graph_id=graph_id,
            approved=payload.approved,
        )
    return CopilotStatusResponse.model_validate(result)


@router.post("/{graph_id}/apply", response_model=CopilotStatusResponse)
async def apply_copilot_patch_endpoint(
    graph_id: uuid.UUID,
    payload: CopilotDecisionRequest,
    uow: UnitOfWork = Depends(get_uow),
) -> CopilotStatusResponse:
    async with uow:
        result = await copilot_service.apply_copilot_patch(
            uow=uow,
            graph_id=graph_id,
            approved=payload.approved,
        )
    return CopilotStatusResponse.model_validate(result)
