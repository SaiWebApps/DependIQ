"""
Blast radius API endpoints.

POST /api/workspaces/{workspace_id}/blast-radius — compute affected projects
GET  /api/blast-radius/{blast_radius_id}/explain — SSE stream of chain reaction explanation
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..graph import GraphService
from ..middleware import get_current_user
from ..models import User
from ..services import stream_publisher
from ..services.blast_radius import (
    BlastRadiusService,
    get_blast_result,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["blast-radius"])

# Hold references to background tasks to prevent garbage collection (RUF006)
_background_tasks: set[asyncio.Task] = set()


# --- Request/Response Models ---


class BlastRadiusRequest(BaseModel):
    """Request body for computing blast radius."""

    package: str
    ecosystem: str
    from_version: str | None = None
    to_version: str | None = None


class AffectedProjectResponse(BaseModel):
    """A single affected project in the blast radius."""

    project_id: str
    name: str
    distance: int
    impact_type: str


class BlastRadiusResponse(BaseModel):
    """Response from the blast radius computation."""

    id: str
    package: str
    ecosystem: str
    from_version: str | None
    to_version: str | None
    affected_projects: list[AffectedProjectResponse]
    total_affected: int
    computed_at: str
    stream_url: str


# --- Dependency injection ---


def get_graph_service() -> GraphService:
    """Provide a GraphService instance. Overridden in tests."""
    return GraphService()


def get_blast_radius_service(
    graph_service: GraphService = Depends(get_graph_service),
) -> BlastRadiusService:
    """Provide a BlastRadiusService. Overridden in tests."""
    return BlastRadiusService(graph_service=graph_service)


# --- Endpoints ---


@router.post(
    "/workspaces/{workspace_id}/blast-radius",
    response_model=BlastRadiusResponse,
    status_code=status.HTTP_200_OK,
)
async def compute_blast_radius(
    workspace_id: str,
    body: BlastRadiusRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    service: BlastRadiusService = Depends(get_blast_radius_service),
):
    """
    Compute the blast radius of a package update within a workspace.

    Returns the list of affected projects ordered by distance, plus a
    stream_url the client can connect to for an LLM-powered explanation
    of the chain reaction.
    """
    try:
        result = await service.compute_blast_radius(
            workspace_id=workspace_id,
            package_name=body.package,
            ecosystem=body.ecosystem,
            from_version=body.from_version,
            to_version=body.to_version,
        )
    except Exception as e:
        logger.error("Blast radius computation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Blast radius computation failed: {e!s}",
        )

    # Kick off the explanation stream in the background
    task_id = f"explain-{result['id']}-{uuid.uuid4().hex[:8]}"
    background_tasks.add_task(service.explain_chain_reaction, result["id"], task_id)

    stream_url = f"/api/blast-radius/{result['id']}/explain?task_id={task_id}"

    return BlastRadiusResponse(
        id=result["id"],
        package=result["package"],
        ecosystem=result["ecosystem"],
        from_version=result.get("from_version"),
        to_version=result.get("to_version"),
        affected_projects=[
            AffectedProjectResponse(
                project_id=p.get("project_id", ""),
                name=p.get("name", ""),
                distance=p.get("distance", 0),
                impact_type=p.get("impact_type", "unknown"),
            )
            for p in result["affected_projects"]
        ],
        total_affected=result["total_affected"],
        computed_at=result["computed_at"],
        stream_url=stream_url,
    )


@router.get("/blast-radius/{blast_radius_id}/explain")
async def explain_blast_radius(
    blast_radius_id: str,
    task_id: str | None = None,
    current_user: User = Depends(get_current_user),
    service: BlastRadiusService = Depends(get_blast_radius_service),
):
    """
    Stream LLM explanation of the blast radius chain reaction via SSE.

    Each affected project is analyzed sequentially with progress events,
    thinking events, and result events published as the LLM reasons.
    """
    # Verify the blast radius result exists
    result = get_blast_result(blast_radius_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blast radius result '{blast_radius_id}' not found or expired",
        )

    # If no task_id provided, start a new explanation
    if task_id is None:
        task_id = f"explain-{blast_radius_id}-{uuid.uuid4().hex[:8]}"
        # Start the explanation in a background task via asyncio
        task = asyncio.create_task(
            service.explain_chain_reaction(blast_radius_id, task_id)
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    else:
        # Ensure the stream exists (it was created by the background task)
        # Give it a moment to initialize if needed
        for _ in range(10):
            if task_id in stream_publisher.get_active_streams():
                break
            await asyncio.sleep(0.05)

    return StreamingResponse(
        stream_publisher.subscribe(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
            "X-Accel-Buffering": "no",
        },
    )
