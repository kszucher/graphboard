import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.context import UnitOfWork
from app.copilot import service as copilot_service
from app.core.db import get_uow

router = APIRouter(prefix="/copilot", tags=["copilot"])


class CopilotInitiateRequest(BaseModel):
    prompt: str


class CopilotStatusResponse(BaseModel):
    graph_id: str
    applied: bool
    validation_error: str | None = None


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
