from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Expose models so SQLAlchemy registry finds them and Base.metadata is fully populated
from app.modules.graphs.models import DocumentChunk, Graph, GraphHistory  # noqa: E402
from app.modules.users.models import User  # noqa: E402

__all__ = ["Base", "User", "Graph", "GraphHistory", "DocumentChunk"]
