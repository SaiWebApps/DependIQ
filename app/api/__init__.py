"""
API routes for the dependiq application
"""

from fastapi import APIRouter

# Import route modules
from . import (
    analysis,
    auth,
    blast_radius,
    files,
    graph,
    jobs,
    pipeline,
    progress,
    projects,
    relationships,
    stream,
    updates,
    user,
    workspaces,
)


def create_router() -> APIRouter:
    """Create and configure the main API router"""
    router = APIRouter()

    # Include route modules
    router.include_router(auth.router, tags=["authentication"])
    router.include_router(user.router, tags=["user"])
    router.include_router(projects.router, tags=["projects"])
    router.include_router(workspaces.router, tags=["workspaces"])
    router.include_router(jobs.router, tags=["jobs"])
    router.include_router(analysis.router, tags=["analysis"])
    router.include_router(progress.router, tags=["progress"])
    router.include_router(updates.router, tags=["updates"])
    router.include_router(files.router, tags=["files"])
    router.include_router(pipeline.router, tags=["pipeline"])
    router.include_router(stream.router, tags=["stream"])
    router.include_router(graph.router, tags=["graph"])
    router.include_router(relationships.router, tags=["relationships"])
    router.include_router(blast_radius.router, tags=["blast_radius"])

    return router


__all__ = ["create_router"]
