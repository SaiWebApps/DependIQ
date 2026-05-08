"""
Tests for workspace CRUD operations
"""

import uuid

from fastapi import status
from sqlalchemy import select

from app.models import Workspace, WorkspaceMember


class TestCreateWorkspace:
    """Test workspace creation"""

    def test_create_workspace(self, test_client, auth_headers, test_user):
        """Creates workspace and verifies owner is auto-added as member"""
        response = test_client.post(
            "/api/workspaces/",
            headers=auth_headers,
            json={"name": "My Team Workspace"},
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "My Team Workspace"
        assert data["owner_id"] == str(test_user.id)
        assert "id" in data
        assert "created_at" in data

    def test_create_workspace_owner_is_member(
        self, test_client, auth_headers, test_user, test_db_session
    ):
        """Verify the owner is added as a member with role='owner'"""
        response = test_client.post(
            "/api/workspaces/",
            headers=auth_headers,
            json={"name": "Check Member"},
        )

        assert response.status_code == status.HTTP_201_CREATED
        ws_id = uuid.UUID(response.json()["id"])

        # Verify membership via direct DB query
        import asyncio

        async def check_member():
            result = await test_db_session.execute(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == ws_id,
                    WorkspaceMember.user_id == test_user.id,
                )
            )
            return result.scalar_one_or_none()

        member = asyncio.get_event_loop().run_until_complete(check_member())
        assert member is not None
        assert member.role == "owner"

    def test_create_workspace_requires_auth(self, test_client):
        """Test that creating a workspace requires authentication"""
        response = test_client.post(
            "/api/workspaces/",
            json={"name": "No Auth Workspace"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestListWorkspaces:
    """Test listing workspaces"""

    def test_list_workspaces_empty(self, test_client, auth_headers):
        """User with no workspaces sees empty list"""
        response = test_client.get("/api/workspaces/", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    def test_list_workspaces_shows_user_workspaces(
        self, test_client, auth_headers, test_user
    ):
        """User sees only workspaces they are a member of"""
        # Create two workspaces
        test_client.post(
            "/api/workspaces/",
            headers=auth_headers,
            json={"name": "Workspace A"},
        )
        test_client.post(
            "/api/workspaces/",
            headers=auth_headers,
            json={"name": "Workspace B"},
        )

        response = test_client.get("/api/workspaces/", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2
        names = {w["name"] for w in data}
        assert "Workspace A" in names
        assert "Workspace B" in names


class TestGetWorkspaceDetail:
    """Test getting workspace detail"""

    def test_get_workspace_detail(self, test_client, auth_headers, test_user):
        """Returns workspace with projects and members"""
        # Create workspace
        create_resp = test_client.post(
            "/api/workspaces/",
            headers=auth_headers,
            json={"name": "Detail Workspace"},
        )
        ws_id = create_resp.json()["id"]

        # Get detail
        response = test_client.get(
            f"/api/workspaces/{ws_id}", headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Detail Workspace"
        assert data["owner_id"] == str(test_user.id)
        assert "members" in data
        assert len(data["members"]) == 1
        assert data["members"][0]["role"] == "owner"
        assert data["members"][0]["user_id"] == str(test_user.id)
        assert "projects" in data
        assert data["projects"] == []

    def test_get_workspace_not_found(self, test_client, auth_headers):
        """Returns 404 for non-existent workspace"""
        fake_id = str(uuid.uuid4())
        response = test_client.get(
            f"/api/workspaces/{fake_id}", headers=auth_headers
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_workspace_invalid_id(self, test_client, auth_headers):
        """Returns 400 for invalid UUID"""
        response = test_client.get(
            "/api/workspaces/not-a-uuid", headers=auth_headers
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestUpdateWorkspace:
    """Test workspace update"""

    def test_update_workspace_name(self, test_client, auth_headers, test_user):
        """Owner can rename workspace"""
        # Create workspace
        create_resp = test_client.post(
            "/api/workspaces/",
            headers=auth_headers,
            json={"name": "Original Name"},
        )
        ws_id = create_resp.json()["id"]

        # Update
        response = test_client.put(
            f"/api/workspaces/{ws_id}",
            headers=auth_headers,
            json={"name": "Updated Name"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["id"] == ws_id

    def test_update_workspace_not_found(self, test_client, auth_headers):
        """Returns 404 for non-existent workspace"""
        fake_id = str(uuid.uuid4())
        response = test_client.put(
            f"/api/workspaces/{fake_id}",
            headers=auth_headers,
            json={"name": "New Name"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDeleteWorkspace:
    """Test workspace deletion"""

    def test_delete_workspace(self, test_client, auth_headers, test_user):
        """Owner can delete workspace, cascades to members"""
        # Create workspace
        create_resp = test_client.post(
            "/api/workspaces/",
            headers=auth_headers,
            json={"name": "To Delete"},
        )
        ws_id = create_resp.json()["id"]

        # Delete
        response = test_client.delete(
            f"/api/workspaces/{ws_id}", headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["message"] == "Workspace deleted successfully"
        assert data["workspace_id"] == ws_id

        # Verify it's gone
        get_resp = test_client.get(
            f"/api/workspaces/{ws_id}", headers=auth_headers
        )
        assert get_resp.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_workspace_not_found(self, test_client, auth_headers):
        """Returns 404 for non-existent workspace"""
        fake_id = str(uuid.uuid4())
        response = test_client.delete(
            f"/api/workspaces/{fake_id}", headers=auth_headers
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestNonOwnerPermissions:
    """Test that non-owners cannot perform owner-only actions"""

    def test_non_owner_cannot_delete(
        self, test_client, auth_headers, test_user, test_db_session
    ):
        """Non-owner gets 403 when trying to delete workspace"""
        import asyncio

        # Create workspace owned by a different user
        other_user_id = uuid.uuid4()

        async def create_other_workspace():
            from app.models import User

            other_user = User(
                id=other_user_id,
                email="other@example.com",
                workos_user_id="workos_other_001",
                email_verified=True,
                is_active=True,
            )
            test_db_session.add(other_user)
            await test_db_session.flush()

            workspace = Workspace(
                name="Other Owner Workspace",
                owner_id=other_user_id,
            )
            test_db_session.add(workspace)
            await test_db_session.flush()

            # Add test_user as a regular member (so they can see it)
            member = WorkspaceMember(
                workspace_id=workspace.id,
                user_id=test_user.id,
                role="member",
            )
            test_db_session.add(member)
            await test_db_session.commit()
            await test_db_session.refresh(workspace)
            return workspace

        workspace = asyncio.get_event_loop().run_until_complete(
            create_other_workspace()
        )

        # Attempt delete as non-owner
        response = test_client.delete(
            f"/api/workspaces/{workspace.id}", headers=auth_headers
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "owner" in response.json()["detail"].lower()

    def test_non_owner_cannot_update(
        self, test_client, auth_headers, test_user, test_db_session
    ):
        """Non-owner gets 403 when trying to update workspace"""
        import asyncio

        other_user_id = uuid.uuid4()

        async def create_other_workspace():
            from app.models import User

            other_user = User(
                id=other_user_id,
                email="other2@example.com",
                workos_user_id="workos_other_002",
                email_verified=True,
                is_active=True,
            )
            test_db_session.add(other_user)
            await test_db_session.flush()

            workspace = Workspace(
                name="Other Owner Workspace 2",
                owner_id=other_user_id,
            )
            test_db_session.add(workspace)
            await test_db_session.flush()

            # Add test_user as viewer
            member = WorkspaceMember(
                workspace_id=workspace.id,
                user_id=test_user.id,
                role="viewer",
            )
            test_db_session.add(member)
            await test_db_session.commit()
            await test_db_session.refresh(workspace)
            return workspace

        workspace = asyncio.get_event_loop().run_until_complete(
            create_other_workspace()
        )

        # Attempt update as non-owner
        response = test_client.put(
            f"/api/workspaces/{workspace.id}",
            headers=auth_headers,
            json={"name": "Hijacked Name"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "owner" in response.json()["detail"].lower()
