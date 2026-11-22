# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for ManageCatalogUseCase (probe + persist provider/model CRUD)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.platform.domain.llm_catalog import LLMCatalogService
from app.platform.repo.llm_catalog_repository import LLMCatalogRepository
from app.platform.schemas import LLMModelForm, LLMProviderForm
from app.platform.use_cases.manage_catalog import ManageCatalogUseCase


@pytest.fixture
def catalog_service(tmp_path):
    """Build a catalog service bound to a temporary JSON file."""
    repo = LLMCatalogRepository(path=tmp_path / "llm_models.json", data_dir=tmp_path)
    return LLMCatalogService(repo)


@pytest.fixture
def config_service():
    """Build a config service stub with successful probes."""
    service = MagicMock()
    service.get_config.return_value = None
    service.test_connection = AsyncMock(return_value=(True, "Connection successful"))
    service.test_model = AsyncMock(return_value=(True, "Connection successful"))
    service.discover_models = AsyncMock(return_value=(["gpt-4", "gpt-4o"], None))
    return service


@pytest.fixture
def use_case(config_service, catalog_service):
    """Build the manage-catalog use case with stubbed collaborators."""
    return ManageCatalogUseCase(config_service, catalog_service)


def _provider_form(**overrides):
    """Build a valid provider form payload."""
    data = {
        "display_name": "Cloud",
        "base_url": "https://api.example.com/v1",
    }
    data.update(overrides)
    return LLMProviderForm(**data)


def _model_form(**overrides):
    """Build a valid model form payload."""
    data = {"display_name": "Cloud model", "model": "gpt-4"}
    data.update(overrides)
    return LLMModelForm(**data)


class TestProviderActions:
    """Tests for provider create/update/delete through the use case."""

    @pytest.mark.asyncio
    async def test_create_provider_probes_and_persists(
        self, use_case, catalog_service, config_service
    ):
        """A successful probe persists the provider."""
        result = await use_case.create_provider(_provider_form(api_key="secret"))

        assert result.error is None
        assert result.message == "Added provider 'Cloud'."
        config_service.test_connection.assert_awaited_once()
        providers = catalog_service.load_catalog().providers
        assert providers["api-example-com"].api_key == "secret"

    @pytest.mark.asyncio
    async def test_create_provider_reports_probe_failure(
        self, use_case, catalog_service, config_service
    ):
        """A failed probe is surfaced with a key hint and nothing is saved."""
        config_service.test_connection.return_value = (False, "Unauthorized")

        result = await use_case.create_provider(_provider_form())

        assert result.message is None
        assert "Unauthorized" in result.error
        assert "may require an API key" in result.error
        assert catalog_service.load_catalog().providers == {}

    @pytest.mark.asyncio
    async def test_update_provider_skips_probe_when_unchanged(
        self, use_case, catalog_service, config_service
    ):
        """Renaming a provider without connection changes does not probe."""
        provider = catalog_service.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )

        result = await use_case.update_provider(
            provider.id,
            _provider_form(display_name="Cloud API"),
        )

        assert result.error is None
        config_service.test_connection.assert_not_awaited()
        assert catalog_service.get_provider(provider.id).display_name == "Cloud API"

    @pytest.mark.asyncio
    async def test_update_provider_probes_new_key(
        self, use_case, catalog_service, config_service
    ):
        """Changing the key re-probes the endpoint before saving."""
        provider = catalog_service.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )

        result = await use_case.update_provider(
            provider.id, _provider_form(api_key="new-secret")
        )

        assert result.error is None
        config_service.test_connection.assert_awaited_once()
        assert catalog_service.get_provider(provider.id).api_key == "new-secret"

    @pytest.mark.asyncio
    async def test_update_provider_rejects_unknown_id(self, use_case):
        """Unknown provider ids are reported instead of raising."""
        result = await use_case.update_provider("missing", _provider_form())

        assert result.error == "Unknown LLM provider: missing"

    def test_delete_provider(self, use_case, catalog_service):
        """Deleting a provider removes it from the catalog."""
        provider = catalog_service.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )

        result = use_case.delete_provider(provider.id)

        assert result.message == "Provider removed."
        assert catalog_service.load_catalog().providers == {}


class TestModelActions:
    """Tests for model add/update/delete through the use case."""

    @pytest.mark.asyncio
    async def test_add_model_probes_and_persists(
        self, use_case, catalog_service, config_service
    ):
        """A model is probed with its provider details, then saved."""
        provider = catalog_service.create_provider(
            display_name="Cloud",
            base_url="https://api.example.com/v1",
            api_key="secret",
        )

        result = await use_case.add_model(
            provider.id, _model_form(accepts_audio_input=True)
        )

        assert result.message == "Added model 'Cloud model'."
        probe = config_service.test_model.await_args.args[0]
        assert probe.base_url == "https://api.example.com/v1"
        assert probe.api_key == "secret"
        assert probe.accepts_audio_input is True
        entry = catalog_service.get_selected_model()
        assert entry is not None
        assert entry.provider_id == provider.id

    @pytest.mark.asyncio
    async def test_add_model_reports_probe_failure(
        self, use_case, catalog_service, config_service
    ):
        """A failed model probe does not persist the model."""
        provider = catalog_service.create_provider(
            display_name="Cloud",
            base_url="https://api.example.com/v1",
            api_key="secret",
        )
        config_service.test_model.return_value = (False, "Model not found")

        result = await use_case.add_model(provider.id, _model_form())

        assert result.error == "Model not found"
        assert catalog_service.get_selected_model() is None

    @pytest.mark.asyncio
    async def test_add_model_to_unknown_provider(self, use_case):
        """Unknown provider ids are reported before probing."""
        result = await use_case.add_model("missing", _model_form())

        assert result.error == "Unknown LLM provider: missing"

    @pytest.mark.asyncio
    async def test_update_model_probes_and_persists(
        self, use_case, catalog_service, config_service
    ):
        """Updating a model probes it before saving the new fields."""
        provider = catalog_service.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )
        entry = catalog_service.add_model(
            provider.id, display_name="Cloud", model="gpt-4"
        )

        result = await use_case.update_model(
            provider.id,
            entry.id,
            _model_form(display_name="Cloud Audio", model="gpt-4o-audio"),
        )

        assert result.message == "Saved model 'Cloud Audio'."
        assert catalog_service.get_model(entry.id).model == "gpt-4o-audio"

    def test_delete_model(self, use_case, catalog_service):
        """Deleting a model removes it and clears the selection."""
        provider = catalog_service.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )
        entry = catalog_service.add_model(
            provider.id, display_name="Cloud", model="gpt-4"
        )

        result = use_case.delete_model(provider.id, entry.id)

        assert result.message == "Model removed."
        assert catalog_service.get_model(entry.id) is None
        assert catalog_service.get_selected_model_id() is None

    def test_delete_model_rejects_a_foreign_provider(self, use_case, catalog_service):
        """A provider cannot delete a model that belongs to another provider."""
        first = catalog_service.create_provider(
            display_name="One", base_url="https://one.example.com/v1"
        )
        second = catalog_service.create_provider(
            display_name="Two", base_url="https://two.example.com/v1"
        )
        entry = catalog_service.add_model(first.id, display_name="One", model="gpt-4")

        result = use_case.delete_model(second.id, entry.id)

        assert result.error == f"Unknown LLM model: {entry.id}"
        assert catalog_service.get_model(entry.id) is not None


class TestDiscoverModels:
    """Tests for model discovery."""

    @pytest.mark.asyncio
    async def test_discover_uses_stored_provider_credentials(
        self, use_case, catalog_service, config_service
    ):
        """Discovery queries the provider endpoint with its stored key."""
        provider = catalog_service.create_provider(
            display_name="Cloud",
            base_url="https://api.example.com/v1",
            api_key="secret",
        )

        result = await use_case.discover_models(provider.id)

        assert result.models == ["gpt-4", "gpt-4o"]
        assert result.error is None
        kwargs = config_service.discover_models.await_args.kwargs
        assert kwargs["base_url"] == "https://api.example.com/v1"
        assert kwargs["api_key"] == "secret"

    @pytest.mark.asyncio
    async def test_discover_reports_error(
        self, use_case, catalog_service, config_service
    ):
        """A discovery failure is returned without raising."""
        provider = catalog_service.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )
        config_service.discover_models.return_value = ([], "Unauthorized")

        result = await use_case.discover_models(provider.id)

        assert result.models == []
        assert "Unauthorized" in result.error
        assert "may require an API key" in result.error

    @pytest.mark.asyncio
    async def test_discover_unknown_provider(self, use_case):
        """Unknown provider ids are reported."""
        result = await use_case.discover_models("missing")

        assert result.error == "Unknown LLM provider: missing"
