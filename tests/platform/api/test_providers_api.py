# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for provider and model catalog API endpoints."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

from app.platform.domain.config import AppConfig
from app.platform.domain.llm_catalog import LLMCatalogService
from app.platform.repo.llm_catalog_repository import LLMCatalogRepository


@pytest.fixture
def catalog(tmp_path):
    """Build a catalog service bound to a temporary JSON file."""
    repo = LLMCatalogRepository(path=tmp_path / "llm_models.json", data_dir=tmp_path)
    return LLMCatalogService(repo)


@contextmanager
def catalog_api(
    catalog,
    *,
    connection=(True, "Connection successful"),
    discover=(["gpt-4", "gpt-4o"], None),
    config=None,
):
    """Patch the config page and catalog probe collaborators for API tests."""
    with (
        patch(
            "app.platform.repo.config_composition.get_default_catalog_service",
            return_value=catalog,
        ),
        patch(
            "app.platform.queries.llm_page.get_default_catalog_service",
            return_value=catalog,
        ),
        patch(
            "app.platform.queries.platform_page.get_default_catalog_service",
            return_value=catalog,
        ),
        patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=config,
        ),
        patch(
            "app.platform.domain.config.ConfigService.test_connection",
            new=AsyncMock(return_value=connection),
        ),
        patch(
            "app.platform.domain.config.ConfigService.test_model",
            new=AsyncMock(return_value=connection),
        ),
        patch(
            "app.platform.domain.config.ConfigService.discover_models",
            new=AsyncMock(return_value=discover),
        ),
    ):
        yield


def _provider_body(**overrides):
    """Build a valid provider JSON payload."""
    data = {
        "display_name": "Cloud",
        "base_url": "https://api.example.com/v1",
    }
    data.update(overrides)
    return data


def _model_body(**overrides):
    """Build a valid model JSON payload."""
    data = {"display_name": "Cloud model", "model": "gpt-4"}
    data.update(overrides)
    return data


class TestProviderEndpoints:
    """Tests for provider CRUD endpoints."""

    def test_config_page_lists_providers_and_models(self, client, catalog):
        """GET /api/config exposes providers with their models."""
        provider = catalog.create_provider(
            display_name="Cloud",
            base_url="https://api.example.com/v1",
            api_key="secret",
        )
        catalog.add_model(provider.id, display_name="Cloud model", model="gpt-4")

        with catalog_api(catalog):
            response = client.get("/api/config")

        assert response.status_code == 200
        providers = response.json()["llm_providers"]
        assert providers == [
            {
                "id": provider.id,
                "display_name": "Cloud",
                "base_url": "https://api.example.com/v1",
                "provider_type": "openai-compatible",
                "has_api_key": True,
                "discovery_error": None,
                "models": [
                    {
                        "id": "cloud-model",
                        "provider_id": provider.id,
                        "display_name": "Cloud model",
                        "model": "gpt-4",
                        "accepts_audio_input": False,
                    }
                ],
            }
        ]

    def test_create_provider(self, client, catalog):
        """POST /api/config/providers persists the provider and imports models."""
        with catalog_api(catalog):
            response = client.post(
                "/api/config/providers", json=_provider_body(api_key="secret")
            )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert data["message"] == "Added provider 'Cloud' — imported 2 models."
        page_provider = data["page"]["llm_providers"][0]
        assert page_provider["has_api_key"] is True
        assert page_provider["discovery_error"] is None
        assert [item["model"] for item in page_provider["models"]] == [
            "gpt-4",
            "gpt-4o",
        ]
        assert catalog.load_catalog().providers["api-example-com"].api_key == "secret"

    def test_create_provider_marks_discovery_failure(self, client, catalog):
        """A failed discovery still saves the provider and marks the card."""
        with catalog_api(catalog, discover=([], "Unauthorized")):
            response = client.post("/api/config/providers", json=_provider_body())

        data = response.json()
        assert data["error"] is None
        assert "Could not load models" in data["message"]
        assert "Unauthorized" in data["page"]["llm_providers"][0]["discovery_error"]

    def test_create_provider_reports_probe_failure(self, client, catalog):
        """A failed probe returns an error and persists nothing."""
        with catalog_api(catalog, connection=(False, "Unauthorized")):
            response = client.post("/api/config/providers", json=_provider_body())

        data = response.json()
        assert "Unauthorized" in data["error"]
        assert "may require an API key" in data["error"]
        assert catalog.load_catalog().providers == {}

    def test_create_provider_rejects_duplicate_url(self, client, catalog):
        """A second provider for the same endpoint is rejected."""
        catalog.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )

        with catalog_api(catalog):
            response = client.post("/api/config/providers", json=_provider_body())

        assert "already exists" in response.json()["error"]

    def test_update_provider(self, client, catalog):
        """PUT /api/config/providers/{id} updates and re-probes details."""
        provider = catalog.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )

        with catalog_api(catalog):
            response = client.put(
                f"/api/config/providers/{provider.id}",
                json=_provider_body(
                    display_name="Cloud API",
                    base_url="https://api.example.com/v2",
                    api_key="secret",
                ),
            )

        data = response.json()
        assert data["error"] is None
        updated = catalog.get_provider(provider.id)
        assert updated.display_name == "Cloud API"
        assert updated.base_url == "https://api.example.com/v2"
        assert updated.api_key == "secret"

    def test_update_provider_unknown(self, client, catalog):
        """Unknown provider ids are reported as an error."""
        with catalog_api(catalog):
            response = client.put(
                "/api/config/providers/missing", json=_provider_body()
            )

        assert response.json()["error"] == "Unknown LLM provider: missing"

    def test_delete_provider_removes_models_and_resets_selection(self, client, catalog):
        """DELETE removes the provider, its models, and a stale selection."""
        provider = catalog.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )
        entry = catalog.add_model(
            provider.id, display_name="Cloud model", model="gpt-4"
        )
        config = AppConfig(llm_preset_id=entry.id)

        with catalog_api(catalog, config=config):
            response = client.delete(f"/api/config/providers/{provider.id}")

        data = response.json()
        assert data["message"] == "Provider removed."
        assert data["page"]["llm_providers"] == []
        assert data["page"]["llm_presets"] == []
        assert data["page"]["selected_llm_preset_id"] is None
        assert catalog.load_catalog().providers == {}


class TestModelEndpoints:
    """Tests for model CRUD endpoints under a provider."""

    def test_add_model(self, client, catalog):
        """POST /providers/{id}/models probes and saves the model."""
        provider = catalog.create_provider(
            display_name="Cloud",
            base_url="https://api.example.com/v1",
            api_key="secret",
        )

        with catalog_api(catalog):
            response = client.post(
                f"/api/config/providers/{provider.id}/models",
                json=_model_body(accepts_audio_input=True),
            )

        data = response.json()
        assert data["error"] is None
        assert data["message"] == "Added model 'Cloud model'."
        models = data["page"]["llm_providers"][0]["models"]
        assert models[0]["accepts_audio_input"] is True
        assert data["page"]["selected_llm_preset_id"] == models[0]["id"]

    def test_add_model_probe_failure(self, client, catalog):
        """A failed model probe returns an error and saves nothing."""
        provider = catalog.create_provider(
            display_name="Cloud",
            base_url="https://api.example.com/v1",
            api_key="secret",
        )

        with catalog_api(catalog, connection=(False, "Model not found")):
            response = client.post(
                f"/api/config/providers/{provider.id}/models",
                json=_model_body(),
            )

        data = response.json()
        assert data["error"] == "Model not found"
        assert catalog.load_catalog().models == {}

    def test_update_model(self, client, catalog):
        """PUT updates model fields."""
        provider = catalog.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )
        entry = catalog.add_model(provider.id, display_name="Cloud", model="gpt-4")

        with catalog_api(catalog):
            response = client.put(
                f"/api/config/providers/{provider.id}/models/{entry.id}",
                json=_model_body(display_name="Cloud Audio", model="gpt-4o-audio"),
            )

        data = response.json()
        assert data["message"] == "Saved model 'Cloud Audio'."
        assert catalog.get_model(entry.id).model == "gpt-4o-audio"

    def test_delete_model(self, client, catalog):
        """DELETE removes a model and clears the selection."""
        provider = catalog.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )
        entry = catalog.add_model(provider.id, display_name="Cloud", model="gpt-4")

        with catalog_api(catalog):
            response = client.delete(
                f"/api/config/providers/{provider.id}/models/{entry.id}"
            )

        data = response.json()
        assert data["message"] == "Model removed."
        assert data["page"]["selected_llm_preset_id"] is None
        assert catalog.get_model(entry.id) is None

    def test_delete_model_from_foreign_provider(self, client, catalog):
        """A provider cannot delete a model that belongs to another provider."""
        first = catalog.create_provider(
            display_name="One", base_url="https://one.example.com/v1"
        )
        second = catalog.create_provider(
            display_name="Two", base_url="https://two.example.com/v1"
        )
        entry = catalog.add_model(first.id, display_name="One", model="gpt-4")

        with catalog_api(catalog):
            response = client.delete(
                f"/api/config/providers/{second.id}/models/{entry.id}"
            )

        assert response.json()["error"] == f"Unknown LLM model: {entry.id}"
        assert catalog.get_model(entry.id) is not None


class TestDiscoverEndpoint:
    """Tests for provider model discovery."""

    def test_discover_models(self, client, catalog):
        """Discovery returns the model ids reported by the endpoint."""
        provider = catalog.create_provider(
            display_name="Cloud",
            base_url="https://api.example.com/v1",
            api_key="secret",
        )

        with catalog_api(catalog):
            response = client.post(
                f"/api/config/providers/{provider.id}/discover-models"
            )

        assert response.json() == {"models": ["gpt-4", "gpt-4o"], "error": None}

    def test_discover_models_reports_error(self, client, catalog):
        """A discovery failure returns an error message."""
        provider = catalog.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )

        with catalog_api(catalog, discover=([], "Unauthorized")):
            response = client.post(
                f"/api/config/providers/{provider.id}/discover-models"
            )

        data = response.json()
        assert data["models"] == []
        assert "Unauthorized" in data["error"]
        assert "may require an API key" in data["error"]

    def test_discover_unknown_provider(self, client, catalog):
        """Unknown provider ids are reported."""
        with catalog_api(catalog):
            response = client.post("/api/config/providers/missing/discover-models")

        assert response.json()["error"] == "Unknown LLM provider: missing"

    def test_import_models(self, client, catalog):
        """POST import-models adds every unknown model and returns a page."""
        provider = catalog.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )
        catalog.add_model(provider.id, display_name="Cloud model", model="gpt-4")

        with catalog_api(catalog):
            response = client.post(
                f"/api/config/providers/{provider.id}/import-models"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert data["message"] == "Imported 1 model from 'Cloud'."
        page_models = data["page"]["llm_providers"][0]["models"]
        assert sorted(item["model"] for item in page_models) == ["gpt-4", "gpt-4o"]
        assert all(not item["accepts_audio_input"] for item in page_models)

    def test_import_models_failure_marks_provider(self, client, catalog):
        """A failed import returns an error and marks the provider card."""
        provider = catalog.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )

        with catalog_api(catalog, discover=([], "Unauthorized")):
            response = client.post(
                f"/api/config/providers/{provider.id}/import-models"
            )

        data = response.json()
        assert "Unauthorized" in data["error"]
        assert "Unauthorized" in data["page"]["llm_providers"][0]["discovery_error"]

    def test_import_unknown_provider(self, client, catalog):
        """Unknown provider ids are reported."""
        with catalog_api(catalog):
            response = client.post("/api/config/providers/missing/import-models")

        assert response.json()["error"] == "Unknown LLM provider: missing"

    def test_set_model_audio_input(self, client, catalog):
        """PATCH on a model toggles its audio-input flag."""
        provider = catalog.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )
        entry = catalog.add_model(provider.id, display_name="Cloud model", model="gpt-4")

        with catalog_api(catalog):
            response = client.patch(
                f"/api/config/providers/{provider.id}/models/{entry.id}",
                json={"accepts_audio_input": True},
            )

        assert response.status_code == 200
        assert response.json()["error"] is None
        page_models = response.json()["page"]["llm_providers"][0]["models"]
        assert page_models[0]["accepts_audio_input"] is True

    def test_set_model_audio_input_unknown_model(self, client, catalog):
        """PATCH on an unknown model id is reported."""
        provider = catalog.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )

        with catalog_api(catalog):
            response = client.patch(
                f"/api/config/providers/{provider.id}/models/missing",
                json={"accepts_audio_input": True},
            )

        assert "Unknown LLM model" in response.json()["error"]
