"""
User profile and preferences API routes
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware import get_current_user
from ..models import ProjectHistory, User, UserPreference

router = APIRouter(prefix="/user", tags=["user"])


# Request/Response Models


class UpdateProfileRequest(BaseModel):
    """Update user profile request"""

    email: EmailStr | None = None


class UserPreferencesResponse(BaseModel):
    """User preferences response"""

    theme: str
    language: str
    timezone: str
    notifications_enabled: bool
    high_contrast: bool
    colorblind_mode: str | None
    font_size: str
    reduce_motion: bool
    updated_at: str


class UpdatePreferencesRequest(BaseModel):
    """Update user preferences request"""

    theme: str | None = None
    language: str | None = None
    timezone: str | None = None
    notifications_enabled: bool | None = None
    high_contrast: bool | None = None
    colorblind_mode: str | None = None
    font_size: str | None = None
    reduce_motion: bool | None = None


class ProjectHistoryItem(BaseModel):
    """Project history item"""

    id: str
    session_id: str
    project_name: str | None
    project_type: str | None
    source_type: str
    github_repo_url: str | None
    status: str
    dependencies_count: int
    updates_count: int
    created_at: str
    completed_at: str | None
    error_message: str | None


class ProjectHistoryResponse(BaseModel):
    """Project history response with pagination"""

    projects: list[ProjectHistoryItem]
    pagination: dict


class OAuthConnectionResponse(BaseModel):
    """OAuth connection response"""

    id: str
    provider: str
    provider_email: str | None
    connected_at: str
    updated_at: str


class UserProfileResponse(BaseModel):
    """Complete user profile response"""

    id: str
    email: str
    email_verified: bool
    is_active: bool
    created_at: str
    last_login_at: str | None
    oauth_connections: list[OAuthConnectionResponse]
    preferences: UserPreferencesResponse


class MessageResponse(BaseModel):
    """Generic message response"""

    message: str


# Routes


@router.get("/profile", response_model=UserProfileResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Get complete user profile including OAuth connections and preferences
    """
    # Build OAuth connections from user token columns
    oauth_connections = []
    if current_user.github_access_token:
        oauth_connections.append(
            OAuthConnectionResponse(
                id="github",
                provider="github",
                provider_email=current_user.email,
                connected_at=current_user.created_at.isoformat(),
                updated_at=current_user.updated_at.isoformat(),
            )
        )

    # Get preferences
    prefs_result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )
    preferences = prefs_result.scalar_one_or_none()

    # If no preferences exist, create default ones
    if not preferences:
        preferences = UserPreference(
            user_id=current_user.id,
            theme="light",
            language="en",
            timezone="UTC",
            notifications_enabled=True,
        )
        db.add(preferences)
        await db.commit()
        await db.refresh(preferences)

    return UserProfileResponse(
        id=str(current_user.id),
        email=current_user.email,
        email_verified=current_user.email_verified,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat(),
        last_login_at=(
            current_user.last_login_at.isoformat()
            if current_user.last_login_at
            else None
        ),
        oauth_connections=oauth_connections,
        preferences=UserPreferencesResponse(
            theme=preferences.theme,
            language=preferences.language,
            timezone=preferences.timezone,
            notifications_enabled=preferences.notifications_enabled,
            high_contrast=preferences.high_contrast,
            colorblind_mode=preferences.colorblind_mode,
            font_size=preferences.font_size,
            reduce_motion=preferences.reduce_motion,
            updated_at=preferences.updated_at.isoformat(),
        ),
    )


@router.put("/profile", response_model=MessageResponse)
async def update_user_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update user profile information

    Currently supports:
    - Updating email address

    Note: Changing email will require re-verification
    """
    if request.email and request.email != current_user.email:
        # Check if email is already taken
        result = await db.execute(
            select(User).where(User.email == request.email.lower())
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email address is already in use",
            )

        current_user.email = request.email.lower()
        current_user.email_verified = False  # Require re-verification

        await db.commit()

        return MessageResponse(
            message="Email updated successfully. Please verify your new email address."
        )

    return MessageResponse(message="No changes made")


@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_user_preferences(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Get user preferences (theme, language, timezone, notifications)
    """
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )
    preferences = result.scalar_one_or_none()

    # Create default preferences if they don't exist
    if not preferences:
        preferences = UserPreference(
            user_id=current_user.id,
            theme="light",
            language="en",
            timezone="UTC",
            notifications_enabled=True,
        )
        db.add(preferences)
        await db.commit()
        await db.refresh(preferences)

    return UserPreferencesResponse(
        theme=preferences.theme,
        language=preferences.language,
        timezone=preferences.timezone,
        notifications_enabled=preferences.notifications_enabled,
        high_contrast=preferences.high_contrast,
        colorblind_mode=preferences.colorblind_mode,
        font_size=preferences.font_size,
        reduce_motion=preferences.reduce_motion,
        updated_at=preferences.updated_at.isoformat(),
    )


@router.put("/preferences", response_model=UserPreferencesResponse)
async def update_user_preferences(
    request: UpdatePreferencesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update user preferences

    - **theme**: 'light' or 'dark'
    - **language**: ISO language code (e.g., 'en', 'es', 'fr')
    - **timezone**: Timezone string (e.g., 'UTC', 'America/New_York')
    - **notifications_enabled**: Boolean
    """
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )
    preferences = result.scalar_one_or_none()

    # Create preferences if they don't exist
    if not preferences:
        preferences = UserPreference(
            user_id=current_user.id,
            theme="light",
            language="en",
            timezone="UTC",
            notifications_enabled=True,
        )
        db.add(preferences)

    # Update preferences
    if request.theme is not None:
        valid_themes = ["light", "dark", "ocean", "forest", "nord", "dracula", "system"]
        if request.theme not in valid_themes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Theme must be one of: {', '.join(valid_themes)}",
            )
        preferences.theme = request.theme

    if request.language is not None:
        preferences.language = request.language

    if request.timezone is not None:
        preferences.timezone = request.timezone

    if request.notifications_enabled is not None:
        preferences.notifications_enabled = request.notifications_enabled

    # Update accessibility preferences
    if request.high_contrast is not None:
        preferences.high_contrast = request.high_contrast

    # Check if colorblind_mode field is present in request (allow None to clear)
    if hasattr(request, "colorblind_mode") and "colorblind_mode" in request.model_dump(
        exclude_unset=True
    ):
        valid_modes = ["protanopia", "deuteranopia", "tritanopia"]
        if request.colorblind_mode and request.colorblind_mode not in valid_modes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Colorblind mode must be one of: {', '.join(valid_modes)}, or null",
            )
        preferences.colorblind_mode = request.colorblind_mode

    if request.font_size is not None:
        valid_sizes = ["normal", "large", "xlarge"]
        if request.font_size not in valid_sizes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Font size must be one of: {', '.join(valid_sizes)}",
            )
        preferences.font_size = request.font_size

    if request.reduce_motion is not None:
        preferences.reduce_motion = request.reduce_motion

    await db.commit()
    await db.refresh(preferences)

    return UserPreferencesResponse(
        theme=preferences.theme,
        language=preferences.language,
        timezone=preferences.timezone,
        notifications_enabled=preferences.notifications_enabled,
        high_contrast=preferences.high_contrast,
        colorblind_mode=preferences.colorblind_mode,
        font_size=preferences.font_size,
        reduce_motion=preferences.reduce_motion,
        updated_at=preferences.updated_at.isoformat(),
    )


@router.get("/projects", response_model=ProjectHistoryResponse)
async def get_user_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(None, description="Filter by status"),
    source_type: str | None = Query(None, description="Filter by source type"),
):
    """
    Get user's project history with pagination and filtering

    - **page**: Page number (default: 1)
    - **limit**: Items per page (default: 20, max: 100)
    - **status**: Filter by status ('processing', 'completed', 'failed')
    - **source_type**: Filter by source ('zip_upload', 'github')
    """
    # Build query
    query = select(ProjectHistory).where(ProjectHistory.user_id == current_user.id)

    if status:
        query = query.where(ProjectHistory.status == status)

    if source_type:
        query = query.where(ProjectHistory.source_type == source_type)

    # Get total count
    count_query = (
        select(func.count())
        .select_from(ProjectHistory)
        .where(ProjectHistory.user_id == current_user.id)
    )
    if status:
        count_query = count_query.where(ProjectHistory.status == status)
    if source_type:
        count_query = count_query.where(ProjectHistory.source_type == source_type)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Calculate pagination
    offset = (page - 1) * limit
    total_pages = (total + limit - 1) // limit

    # Get projects
    query = query.order_by(ProjectHistory.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    projects = result.scalars().all()

    return ProjectHistoryResponse(
        projects=[
            ProjectHistoryItem(
                id=str(proj.id),
                session_id=proj.session_id,
                project_name=proj.project_name,
                project_type=proj.project_type,
                source_type=proj.source_type,
                github_repo_url=proj.github_repo_url,
                status=proj.status,
                dependencies_count=proj.dependencies_count,
                updates_count=proj.updates_count,
                created_at=proj.created_at.isoformat(),
                completed_at=(
                    proj.completed_at.isoformat() if proj.completed_at else None
                ),
                error_message=proj.error_message,
            )
            for proj in projects
        ],
        pagination={
            "page": page,
            "limit": limit,
            "total": total,
            "pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    )


@router.get("/projects/{session_id}", response_model=ProjectHistoryItem)
async def get_project_details(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed information about a specific project
    """
    result = await db.execute(
        select(ProjectHistory).where(
            ProjectHistory.session_id == session_id,
            ProjectHistory.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    return ProjectHistoryItem(
        id=str(project.id),
        session_id=project.session_id,
        project_name=project.project_name,
        project_type=project.project_type,
        source_type=project.source_type,
        github_repo_url=project.github_repo_url,
        status=project.status,
        dependencies_count=project.dependencies_count,
        updates_count=project.updates_count,
        created_at=project.created_at.isoformat(),
        completed_at=project.completed_at.isoformat() if project.completed_at else None,
        error_message=project.error_message,
    )


@router.get("/oauth-connections", response_model=list[OAuthConnectionResponse])
async def get_oauth_connections(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Get all OAuth connections for the current user.
    Derived from token columns on the User model.
    """
    connections = []
    if current_user.github_access_token:
        connections.append(
            OAuthConnectionResponse(
                id="github",
                provider="github",
                provider_email=current_user.email,
                connected_at=current_user.created_at.isoformat(),
                updated_at=current_user.updated_at.isoformat(),
            )
        )
    if current_user.gitlab_access_token:
        connections.append(
            OAuthConnectionResponse(
                id="gitlab",
                provider="gitlab",
                provider_email=current_user.email,
                connected_at=current_user.created_at.isoformat(),
                updated_at=current_user.updated_at.isoformat(),
            )
        )
    if current_user.bitbucket_access_token:
        connections.append(
            OAuthConnectionResponse(
                id="bitbucket",
                provider="bitbucket",
                provider_email=current_user.email,
                connected_at=current_user.created_at.isoformat(),
                updated_at=current_user.updated_at.isoformat(),
            )
        )
    return connections


@router.delete("/oauth-connections/{provider}", response_model=MessageResponse)
async def unlink_oauth_connection(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Unlink an OAuth connection from the user's account.

    - **provider**: OAuth provider name ('github', 'gitlab', 'bitbucket')
    """
    token_attr = f"{provider}_access_token"
    if not hasattr(current_user, token_attr) or not getattr(current_user, token_attr):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {provider} connection found",
        )

    setattr(current_user, token_attr, None)
    await db.commit()

    return MessageResponse(
        message=f"{provider.capitalize()} account unlinked successfully"
    )
