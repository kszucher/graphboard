from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.graphs.operations import GraphUpdateInput


class OperationPlan(BaseModel):
    """The plan containing a single declarative transaction to update the graph."""

    thought_process: str = Field(
        description=(
            "Before outputting the graph update payload, think step-by-step. Document: "
            "1. What new nodes and state variables are needed. "
            "2. Exactly what routing transitions need to change (targets and branches). "
            "3. What Prisma filters and atomic updates need to be written."
        )
    )
    update: GraphUpdateInput
