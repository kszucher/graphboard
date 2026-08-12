import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import graphs, users, ws
from app.config import settings
from app.exceptions import GraphboardError

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Graphboard API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    @app.exception_handler(GraphboardError)
    async def graphboard_exception_handler(request: Request, exc: GraphboardError) -> JSONResponse:
        logger.error("Validation error: %s", exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error", "error": str(exc)},
        )

    from app import copilot

    app.include_router(users.router)
    app.include_router(graphs.router)
    app.include_router(ws.router)
    app.include_router(copilot.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
