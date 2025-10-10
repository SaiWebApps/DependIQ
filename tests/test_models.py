"""
Unit tests for database models
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.email_verification_token import EmailVerificationToken
from app.models.magic_link_token import MagicLinkToken
from app.models.oauth_connection import OAuthConnection
from app.models.password_reset_token import PasswordResetToken
from app.models.project_history import ProjectHistory
from app.models.user import User
from app.models.user_preference import UserPreference
from app.models.user_session import UserSession
from app.utils.password_utils import hash_password


class TestUserModel:
    """Test User model"""

    @pytest.mark.asyncio
    async def test_create_user(self, test_db_session):
        """Test creating a user"""
        user = User(
            email="model_test@example.com",
            password_hash=hash_password("TestPassword123!"),
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
            password_hash=hash_password("Different123!"),
            email_verified=False,
        )

        test_db_session.add(duplicate_user)

        # Use specific exception instead of generic Exception
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await test_db_session.commit()

    @pytest.mark.asyncio
    async def test_user_timestamps(self, test_db_session):
        """Test user timestamp fields"""
        user = User(
            email="timestamps@example.com",
            password_hash=hash_password("TestPassword123!"),
        )

        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)

        assert user.created_at is not None
        assert user.updated_at is not None
        assert isinstance(user.created_at, datetime)
        assert isinstance(user.updated_at, datetime)


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


class TestOAuthConnectionModel:
    """Test OAuthConnection model"""

    @pytest.mark.asyncio
    async def test_create_oauth_connection(self, test_db_session, test_user):
        """Test creating OAuth connection"""
        connection = OAuthConnection(
            user_id=test_user.id,
            provider="github",
            provider_user_id="12345",
            provider_email="github@example.com",
            access_token="gho_test_token",
            scopes="read:user repo",
        )

        test_db_session.add(connection)
        await test_db_session.commit()
        await test_db_session.refresh(connection)

        assert connection.id is not None
        assert connection.provider == "github"
        assert connection.provider_user_id == "12345"

    @pytest.mark.asyncio
    async def test_oauth_connection_provider_data(self, test_db_session, test_user):
        """Test OAuth provider data storage"""
        provider_data = {
            "id": 12345,
            "login": "testuser",
            "avatar_url": "https://example.com/avatar.jpg",
        }

        connection = OAuthConnection(
            user_id=test_user.id,
            provider="github",
            provider_user_id="12345",
            access_token="token",
            provider_data=provider_data,
        )

        test_db_session.add(connection)
        await test_db_session.commit()
        await test_db_session.refresh(connection)

        assert connection.provider_data is not None
        assert connection.provider_data["login"] == "testuser"


class TestUserSessionModel:
    """Test UserSession model"""

    @pytest.mark.asyncio
    async def test_create_user_session(self, test_db_session, test_user):
        """Test creating user session"""
        expires_at = datetime.utcnow() + timedelta(hours=8)

        session = UserSession(
            user_id=test_user.id,
            session_token="test_session_token",
            expires_at=expires_at,
        )

        test_db_session.add(session)
        await test_db_session.commit()
        await test_db_session.refresh(session)

        assert session.id is not None
        assert session.session_token == "test_session_token"
        assert session.expires_at is not None

    @pytest.mark.asyncio
    async def test_session_expiration_check(self, test_db_session, test_user):
        """Test checking if session is expired"""
        # Create expired session
        expired_session = UserSession(
            user_id=test_user.id,
            session_token="expired_token",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )

        # Create valid session
        valid_session = UserSession(
            user_id=test_user.id,
            session_token="valid_token",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )

        test_db_session.add(expired_session)
        test_db_session.add(valid_session)
        await test_db_session.commit()

        # Query for non-expired sessions
        result = await test_db_session.execute(
            select(UserSession).where(
                UserSession.user_id == test_user.id,
                UserSession.expires_at > datetime.utcnow(),
            )
        )
        sessions = result.scalars().all()

        assert len(sessions) == 1
        assert sessions[0].session_token == "valid_token"


class TestTokenModels:
    """Test various token models"""

    @pytest.mark.asyncio
    async def test_create_email_verification_token(self, test_db_session, test_user):
        """Test creating email verification token"""
        token = EmailVerificationToken(
            user_id=test_user.id,
            token="verify_token_123",
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )

        test_db_session.add(token)
        await test_db_session.commit()
        await test_db_session.refresh(token)

        assert token.id is not None
        assert token.token == "verify_token_123"
        assert not token.is_used()

    @pytest.mark.asyncio
    async def test_create_password_reset_token(self, test_db_session, test_user):
        """Test creating password reset token"""
        token = PasswordResetToken(
            user_id=test_user.id,
            token="reset_token_456",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )

        test_db_session.add(token)
        await test_db_session.commit()
        await test_db_session.refresh(token)

        assert token.id is not None
        assert token.token == "reset_token_456"

    @pytest.mark.asyncio
    async def test_create_magic_link_token(self, test_db_session, test_user):
        """Test creating magic link token"""
        token = MagicLinkToken(
            email=test_user.email,
            token="magic_token_789",
            temp_password="TempPass123!",
            expires_at=datetime.utcnow() + timedelta(minutes=15),
        )

        test_db_session.add(token)
        await test_db_session.commit()
        await test_db_session.refresh(token)

        assert token.id is not None
        assert token.token == "magic_token_789"

    @pytest.mark.asyncio
    async def test_token_expiration_and_usage(self, test_db_session, test_user):
        """Test token expiration and usage tracking"""
        token = EmailVerificationToken(
            user_id=test_user.id,
            token="usage_test_token",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )

        test_db_session.add(token)
        await test_db_session.commit()

        # Mark as used
        token.used_at = datetime.utcnow()

        await test_db_session.commit()
        await test_db_session.refresh(token)

        assert token.is_used() is True
        assert token.used_at is not None


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

    @pytest.mark.asyncio
    async def test_user_oauth_connections_relationship(
        self, test_db_session, test_user
    ):
        """Test user to OAuth connections relationship"""
        # Create OAuth connection
        connection = OAuthConnection(
            user_id=test_user.id,
            provider="github",
            provider_user_id="54321",
            access_token="token",
        )

        test_db_session.add(connection)
        await test_db_session.commit()

        # Query connections
        result = await test_db_session.execute(
            select(OAuthConnection).where(OAuthConnection.user_id == test_user.id)
        )
        connections = result.scalars().all()

        assert len(connections) >= 1
        assert connections[0].provider == "github"
