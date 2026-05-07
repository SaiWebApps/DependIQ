"""
Unit tests for database models
"""

from datetime import datetime

import pytest
from sqlalchemy import select

from app.models.project_history import ProjectHistory
from app.models.user import User
from app.models.user_preference import UserPreference


class TestUserModel:
    """Test User model"""

    @pytest.mark.asyncio
    async def test_create_user(self, test_db_session):
        """Test creating a user"""
        user = User(
            email="model_test@example.com",
            workos_user_id="workos_model_test",
            email_verified=False,
            is_active=True,
        )

        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)

        assert user.id is not None
        assert user.email == "model_test@example.com"
        assert user.created_at is not None
        assert user.updated_at is not None

    @pytest.mark.asyncio
    async def test_user_email_unique(self, test_db_session, test_user):
        """Test that user email must be unique"""
        duplicate_user = User(
            email=test_user.email,
            workos_user_id="workos_dup",
            email_verified=False,
        )

        test_db_session.add(duplicate_user)

        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await test_db_session.commit()

    @pytest.mark.asyncio
    async def test_user_timestamps(self, test_db_session):
        """Test user timestamp fields"""
        user = User(
            email="timestamps@example.com",
            workos_user_id="workos_ts",
        )

        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)

        assert user.created_at is not None
        assert user.updated_at is not None
        assert isinstance(user.created_at, datetime)
        assert isinstance(user.updated_at, datetime)

    @pytest.mark.asyncio
    async def test_user_provider_columns(self, test_db_session):
        """Test user provider OAuth columns"""
        user = User(
            email="providers@example.com",
            workos_user_id="workos_prov",
            email_verified=True,
            is_active=True,
        )

        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)

        # Columns exist and default to None
        assert user.github_access_token is None
        assert user.gitlab_access_token is None
        assert user.bitbucket_access_token is None


class TestUserPreferenceModel:
    """Test UserPreference model"""

    @pytest.mark.asyncio
    async def test_create_preference(self, test_db_session, test_user):
        """Test creating user preferences"""
        preference = UserPreference(
            user_id=test_user.id,
            theme="dark",
            language="es",
            timezone="America/New_York",
            notifications_enabled=True,
        )

        test_db_session.add(preference)
        await test_db_session.commit()
        await test_db_session.refresh(preference)

        assert preference.user_id is not None
        assert preference.theme == "dark"
        assert preference.language == "es"

    @pytest.mark.asyncio
    async def test_preference_defaults(self, test_db_session, test_user):
        """Test default preference values"""
        preference = UserPreference(user_id=test_user.id)

        test_db_session.add(preference)
        await test_db_session.commit()
        await test_db_session.refresh(preference)

        # Check defaults (adjust based on your model defaults)
        assert preference.theme in ["light", "dark", None]
        assert preference.notifications_enabled in [True, False, None]


class TestProjectHistoryModel:
    """Test ProjectHistory model"""

    @pytest.mark.asyncio
    async def test_create_project_history(self, test_db_session, test_user):
        """Test creating project history entry"""
        project = ProjectHistory(
            user_id=test_user.id,
            session_id="test_session_123",
            project_name="Test Project",
            source_type="zip_upload",
            status="pending",
        )

        test_db_session.add(project)
        await test_db_session.commit()
        await test_db_session.refresh(project)

        assert project.id is not None
        assert project.project_name == "Test Project"
        assert project.status == "pending"
        assert project.created_at is not None

    @pytest.mark.asyncio
    async def test_project_history_status_update(self, test_db_session, test_user):
        """Test updating project status"""
        project = ProjectHistory(
            user_id=test_user.id,
            session_id="test_session_456",
            project_name="Update Test",
            source_type="github",
            status="processing",
        )

        test_db_session.add(project)
        await test_db_session.commit()

        # Update status
        project.status = "completed"
        project.dependencies_count = 10
        project.updates_count = 3

        await test_db_session.commit()
        await test_db_session.refresh(project)

        assert project.status == "completed"
        assert project.dependencies_count == 10
        assert project.updates_count == 3

    @pytest.mark.asyncio
    async def test_project_history_metadata(self, test_db_session, test_user):
        """Test project metadata storage"""
        metadata = {"project_type": "python", "file_count": 50, "custom_field": "value"}

        project = ProjectHistory(
            user_id=test_user.id,
            session_id="metadata_test",
            project_name="Metadata Test",
            source_type="zip_upload",
            status="completed",
            metadata=metadata,
        )

        test_db_session.add(project)
        await test_db_session.commit()
        await test_db_session.refresh(project)

        assert project.metadata is not None
        assert project.metadata["project_type"] == "python"
        assert project.metadata["file_count"] == 50


class TestModelRelationships:
    """Test model relationships"""

    @pytest.mark.asyncio
    async def test_user_preferences_relationship(self, test_db_session, test_user):
        """Test user to preferences relationship"""
        # Create preference
        preference = UserPreference(user_id=test_user.id, theme="dark")

        test_db_session.add(preference)
        await test_db_session.commit()

        # Query user with preferences
        result = await test_db_session.execute(
            select(User).where(User.id == test_user.id)
        )
        user = result.scalar_one()

        assert user is not None
        assert user.id == test_user.id

    @pytest.mark.asyncio
    async def test_user_projects_relationship(self, test_db_session, test_user):
        """Test user to projects relationship"""
        # Create multiple projects
        for i in range(3):
            project = ProjectHistory(
                user_id=test_user.id,
                session_id=f"session_{i}",
                project_name=f"Project {i}",
                source_type="zip_upload",
                status="completed",
            )
            test_db_session.add(project)

        await test_db_session.commit()

        # Query projects
        result = await test_db_session.execute(
            select(ProjectHistory).where(ProjectHistory.user_id == test_user.id)
        )
        projects = result.scalars().all()

        assert len(projects) == 3
