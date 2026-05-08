"""
Graph API routes for workspace dependency topology.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..graph.service import get_graph_service
from ..middleware import get_current_user
from ..models import User

router = APIRouter(prefix="/workspaces", tags=["graph"])


class GraphResponse(BaseModel):
    """Response for workspace graph."""

    nodes: list[dict]
    edges: list[dict]


@router.get("/{workspace_id}/graph", response_model=GraphResponse)
async def get_workspace_graph(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the full dependency graph for a workspace (nodes + edges)."""
    try:
        service = await get_graph_service()
        graph = await service.get_workspace_graph(workspace_id)
        return GraphResponse(nodes=graph["nodes"], edges=graph["edges"])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph service unavailable: {e!s}",
        )
