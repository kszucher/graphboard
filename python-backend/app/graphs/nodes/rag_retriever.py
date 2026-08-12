from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.constants import NodeType

from .base import BaseNode


class RagRetrieverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.RAG_RETRIEVER] = NodeType.RAG_RETRIEVER
    query_var: str = ""
    context_output_var: str = ""
    knowledge_base: str = "trivia"
    top_k: int = 3


class RagRetrieverNode(BaseNode, RagRetrieverConfig):
    def get_variable_references(self) -> set[str]:
        refs = set()
        if self.query_var:
            refs.add(self.query_var)
        if self.context_output_var:
            refs.add(self.context_output_var)
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        if self.query_var == old_key:
            self.query_var = new_key
        if self.context_output_var == old_key:
            self.context_output_var = new_key

    def serialize_compact(self) -> list[str]:
        return [
            f"  - {self.id} [{self.node_type.value}]",
            f"    query: {self.query_var}",
            f"    output: {self.context_output_var}",
            f"    kb: {self.knowledge_base}",
            f"    top_k: {self.top_k}",
        ]

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        if not self.query_var:
            raise ValidationError(f"RAG node '{self.id}' requires a query_var.")
        if not self.context_output_var:
            raise ValidationError(f"RAG node '{self.id}' requires a context_output_var.")
