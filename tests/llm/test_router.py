"""
Tests for the LLM model router.
"""

from app.services.llm.router import (
    COST_ROUTES,
    DEFAULT_ROUTES,
    LOCAL_ONLY_ROUTES,
    ModelRouter,
    RoutingMode,
    TaskType,
)


class TestTaskType:
    def test_all_task_types_have_routes(self):
        """Every TaskType must have an entry in all three route tables."""
        for task in TaskType:
            assert task in DEFAULT_ROUTES, f"{task} missing from DEFAULT_ROUTES"
            assert task in LOCAL_ONLY_ROUTES, f"{task} missing from LOCAL_ONLY_ROUTES"
            assert task in COST_ROUTES, f"{task} missing from COST_ROUTES"

    def test_all_routes_are_nonempty(self):
        """No route table should have empty chains."""
        for task in TaskType:
            assert len(DEFAULT_ROUTES[task]) > 0
            assert len(LOCAL_ONLY_ROUTES[task]) > 0
            assert len(COST_ROUTES[task]) > 0


class TestModelRouter:
    def test_default_mode_from_env(self, monkeypatch):
        monkeypatch.setenv("DEPENDIQ_ROUTING_MODE", "quality")
        router = ModelRouter()
        assert router.mode == RoutingMode.QUALITY

    def test_default_mode_balanced(self, monkeypatch):
        monkeypatch.setenv("DEPENDIQ_ROUTING_MODE", "balanced")
        router = ModelRouter()
        assert router.mode == RoutingMode.BALANCED

    def test_get_primary_model(self):
        router = ModelRouter(mode=RoutingMode.QUALITY)
        model = router.get_primary_model(TaskType.MANIFEST_PARSE)
        assert "haiku" in model or "mini" in model or "ollama" in model

    def test_get_primary_model_security(self):
        router = ModelRouter(mode=RoutingMode.QUALITY)
        model = router.get_primary_model(TaskType.SECURITY_ANALYSIS)
        assert "sonnet" in model or "gpt-4o" in model

    def test_get_fallbacks(self):
        router = ModelRouter(mode=RoutingMode.QUALITY)
        fallbacks = router.get_fallbacks(TaskType.VERSION_RESEARCH)
        assert len(fallbacks) >= 1

    def test_local_only_mode(self):
        router = ModelRouter(mode=RoutingMode.LOCAL_ONLY)
        for task in TaskType:
            chain = router.get_model_chain(task)
            for model in chain:
                assert model.startswith("ollama/"), (
                    f"Local-only mode should only use ollama models, got {model}"
                )

    def test_cost_mode_prefers_cheap(self):
        router = ModelRouter(mode=RoutingMode.COST)
        primary = router.get_primary_model(TaskType.MANIFEST_PARSE)
        assert "ollama" in primary or "haiku" in primary or "mini" in primary

    def test_custom_routes_override(self):
        custom = {TaskType.MANIFEST_PARSE: ["custom/my-model"]}
        router = ModelRouter(mode=RoutingMode.QUALITY, custom_routes=custom)
        chain = router.get_model_chain(TaskType.MANIFEST_PARSE)
        assert chain == ["custom/my-model"]

    def test_custom_routes_dont_affect_other_tasks(self):
        custom = {TaskType.MANIFEST_PARSE: ["custom/my-model"]}
        router = ModelRouter(mode=RoutingMode.QUALITY, custom_routes=custom)
        # Other tasks should still use default routes
        chain = router.get_model_chain(TaskType.SECURITY_ANALYSIS)
        assert chain == DEFAULT_ROUTES[TaskType.SECURITY_ANALYSIS]

    def test_get_config_structure(self):
        router = ModelRouter(mode=RoutingMode.BALANCED)
        config = router.get_config(TaskType.CODE_UPDATE)
        assert "model" in config
        assert "fallbacks" in config
        assert "temperature" in config
        assert "max_tokens" in config
        assert config["temperature"] == 0.0
        assert config["max_tokens"] == 8192  # heavy task

    def test_max_tokens_by_task_type(self):
        router = ModelRouter(mode=RoutingMode.BALANCED)
        assert router._max_tokens_for_task(TaskType.CODE_UPDATE) == 8192
        assert router._max_tokens_for_task(TaskType.MIGRATION_PLANNING) == 8192
        assert router._max_tokens_for_task(TaskType.SECURITY_ANALYSIS) == 4096
        assert router._max_tokens_for_task(TaskType.MANIFEST_PARSE) == 2048

    def test_available_providers_with_keys(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        router = ModelRouter()
        providers = router.available_providers()
        assert "anthropic" in providers
        assert "openai" in providers
        assert "ollama" in providers

    def test_available_providers_no_keys(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        router = ModelRouter()
        providers = router.available_providers()
        assert "anthropic" not in providers
        assert "openai" not in providers
        assert "ollama" in providers  # always available

    def test_filter_chain_by_available(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        router = ModelRouter(mode=RoutingMode.QUALITY)
        chain = router.filter_chain_by_available(TaskType.VERSION_RESEARCH)
        for model in chain:
            assert not model.startswith("openai/"), (
                f"OpenAI model {model} should be filtered out (no API key)"
            )


class TestRoutingModeValues:
    def test_all_modes_are_valid_strings(self):
        """Modes should be simple lowercase strings (usable as env var values)."""
        for mode in RoutingMode:
            assert mode.value == mode.value.lower()
            assert " " not in mode.value

    def test_model_ids_are_litellm_format(self):
        """All model IDs should be in provider/model format."""
        for table in [DEFAULT_ROUTES, LOCAL_ONLY_ROUTES, COST_ROUTES]:
            for task, chain in table.items():
                for model in chain:
                    assert "/" in model, (
                        f"Model '{model}' for {task} should be in 'provider/model' format"
                    )
