import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.context import UnitOfWork
from app.db import get_uow
from app.copilot import service as copilot_service
from app.graphs.schemas import GraphFlowRead

router = APIRouter(prefix="/copilot", tags=["copilot"])


class CopilotApplyRequest(BaseModel):
    prompt: str


@router.post("/{graph_id}/apply", response_model=GraphFlowRead)
async def apply_copilot_patch_endpoint(
    graph_id: uuid.UUID,
    payload: CopilotApplyRequest,
    uow: UnitOfWork = Depends(get_uow),
) -> GraphFlowRead:
    async with uow:
        result = await copilot_service.generate_and_apply_copilot_patch(
            uow=uow,
            graph_id=graph_id,
            prompt=payload.prompt,
        )
    return GraphFlowRead.model_validate(result)
