"""
User service for common user operations
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ProjectHistory, UserPreference


class UserService:
    """Service for user-related operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_preferences(self, user_id: str) -> UserPreference:
        """
        Get user preferences or create default if they don't exist

        Args:
            user_id: User ID

        Returns:
            UserPreference object
        """
        # Convert string UUID to UUID object if needed
        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

        result = await self.db.execute(
            select(UserPreference).where(UserPreference.user_id == user_uuid)
        )
        preferences = result.scalar_one_or_none()

        if not preferences:
            preferences = UserPreference(
                user_id=user_uuid,
                theme="light",
                language="en",
                timezone="UTC",
                notifications_enabled=True,
            )
            self.db.add(preferences)
            await self.db.commit()
            await self.db.refresh(preferences)

        return preferences

    async def create_project_history(
        self,
        user_id: str,
        session_id: str,
        project_name: str | None = None,
        project_type: str | None = None,
        source_type: str = "zip_upload",
        github_repo_url: str | None = None,
        zip_file_path: str | None = None,
    ) -> ProjectHistory:
        """
        Create a new project history entry

        Args:
            user_id: User ID
            session_id: Unique session identifier
            project_name: Optional project name
            project_type: Optional project type (python, java, etc.)
            source_type: Source type (zip_upload or github)
            github_repo_url: Optional GitHub repository URL
            zip_file_path: Optional path to uploaded ZIP file

        Returns:
            ProjectHistory object
        """
        # Convert string UUID to UUID object if needed
        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

        project = ProjectHistory(
            user_id=user_uuid,
            session_id=session_id,
            project_name=project_name,
            project_type=project_type,
            source_type=source_type,
            github_repo_url=github_repo_url,
            zip_file_path=zip_file_path,
            status="processing",
            dependencies_count=0,
            updates_count=0,
        )

        self.db.add(project)
        await self.db.commit()
        await self.db.refresh(project)

        return project

    async def update_project_status(
        self,
        session_id: str,
        status: str,
        dependencies_count: int = 0,
        updates_count: int = 0,
        error_message: str | None = None,
        metadata: dict | None = None,
    ) -> ProjectHistory | None:
        """
        Update project history status

        Args:
            session_id: Session identifier
            status: New status (processing, completed, failed)
            dependencies_count: Number of dependencies found
            updates_count: Number of updates applied
            error_message: Optional error message
            metadata: Optional additional metadata

        Returns:
            Updated ProjectHistory object or None if not found
        """
        result = await self.db.execute(
            select(ProjectHistory).where(ProjectHistory.session_id == session_id)
        )
        project = result.scalar_one_or_none()

        if not project:
            return None

        project.status = status
        project.dependencies_count = dependencies_count
        project.updates_count = updates_count

        if error_message:
            project.error_message = error_message

        if metadata:
            project.metadata = metadata

        if status in ["completed", "failed"]:
            project.completed_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(project)

        return project

    async def get_project_by_session(
        self, session_id: str, user_id: str | None = None
    ) -> ProjectHistory | None:
        """
        Get project history by session ID

        Args:
            session_id: Session identifier
            user_id: Optional user ID to verify ownership

        Returns:
            ProjectHistory object or None
        """
        query = select(ProjectHistory).where(ProjectHistory.session_id == session_id)

        if user_id:
            user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
            query = query.where(ProjectHistory.user_id == user_uuid)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()
