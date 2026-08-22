from __future__ import annotations

from typing import Literal

from app.core.constants import NodeType

from .base import BaseNode


class RagRetrieverNode(BaseNode):
    node_type: Literal[NodeType.RAG_RETRIEVER] = NodeType.RAG_RETRIEVER
    query_var: str = ""
    context_output_var: str = ""
    knowledge_base: str = "trivia"
    top_k: int = 3

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.core.exceptions import ValidationError

        if not self.query_var:
            raise ValidationError(f"RAG node '{self.id}' requires a query_var.")
        if not self.context_output_var:
            raise ValidationError(f"RAG node '{self.id}' requires a context_output_var.")
