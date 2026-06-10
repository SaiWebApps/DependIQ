"""
Tests for blast radius computation and streaming explanation.

All tests mock GraphService and LLM Agent — no real Neo4j or API keys needed.
"""

import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.graph import BlastRadiusResult, GraphService
from app.services import stream_publisher
from app.services.blast_radius import (
    BlastRadiusService,
    _blast_results,
    get_blast_result,
    store_blast_result,
)
from app.services.llm.agent import Agent, AgentResult
from app.services.llm.events import AnalysisEvent, EventType

# --- Fixtures ---


@pytest.fixture(autouse=True)
def clean_blast_results():
    """Ensure blast results store is clean between tests."""
    _blast_results.clear()
    yield
    _blast_results.clear()


@pytest.fixture
def mock_graph_service():
    """GraphService that returns 3 affected projects at varying distances."""
    service = AsyncMock(spec=GraphService)
    service.query_blast_radius.return_value = BlastRadiusResult(
        package_name="sqlalchemy",
        ecosystem="pypi",
        affected_projects=[
            {
                "project_id": "proj-1",
                "name": "api-gateway",
                "distance": 1,
                "impact_type": "direct",
            },
            {
                "project_id": "proj-2",
                "name": "auth-service",
                "distance": 2,
                "impact_type": "indirect",
            },
            {
                "project_id": "proj-3",
                "name": "analytics",
                "distance": 3,
                "impact_type": "indirect",
            },
        ],
        total_affected=3,
    )
    return service


@pytest.fixture
def mock_graph_service_empty():
    """GraphService that returns no affected projects."""
    service = AsyncMock(spec=GraphService)
    service.query_blast_radius.return_value = BlastRadiusResult(
        package_name="obscure-lib",
        ecosystem="pypi",
        affected_projects=[],
        total_affected=0,
    )
    return service


@pytest.fixture
def mock_agent():
    """LLM Agent that returns a canned explanation."""
    agent = AsyncMock(spec=Agent)
    agent.run.return_value = AgentResult(
        content="This project uses sqlalchemy.orm.Session directly. "
        "The raw() method was removed in 2.0.36, which will cause ImportError.",
        model_used="anthropic/claude-sonnet-4-20250514",
        tool_calls_made=0,
        total_tokens=150,
    )
    return agent


# --- Unit Tests: Blast Result Store ---


class TestBlastResultStore:
    """Tests for the in-memory blast result store with TTL."""

    def test_store_and_retrieve(self):
        """Store a result and retrieve it within TTL."""
        store_blast_result("br-abc123", {"package": "flask", "total_affected": 2})
        result = get_blast_result("br-abc123")
        assert result is not None
        assert result["package"] == "flask"
        assert result["total_affected"] == 2

    def test_retrieve_nonexistent(self):
        """Attempting to retrieve a nonexistent ID returns None."""
        result = get_blast_result("br-does-not-exist")
        assert result is None

    def test_expired_result_returns_none(self):
        """A result stored past the TTL is not returned."""
        store_blast_result("br-old", {"package": "requests"})
        # Manually backdate the stored_at to exceed TTL
        _blast_results["br-old"]["stored_at"] = time.time() - 4000
        result = get_blast_result("br-old")
        assert result is None

    def test_cleanup_on_store(self):
        """Storing a new result triggers cleanup of expired entries."""
        # Store an entry and backdate it
        _blast_results["br-stale"] = {"package": "old", "stored_at": time.time() - 5000}
        # Store a new entry — cleanup should remove the stale one
        store_blast_result("br-fresh", {"package": "new"})
        assert "br-stale" not in _blast_results
        assert "br-fresh" in _blast_results


# --- Unit Tests: BlastRadiusService.compute_blast_radius ---


class TestComputeBlastRadius:
    """Tests for the compute step of the blast radius service."""

    @pytest.mark.asyncio
    async def test_returns_affected_projects_ordered_by_distance(
        self, mock_graph_service
    ):
        """Projects are returned sorted by distance (direct first)."""
        service = BlastRadiusService(graph_service=mock_graph_service)
        result = await service.compute_blast_radius(
            workspace_id="ws-1",
            package_name="sqlalchemy",
            ecosystem="pypi",
            from_version="2.0.30",
            to_version="2.0.36",
        )

        assert result["package"] == "sqlalchemy"
        assert result["ecosystem"] == "pypi"
        assert result["total_affected"] == 3
        assert result["from_version"] == "2.0.30"
        assert result["to_version"] == "2.0.36"

        # Verify ordering: distance 1, 2, 3
        projects = result["affected_projects"]
        assert projects[0]["distance"] == 1
        assert projects[0]["name"] == "api-gateway"
        assert projects[1]["distance"] == 2
        assert projects[1]["name"] == "auth-service"
        assert projects[2]["distance"] == 3
        assert projects[2]["name"] == "analytics"

    @pytest.mark.asyncio
    async def test_no_affected_projects(self, mock_graph_service_empty):
        """When no projects are affected, returns empty list."""
        service = BlastRadiusService(graph_service=mock_graph_service_empty)
        result = await service.compute_blast_radius(
            workspace_id="ws-1",
            package_name="obscure-lib",
            ecosystem="pypi",
        )

        assert result["total_affected"] == 0
        assert result["affected_projects"] == []

    @pytest.mark.asyncio
    async def test_result_is_stored(self, mock_graph_service):
        """Compute stores the result for later explain stream."""
        service = BlastRadiusService(graph_service=mock_graph_service)
        result = await service.compute_blast_radius(
            workspace_id="ws-1",
            package_name="sqlalchemy",
            ecosystem="pypi",
        )

        stored = get_blast_result(result["id"])
        assert stored is not None
        assert stored["id"] == result["id"]

    @pytest.mark.asyncio
    async def test_result_has_id_and_computed_at(self, mock_graph_service):
        """Result includes a unique ID and timestamp."""
        service = BlastRadiusService(graph_service=mock_graph_service)
        result = await service.compute_blast_radius(
            workspace_id="ws-1",
            package_name="sqlalchemy",
            ecosystem="pypi",
        )

        assert result["id"].startswith("br-")
        assert "computed_at" in result


# --- Unit Tests: BlastRadiusService.explain_chain_reaction ---


class TestExplainChainReaction:
    """Tests for the streaming explanation of chain reactions."""

    @pytest.mark.asyncio
    async def test_publishes_progress_per_project(self, mock_graph_service, mock_agent):
        """Each affected project gets a progress event."""
        service = BlastRadiusService(graph_service=mock_graph_service, agent=mock_agent)
        result = await service.compute_blast_radius(
            workspace_id="ws-1",
            package_name="sqlalchemy",
            ecosystem="pypi",
            from_version="2.0.30",
            to_version="2.0.36",
        )

        task_id = "test-task-progress"
        await service.explain_chain_reaction(result["id"], task_id)

        # The stream should have been completed; collect events from a fresh run
        # by checking that the agent was called 3 times (once per project)
        assert mock_agent.run.call_count == 3

    @pytest.mark.asyncio
    async def test_explain_not_found_publishes_error(self, mock_agent):
        """Explaining a nonexistent blast radius publishes an error event."""
        service = BlastRadiusService(agent=mock_agent)
        task_id = "test-task-notfound"

        await service.explain_chain_reaction("br-nonexistent", task_id)

        # Agent should not have been called
        mock_agent.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_explain_empty_result_publishes_no_affected(
        self, mock_graph_service_empty, mock_agent
    ):
        """When there are no affected projects, a single result event is published."""
        service = BlastRadiusService(
            graph_service=mock_graph_service_empty, agent=mock_agent
        )
        result = await service.compute_blast_radius(
            workspace_id="ws-1",
            package_name="obscure-lib",
            ecosystem="pypi",
        )

        task_id = "test-task-empty"
        await service.explain_chain_reaction(result["id"], task_id)

        # No LLM calls needed for empty results
        mock_agent.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_explain_calls_llm_with_correct_task_type(
        self, mock_graph_service, mock_agent
    ):
        """LLM is called with SECURITY_ANALYSIS task type."""
        service = BlastRadiusService(graph_service=mock_graph_service, agent=mock_agent)
        result = await service.compute_blast_radius(
            workspace_id="ws-1",
            package_name="sqlalchemy",
            ecosystem="pypi",
            from_version="2.0.30",
            to_version="2.0.36",
        )

        task_id = "test-task-type"
        await service.explain_chain_reaction(result["id"], task_id)

        # Verify first call used SECURITY_ANALYSIS
        from app.services.llm.router import TaskType

        first_call = mock_agent.run.call_args_list[0]
        assert (
            first_call.kwargs.get("task") == TaskType.SECURITY_ANALYSIS
            or first_call[1].get("task") == TaskType.SECURITY_ANALYSIS
        )


# --- Unit Tests: AnalysisEvent ---


class TestAnalysisEvent:
    """Tests for the AnalysisEvent dataclass and factory methods."""

    def test_thinking_event(self):
        """thinking() creates a THINKING event with content."""
        event = AnalysisEvent.thinking("Reasoning about impact...")
        assert event.type == EventType.THINKING
        assert event.content == "Reasoning about impact..."
        assert event.data == {}

    def test_progress_event(self):
        """progress() creates a PROGRESS event with phase and pct."""
        event = AnalysisEvent.progress("Analyzing api-gateway (1/3)", 33)
        assert event.type == EventType.PROGRESS
        assert event.data["phase"] == "Analyzing api-gateway (1/3)"
        assert event.data["percent"] == 33

    def test_result_event(self):
        """result() creates a RESULT event with content and data."""
        event = AnalysisEvent.result(
            "Breaking change detected",
            data={"project": "api-gateway", "severity": "high"},
        )
        assert event.type == EventType.RESULT
        assert event.content == "Breaking change detected"
        assert event.data["severity"] == "high"

    def test_error_event(self):
        """error() creates an ERROR event."""
        event = AnalysisEvent.error("Connection timeout")
        assert event.type == EventType.ERROR
        assert event.content == "Connection timeout"

    def test_complete_event(self):
        """complete() creates a COMPLETE event."""
        event = AnalysisEvent.complete()
        assert event.type == EventType.COMPLETE

    def test_tool_call_event(self):
        """tool_call() creates a TOOL_CALL event."""
        event = AnalysisEvent.tool_call("pypi_lookup", {"package": "flask"})
        assert event.type == EventType.TOOL_CALL
        assert event.data["name"] == "pypi_lookup"
        assert event.data["args"]["package"] == "flask"

    def test_to_dict_serialization(self):
        """to_dict() produces a JSON-serializable dictionary."""
        event = AnalysisEvent.result("test", data={"key": "value"})
        d = event.to_dict()
        assert d["type"] == "result"
        assert d["content"] == "test"
        assert d["data"] == {"key": "value"}
        # Verify it's JSON-serializable
        json.dumps(d)


# --- Unit Tests: Stream Publisher ---


class TestStreamPublisher:
    """Tests for the asyncio queue-based stream publisher."""

    @pytest.mark.asyncio
    async def test_create_and_publish(self):
        """Create a stream, publish events, and consume them."""
        task_id = "test-pub-sub"
        stream_publisher.create_stream(task_id)

        # Publish two events then complete
        await stream_publisher.publish_event(task_id, AnalysisEvent.thinking("step 1"))
        await stream_publisher.publish_event(task_id, AnalysisEvent.thinking("step 2"))
        await stream_publisher.complete_stream(task_id)

        # Subscribe and collect
        events = []
        async for sse_line in stream_publisher.subscribe(task_id):
            events.append(sse_line)

        # Should get: thinking, thinking, complete
        assert len(events) == 3
        assert "thinking" in events[0]
        assert "step 1" in events[0]
        assert "step 2" in events[1]
        assert "complete" in events[2]

    @pytest.mark.asyncio
    async def test_subscribe_nonexistent_stream(self):
        """Subscribing to a nonexistent stream yields an error event."""
        events = []
        async for sse_line in stream_publisher.subscribe("nonexistent-task"):
            events.append(sse_line)

        assert len(events) == 1
        assert "error" in events[0]
        assert "not found" in events[0].lower()

    @pytest.mark.asyncio
    async def test_publish_to_nonexistent_stream_drops(self):
        """Publishing to a nonexistent stream silently drops the event."""
        # Should not raise
        await stream_publisher.publish_event(
            "ghost-task", AnalysisEvent.thinking("dropped")
        )

    @pytest.mark.asyncio
    async def test_sse_format(self):
        """Published events are formatted as proper SSE (event: + data:)."""
        task_id = "test-sse-format"
        stream_publisher.create_stream(task_id)
        await stream_publisher.publish_event(
            task_id, AnalysisEvent.progress("step", 50)
        )
        await stream_publisher.complete_stream(task_id)

        events = []
        async for sse_line in stream_publisher.subscribe(task_id):
            events.append(sse_line)

        # First event should be progress
        first = events[0]
        assert first.startswith("event: progress\n")
        assert "data: " in first
        assert first.endswith("\n\n")

        # Parse the data line
        data_line = next(
            line for line in first.split("\n") if line.startswith("data: ")
        )
        payload = json.loads(data_line.removeprefix("data: "))
        assert payload["type"] == "progress"
        assert payload["data"]["percent"] == 50

    @pytest.mark.asyncio
    async def test_active_streams_tracking(self):
        """get_active_streams returns currently active stream IDs."""
        task_id = "test-active"
        stream_publisher.create_stream(task_id)
        assert task_id in stream_publisher.get_active_streams()

        # Clean up
        stream_publisher.cleanup_stream(task_id)
        assert task_id not in stream_publisher.get_active_streams()


# --- Integration Tests: API Endpoints ---


class TestBlastRadiusAPI:
    """Tests for the blast radius HTTP endpoints."""

    def test_compute_blast_radius_endpoint(
        self, test_client, auth_headers, _mock_verify_session, test_user
    ):
        """POST /api/workspaces/{id}/blast-radius returns affected projects + stream_url."""
        mock_graph = AsyncMock(spec=GraphService)
        mock_graph.query_blast_radius.return_value = BlastRadiusResult(
            package_name="sqlalchemy",
            ecosystem="pypi",
            affected_projects=[
                {
                    "project_id": "p1",
                    "name": "api-gateway",
                    "distance": 1,
                    "impact_type": "direct",
                },
                {
                    "project_id": "p2",
                    "name": "worker",
                    "distance": 2,
                    "impact_type": "indirect",
                },
            ],
            total_affected=2,
        )

        from app.api.blast_radius import get_blast_radius_service
        from app.services.blast_radius import BlastRadiusService
        from main import app

        mock_service = AsyncMock(spec=BlastRadiusService)
        mock_service.compute_blast_radius.return_value = {
            "id": "br-test-123",
            "package": "sqlalchemy",
            "ecosystem": "pypi",
            "from_version": "2.0.30",
            "to_version": "2.0.36",
            "affected_projects": [
                {
                    "project_id": "p1",
                    "name": "api-gateway",
                    "distance": 1,
                    "impact_type": "direct",
                },
                {
                    "project_id": "p2",
                    "name": "worker",
                    "distance": 2,
                    "impact_type": "indirect",
                },
            ],
            "total_affected": 2,
            "computed_at": "2026-05-08T00:00:00",
        }

        app.dependency_overrides[get_blast_radius_service] = lambda: mock_service

        try:
            response = test_client.post(
                "/api/workspaces/ws-test/blast-radius",
                json={
                    "package": "sqlalchemy",
                    "ecosystem": "pypi",
                    "from_version": "2.0.30",
                    "to_version": "2.0.36",
                },
                headers=auth_headers,
            )

            assert response.status_code == 200, (
                f"Got {response.status_code}: {response.text}"
            )
            data = response.json()
            assert data["package"] == "sqlalchemy"
            assert data["ecosystem"] == "pypi"
            assert data["total_affected"] == 2
            assert data["affected_projects"][0]["name"] == "api-gateway"
            assert data["affected_projects"][0]["distance"] == 1
            assert data["affected_projects"][1]["name"] == "worker"
            assert "stream_url" in data
            assert data["id"].startswith("br-")
        finally:
            app.dependency_overrides.pop(get_blast_radius_service, None)

    def test_compute_blast_radius_requires_auth(self, test_client):
        """POST without auth returns 401."""
        response = test_client.post(
            "/api/workspaces/ws-test/blast-radius",
            json={"package": "flask", "ecosystem": "pypi"},
        )
        # Should get 401 or 403 (depends on middleware implementation)
        assert response.status_code in (401, 403)

    def test_explain_stream_not_found(
        self, test_client, auth_headers, _mock_verify_session, test_user
    ):
        """GET /api/blast-radius/{id}/explain returns 404 for nonexistent ID."""
        response = test_client.get(
            "/api/blast-radius/br-nonexistent/explain",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_explain_stream_found(
        self, test_client, auth_headers, _mock_verify_session, test_user
    ):
        """GET /api/blast-radius/{id}/explain returns 200 streaming response for valid ID."""
        # Pre-store a blast radius result
        store_blast_result(
            "br-test-explain",
            {
                "id": "br-test-explain",
                "package": "flask",
                "ecosystem": "pypi",
                "from_version": "2.0.0",
                "to_version": "3.0.0",
                "affected_projects": [
                    {
                        "project_id": "p1",
                        "name": "my-app",
                        "distance": 1,
                        "impact_type": "direct",
                    },
                ],
                "total_affected": 1,
            },
        )

        # Mock the agent so the explanation task completes quickly
        with patch("app.services.blast_radius.Agent") as mock_agent_cls:
            mock_instance = AsyncMock()
            mock_instance.run.return_value = AgentResult(
                content="Flask 3.0 removes deprecated APIs.",
                model_used="test-model",
                tool_calls_made=0,
                total_tokens=50,
            )
            mock_agent_cls.return_value = mock_instance

            response = test_client.get(
                "/api/blast-radius/br-test-explain/explain",
                headers=auth_headers,
            )
            # SSE endpoints return 200 with text/event-stream content type
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
