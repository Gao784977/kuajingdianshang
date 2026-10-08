"""Health check and workflow definition endpoints."""
from __future__ import annotations

from backend.api import Request, Response, Router
from backend.config import APP_ENV, APP_VERSION, WORKFLOW_DEFINITION

router = Router()


@router.get("/api/health")
def health(_request: Request) -> Response:
    return Response.json({
        "status": "ok",
        "version": APP_VERSION,
        "environment": APP_ENV,
    })


@router.get("/api/workflow/definition")
def workflow_definition(_request: Request) -> Response:
    """Return the canonical Agent order so the frontend renders dynamically.

    The frontend MUST NOT hardcode the Agent list; it consumes this
    endpoint so workflow changes propagate automatically.
    """
    return Response.json(WORKFLOW_DEFINITION)
