"""
Tests for Neo4j graph connection, service, and API endpoints.
All tests mock the Neo4j driver — no real Neo4j connection required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.graph.connection import close_neo4j, neo4j_health_check
from app.graph.service import (
    BlastRadiusResult,
    GraphDependency,
    GraphProject,
    GraphRelationship,
    GraphService,
    get_graph_service,
)

# ============================================================
# Helper: create a mock driver with correct session() pattern
# ============================================================


def _make_mock_driver(mock_session):
    """Create a mock AsyncDriver where session() is sync but returns an async CM.

    The real Neo4j AsyncDriver.session() is a synchronous method that returns
    an async context manager. We replicate that with a MagicMock that has
    __aenter__/__aexit__ configured.
    """
    driver = MagicMock()
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    driver.session.return_value = session_cm
    # close() is async on the real driver
    driver.close = AsyncMock()
    return driver


# ============================================================
# Fixtures
# ============================================================


@pytest_asyncio.fixture
async def mock_session():
    """Create a mock Neo4j async session."""
    session = AsyncMock()
    session.run = AsyncMock()
    return session


@pytest_asyncio.fixture
async def mock_driver(mock_session):
    """Create a mock Neo4j AsyncDriver with session wired up."""
    return _make_mock_driver(mock_session)


@pytest_asyncio.fixture
async def graph_service(mock_driver):
    """Create a GraphService with a mocked driver."""
    return GraphService(mock_driver)


# ============================================================
# Connection tests
# ============================================================


@pytest.mark.asyncio
async def test_neo4j_health_check_connected():
    """Health check returns connected when Neo4j responds with 1."""
    mock_record = MagicMock()
    mock_record.__getitem__ = MagicMock(return_value=1)

    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value=mock_record)

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)

    driver = _make_mock_driver(mock_session)

    with patch(
        "app.graph.connection.get_neo4j_driver",
        new_callable=AsyncMock,
        return_value=driver,
    ):
        result = await neo4j_health_check()

    assert result == {"status": "connected"}


@pytest.mark.asyncio
async def test_neo4j_health_check_disconnected():
    """Health check returns disconnected when Neo4j throws an exception."""
    with patch(
        "app.graph.connection.get_neo4j_driver",
        new_callable=AsyncMock,
        side_effect=Exception("Connection refused"),
    ):
        result = await neo4j_health_check()

    assert result["status"] == "disconnected"
    assert "Connection refused" in result["detail"]


@pytest.mark.asyncio
async def test_close_neo4j_when_driver_exists():
    """close_neo4j closes the driver and resets the global."""
    mock_driver = AsyncMock()
    mock_driver.close = AsyncMock()

    with patch("app.graph.connection._driver", mock_driver):
        await close_neo4j()

    mock_driver.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_neo4j_when_no_driver():
    """close_neo4j is a no-op when no driver exists."""
    with patch("app.graph.connection._driver", None):
        # Should not raise
        await close_neo4j()


# ============================================================
# GraphService.write_project
# ============================================================


@pytest.mark.asyncio
async def test_graph_service_write_project():
    """write_project calls MERGE with correct parameters."""
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    driver = _make_mock_driver(mock_session)

    service = GraphService(driver)
    project = GraphProject(
        id="proj-1",
        workspace_id="ws-1",
        tenant_id="tenant-1",
        name="my-project",
        language="python",
        summary="A test project",
    )

    await service.write_project(project)

    mock_session.run.assert_awaited_once()
    call_args = mock_session.run.call_args
    query = call_args[0][0]
    kwargs = call_args[1]

    assert "MERGE (p:Project {id: $id})" in query
    assert kwargs["id"] == "proj-1"
    assert kwargs["workspace_id"] == "ws-1"
    assert kwargs["tenant_id"] == "tenant-1"
    assert kwargs["name"] == "my-project"
    assert kwargs["language"] == "python"
    assert kwargs["summary"] == "A test project"


# ============================================================
# GraphService.write_dependencies
# ============================================================


@pytest.mark.asyncio
async def test_graph_service_write_dependencies():
    """write_dependencies creates DEPENDS_ON edges for each dep."""
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    driver = _make_mock_driver(mock_session)

    service = GraphService(driver)
    deps = [
        GraphDependency(
            project_id="proj-1",
            package_name="fastapi",
            ecosystem="pypi",
            version="0.111.0",
            is_direct=True,
        ),
        GraphDependency(
            project_id="proj-1",
            package_name="sqlalchemy",
            ecosystem="pypi",
            version="2.0.49",
            is_direct=True,
        ),
    ]

    await service.write_dependencies("proj-1", deps)

    assert mock_session.run.await_count == 2

    # Verify first call
    first_call = mock_session.run.call_args_list[0]
    query = first_call[0][0]
    kwargs = first_call[1]
    assert "MERGE (proj)-[r:DEPENDS_ON]->(pkg)" in query
    assert kwargs["project_id"] == "proj-1"
    assert kwargs["package_name"] == "fastapi"
    assert kwargs["ecosystem"] == "pypi"
    assert kwargs["version"] == "0.111.0"
    assert kwargs["is_direct"] is True

    # Verify second call
    second_call = mock_session.run.call_args_list[1]
    kwargs2 = second_call[1]
    assert kwargs2["package_name"] == "sqlalchemy"
    assert kwargs2["version"] == "2.0.49"


# ============================================================
# GraphService.write_relationship
# ============================================================


@pytest.mark.asyncio
async def test_graph_service_write_relationship():
    """write_relationship creates RELATES_TO edge between projects."""
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    driver = _make_mock_driver(mock_session)

    service = GraphService(driver)
    rel = GraphRelationship(
        source_project_id="proj-1",
        target_project_id="proj-2",
        relationship_type="imports_from",
        confidence=0.95,
        metadata={"module": "utils"},
    )

    await service.write_relationship(rel)

    mock_session.run.assert_awaited_once()
    call_args = mock_session.run.call_args
    query = call_args[0][0]
    kwargs = call_args[1]

    assert "MERGE (src)-[r:RELATES_TO]->(tgt)" in query
    assert kwargs["source_project_id"] == "proj-1"
    assert kwargs["target_project_id"] == "proj-2"
    assert kwargs["relationship_type"] == "imports_from"
    assert kwargs["confidence"] == 0.95
    assert "utils" in kwargs["metadata"]


# ============================================================
# GraphService.get_workspace_graph
# ============================================================


@pytest.mark.asyncio
async def test_graph_service_get_workspace_graph():
    """get_workspace_graph returns structured nodes and edges."""
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(
        return_value=[
            {
                "p": {
                    "id": "proj-1",
                    "name": "frontend",
                    "language": "typescript",
                    "workspace_id": "ws-1",
                },
                "deps": [
                    {
                        "pkg_name": "react",
                        "pkg_ecosystem": "npm",
                        "dep_version": "18.2.0",
                        "dep_is_direct": True,
                    }
                ],
                "rels": [
                    {
                        "target_id": "proj-2",
                        "rel_type": "calls_api",
                        "rel_confidence": 0.9,
                    }
                ],
            },
            {
                "p": {
                    "id": "proj-2",
                    "name": "backend",
                    "language": "python",
                    "workspace_id": "ws-1",
                },
                "deps": [
                    {
                        "pkg_name": "fastapi",
                        "pkg_ecosystem": "pypi",
                        "dep_version": "0.111.0",
                        "dep_is_direct": True,
                    }
                ],
                "rels": [{"target_id": None, "rel_type": None, "rel_confidence": None}],
            },
        ]
    )

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    driver = _make_mock_driver(mock_session)

    service = GraphService(driver)
    graph = await service.get_workspace_graph("ws-1")

    # Should have 2 project nodes + 2 package nodes
    project_nodes = [n for n in graph["nodes"] if n["type"] == "project"]
    package_nodes = [n for n in graph["nodes"] if n["type"] == "package"]
    assert len(project_nodes) == 2
    assert len(package_nodes) == 2

    # Should have 2 depends_on edges + 1 relationship edge
    depends_edges = [e for e in graph["edges"] if e["type"] == "depends_on"]
    rel_edges = [e for e in graph["edges"] if e["type"] == "calls_api"]
    assert len(depends_edges) == 2
    assert len(rel_edges) == 1

    # Verify edge structure
    react_edge = next(e for e in depends_edges if e["target"] == "npm:react")
    assert react_edge["source"] == "proj-1"
    assert react_edge["version"] == "18.2.0"

    api_edge = rel_edges[0]
    assert api_edge["source"] == "proj-1"
    assert api_edge["target"] == "proj-2"
    assert api_edge["confidence"] == 0.9


# ============================================================
# GraphService.query_blast_radius
# ============================================================


@pytest.mark.asyncio
async def test_graph_service_blast_radius():
    """query_blast_radius returns affected projects ordered by distance."""
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(
        return_value=[
            {
                "project": {"id": "proj-1", "name": "api-service"},
                "distance": 1,
                "impact_type": "direct",
            },
            {
                "project": {"id": "proj-2", "name": "web-frontend"},
                "distance": 2,
                "impact_type": "indirect",
            },
            {
                "project": {"id": "proj-3", "name": "mobile-app"},
                "distance": 3,
                "impact_type": "indirect",
            },
        ]
    )

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    driver = _make_mock_driver(mock_session)

    service = GraphService(driver)
    result = await service.query_blast_radius("ws-1", "requests", "pypi")

    assert isinstance(result, BlastRadiusResult)
    assert result.package_name == "requests"
    assert result.ecosystem == "pypi"
    assert result.total_affected == 3

    # Verify ordering by distance
    assert result.affected_projects[0]["distance"] == 1
    assert result.affected_projects[0]["impact_type"] == "direct"
    assert result.affected_projects[0]["name"] == "api-service"

    assert result.affected_projects[1]["distance"] == 2
    assert result.affected_projects[1]["impact_type"] == "indirect"

    assert result.affected_projects[2]["distance"] == 3


# ============================================================
# GraphService.clear_workspace
# ============================================================


@pytest.mark.asyncio
async def test_graph_service_clear_workspace():
    """clear_workspace runs DETACH DELETE on workspace projects."""
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    driver = _make_mock_driver(mock_session)

    service = GraphService(driver)
    await service.clear_workspace("ws-1")

    mock_session.run.assert_awaited_once()
    call_args = mock_session.run.call_args
    query = call_args[0][0]
    kwargs = call_args[1]

    assert "DETACH DELETE p" in query
    assert kwargs["workspace_id"] == "ws-1"


# ============================================================
# API endpoint tests
# ============================================================


@pytest.mark.asyncio
async def test_graph_api_get_workspace_graph(test_client, _mock_verify_session):
    """GET /api/workspaces/{id}/graph returns graph data."""
    mock_graph = {"nodes": [{"id": "p1", "type": "project"}], "edges": []}

    with patch("app.api.graph.get_graph_service") as mock_factory:
        mock_service = AsyncMock()
        mock_service.get_workspace_graph = AsyncMock(return_value=mock_graph)
        mock_factory.return_value = mock_service

        response = test_client.get(
            "/api/workspaces/ws-1/graph",
            cookies={"diq_session": "session_token_for_ci"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "p1"


@pytest.mark.asyncio
async def test_graph_api_blast_radius(test_client, _mock_verify_session):
    """POST /api/workspaces/{id}/blast-radius returns affected projects."""
    from app.api.blast_radius import get_blast_radius_service
    from app.services.blast_radius import BlastRadiusService
    from main import app

    mock_service = AsyncMock(spec=BlastRadiusService)
    mock_service.compute_blast_radius.return_value = {
        "id": "br-test-graph-001",
        "package": "lodash",
        "ecosystem": "npm",
        "from_version": None,
        "to_version": None,
        "affected_projects": [
            {
                "project_id": "proj-1",
                "name": "frontend",
                "distance": 1,
                "impact_type": "direct",
            }
        ],
        "total_affected": 1,
        "computed_at": "2026-05-08T00:00:00",
    }

    app.dependency_overrides[get_blast_radius_service] = lambda: mock_service

    try:
        response = test_client.post(
            "/api/workspaces/ws-1/blast-radius",
            json={"package": "lodash", "ecosystem": "npm"},
            cookies={"diq_session": "session_token_for_ci"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["package"] == "lodash"
        assert data["ecosystem"] == "npm"
        assert data["total_affected"] == 1
        assert data["affected_projects"][0]["name"] == "frontend"
        assert data["affected_projects"][0]["distance"] == 1
    finally:
        app.dependency_overrides.pop(get_blast_radius_service, None)


@pytest.mark.asyncio
async def test_graph_api_blast_radius_service_unavailable(
    test_client, _mock_verify_session
):
    """POST /api/workspaces/{id}/blast-radius returns 500 when service raises."""
    from app.api.blast_radius import get_blast_radius_service
    from app.services.blast_radius import BlastRadiusService
    from main import app

    mock_service = AsyncMock(spec=BlastRadiusService)
    mock_service.compute_blast_radius.side_effect = Exception(
        "Neo4j connection refused"
    )

    app.dependency_overrides[get_blast_radius_service] = lambda: mock_service

    try:
        response = test_client.post(
            "/api/workspaces/ws-1/blast-radius",
            json={"package": "lodash", "ecosystem": "npm"},
            cookies={"diq_session": "session_token_for_ci"},
        )

        assert response.status_code == 500
    finally:
        app.dependency_overrides.pop(get_blast_radius_service, None)


@pytest.mark.asyncio
async def test_graph_api_get_workspace_graph_service_unavailable(
    test_client, _mock_verify_session
):
    """GET /api/workspaces/{id}/graph returns 503 when graph is down."""
    with patch("app.api.graph.get_graph_service") as mock_factory:
        mock_factory.side_effect = Exception("Neo4j connection refused")

        response = test_client.get(
            "/api/workspaces/ws-1/graph",
            cookies={"diq_session": "session_token_for_ci"},
        )

    assert response.status_code == 503


# ============================================================
# get_graph_service factory
# ============================================================


@pytest.mark.asyncio
async def test_get_graph_service_factory():
    """get_graph_service returns a GraphService instance."""
    mock_driver = MagicMock()

    with patch(
        "app.graph.connection.get_neo4j_driver",
        new_callable=AsyncMock,
        return_value=mock_driver,
    ):
        service = await get_graph_service()

    assert isinstance(service, GraphService)
    assert service.driver is mock_driver
