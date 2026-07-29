from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Expose models so SQLAlchemy registry finds them and Base.metadata is fully populated
from app.graphs.models import Graph, GraphHistory  # noqa: E402
from app.users.models import User  # noqa: E402

__all__ = ["Base", "User", "Graph", "GraphHistory"]
