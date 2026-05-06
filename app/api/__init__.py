"""
API routes for the dependiq application
"""

from fastapi import APIRouter

# Import route modules
from . import analysis, auth, files, jobs, progress, projects, updates, user


def create_router() -> APIRouter:
    """Create and configure the main API router"""
    router = APIRouter()

    # Include route modules
    router.include_router(auth.router, tags=["authentication"])
    router.include_router(user.router, tags=["user"])
    router.include_router(projects.router, tags=["projects"])
    router.include_router(jobs.router, tags=["jobs"])
    router.include_router(analysis.router, tags=["analysis"])
    router.include_router(progress.router, tags=["progress"])
    router.include_router(updates.router, tags=["updates"])
    router.include_router(files.router, tags=["files"])

    return router


__all__ = ["create_router"]
