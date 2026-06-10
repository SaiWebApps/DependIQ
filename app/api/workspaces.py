"""
Workspace API routes
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..middleware import get_current_user
from ..models import User, Workspace, WorkspaceMember

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


# Request/Response Models


class WorkspaceCreateRequest(BaseModel):
    """Request to create a workspace"""

    name: str


class WorkspaceUpdateRequest(BaseModel):
    """Request to update a workspace"""

    name: str


class WorkspaceMemberResponse(BaseModel):
    """Workspace member response"""

    id: str
    user_id: str
    role: str
    joined_at: str | None


class WorkspaceProjectResponse(BaseModel):
    """Project summary within a workspace"""

    id: str
    project_name: str
    source_type: str
    project_type: str | None
    dependencies_count: int
    outdated_dependencies_count: int


class WorkspaceResponse(BaseModel):
    """Workspace response"""

    id: str
    name: str
    owner_id: str
    created_at: str | None


class WorkspaceDetailResponse(BaseModel):
    """Workspace detail response with members and projects"""

    id: str
    name: str
    owner_id: str
    created_at: str | None
    members: list[WorkspaceMemberResponse]
    projects: list[WorkspaceProjectResponse]


class MessageResponse(BaseModel):
    """Generic message response"""

    message: str
    workspace_id: str | None = None


# Routes


@router.post("/", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    request: WorkspaceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new workspace. The creator is automatically added as owner member.
    """
    workspace = Workspace(
        name=request.name,
        owner_id=current_user.id,
    )
    db.add(workspace)
    await db.flush()

    # Auto-add creator as owner member
    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=current_user.id,
        role="owner",
    )
    db.add(member)
    await db.commit()
    await db.refresh(workspace)

    return WorkspaceResponse(
        id=str(workspace.id),
        name=workspace.name,
        owner_id=str(workspace.owner_id),
        created_at=workspace.created_at.isoformat() if workspace.created_at else None,
    )


@router.get("/", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all workspaces the current user is a member of.
    """
    result = await db.execute(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == current_user.id)
        .order_by(Workspace.created_at.desc())
    )
    workspaces = result.scalars().all()

    return [
        WorkspaceResponse(
            id=str(w.id),
            name=w.name,
            owner_id=str(w.owner_id),
            created_at=w.created_at.isoformat() if w.created_at else None,
        )
        for w in workspaces
    ]


@router.get("/{workspace_id}", response_model=WorkspaceDetailResponse)
async def get_workspace(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get workspace detail including members and projects.
    User must be a member of the workspace.
    """
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid workspace ID"
        )

    # Verify user is a member
    membership_result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ws_uuid,
            WorkspaceMember.user_id == current_user.id,
        )
    )
    if not membership_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    # Fetch workspace with members and projects
    result = await db.execute(
        select(Workspace)
        .options(selectinload(Workspace.members), selectinload(Workspace.projects))
        .where(Workspace.id == ws_uuid)
    )
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    members = [
        WorkspaceMemberResponse(
            id=str(m.id),
            user_id=str(m.user_id),
            role=m.role,
            joined_at=m.joined_at.isoformat() if m.joined_at else None,
        )
        for m in workspace.members
    ]

    projects = [
        WorkspaceProjectResponse(
            id=str(p.id),
            project_name=p.project_name,
            source_type=p.source_type,
            project_type=p.project_type,
            dependencies_count=p.dependencies_count,
            outdated_dependencies_count=p.outdated_dependencies_count,
        )
        for p in workspace.projects
    ]

    return WorkspaceDetailResponse(
        id=str(workspace.id),
        name=workspace.name,
        owner_id=str(workspace.owner_id),
        created_at=workspace.created_at.isoformat() if workspace.created_at else None,
        members=members,
        projects=projects,
    )


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    request: WorkspaceUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update workspace name. Only the owner can update.
    """
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid workspace ID"
        )

    result = await db.execute(select(Workspace).where(Workspace.id == ws_uuid))
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    if workspace.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the workspace owner can update it",
        )

    workspace.name = request.name
    await db.commit()
    await db.refresh(workspace)

    return WorkspaceResponse(
        id=str(workspace.id),
        name=workspace.name,
        owner_id=str(workspace.owner_id),
        created_at=workspace.created_at.isoformat() if workspace.created_at else None,
    )


@router.delete("/{workspace_id}", response_model=MessageResponse)
async def delete_workspace(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a workspace. Only the owner can delete.
    Cascades to members. Projects get workspace_id set to NULL.
    """
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid workspace ID"
        )

    result = await db.execute(select(Workspace).where(Workspace.id == ws_uuid))
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    if workspace.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the workspace owner can delete it",
        )

    await db.delete(workspace)
    await db.commit()

    return MessageResponse(
        message="Workspace deleted successfully",
        workspace_id=workspace_id,
    )
