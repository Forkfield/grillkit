# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the LLM model catalog."""

import json
from unittest.mock import MagicMock

import pytest

from app.ai.llm_models import (
    CUSTOM_PRESET_ID,
    generate_model_id,
    generate_provider_id,
    normalize_model_id,
    provider_display_name_from_url,
    slugify_model_id,
)
from app.platform.domain.llm_catalog import LLMCatalogService
from app.platform.repo.llm_catalog_repository import LLMCatalogRepository
from app.platform.schemas import NewLLMModel


@pytest.fixture
def catalog_service(tmp_path):
    """Build a catalog service bound to a temporary JSON file."""
    repo = LLMCatalogRepository(path=tmp_path / "llm_models.json", data_dir=tmp_path)
    return LLMCatalogService(repo)


@pytest.fixture
def catalog_path(tmp_path):
    """Return the temporary catalog file path (shared with ``catalog_service``)."""
    return tmp_path / "llm_models.json"


class TestLLMCatalog:
    """Tests for catalog loading and model persistence."""

    def test_load_catalog_empty_when_file_missing(self, catalog_service):
        """Missing catalog file yields an empty catalog."""
        catalog = catalog_service.load_catalog()
        assert catalog.selected_id is None
        assert catalog.models == {}

    def test_add_user_model_persists_accepts_audio_input(
        self, catalog_service, catalog_path
    ):
        """Audio capability flag round-trips through llm_models.json."""
        entry = catalog_service.add_user_model(
            NewLLMModel(
                display_name="Audio API",
                base_url="https://api.example.com/v1",
                model="gpt-4o-audio",
                accepts_audio_input=True,
            )
        )
        assert entry.id == "audio-api"
        assert entry.accepts_audio_input is True
        saved = json.loads(catalog_path.read_text())
        assert saved["models"]["audio-api"]["accepts_audio_input"] is True

    def test_add_user_model_persists_api_key_on_provider(
        self, catalog_service, catalog_path
    ):
        """The API key is stored once on the provider that owns the model."""
        entry = catalog_service.add_user_model(
            NewLLMModel(
                display_name="Cloud API",
                base_url="https://api.example.com/v1",
                model="gpt-4",
                api_key="secret-key",
            )
        )
        assert entry.id == "cloud-api"
        assert entry.provider_id == "api-example-com"
        assert entry.api_key == "secret-key"
        saved = json.loads(catalog_path.read_text())
        assert "api_key" not in saved["models"]["cloud-api"]
        provider = saved["providers"]["api-example-com"]
        assert provider["api_key"] == "secret-key"
        assert provider["base_url"] == "https://api.example.com/v1"

    def test_add_user_model_sets_selected(self, catalog_service, catalog_path):
        """Adding a model selects it in llm_models.json."""
        catalog_service.add_user_model(
            NewLLMModel(
                display_name="Work API",
                base_url="http://192.168.1.10:11434/v1",
                model="deepseek-coder-v2:16b",
            )
        )
        saved = json.loads(catalog_path.read_text())
        assert saved["selected"] == "work-api"

    def test_add_user_model_generates_unique_id_for_duplicates(
        self, catalog_service, catalog_path
    ):
        """Duplicate display names get distinct auto-generated ids."""
        payload = NewLLMModel(
            display_name="Cloud",
            base_url="https://api.example.com/v1",
            model="gpt-4",
        )
        first = catalog_service.add_user_model(payload)
        second = catalog_service.add_user_model(payload)
        assert first.id == "cloud"
        assert second.id == "cloud-2"
        saved = json.loads(catalog_path.read_text())
        assert set(saved["models"]) == {"cloud", "cloud-2"}

    def test_normalize_model_id_rejects_custom(self, catalog_service):
        """Custom sentinel is not a valid catalog selection."""
        catalog = catalog_service.load_catalog()
        with pytest.raises(ValueError, match="Interview model is required"):
            normalize_model_id(CUSTOM_PRESET_ID, catalog)

    def test_normalize_model_id_rejects_unknown(self, catalog_service):
        """Unknown ids raise ValueError."""
        catalog = catalog_service.load_catalog()
        with pytest.raises(ValueError, match="Unsupported LLM model"):
            normalize_model_id("missing", catalog)

    def test_get_selected_model_reads_catalog_once(self, catalog_service):
        """Selecting the active model loads llm_models.json only once."""
        catalog_service.add_user_model(
            NewLLMModel(
                display_name="Cloud",
                base_url="https://api.example.com/v1",
                model="gpt-4",
            )
        )
        load = MagicMock(wraps=catalog_service.load_catalog)
        catalog_service.load_catalog = load

        entry = catalog_service.get_selected_model()

        assert entry is not None
        assert entry.id == "cloud"
        assert load.call_count == 1

    def test_get_model_strips_trailing_slash_from_base_url(
        self, catalog_service, catalog_path
    ):
        """Trailing slashes on base_url are normalized on read."""
        catalog_path.write_text(
            json.dumps(
                {
                    "selected": "local",
                    "models": {
                        "local": {
                            "display_name": "Local",
                            "provider_type": "openai-compatible",
                            "model": "gpt-4",
                            "base_url": "http://localhost:11434/v1/",
                            "api_key_required": False,
                        }
                    },
                }
            )
        )
        entry = catalog_service.get_model("local")
        assert entry is not None
        assert entry.base_url == "http://localhost:11434/v1"

    def test_legacy_catalog_is_grouped_into_providers(
        self, catalog_service, catalog_path
    ):
        """Legacy per-model entries are grouped by base URL on read."""
        catalog_path.write_text(
            json.dumps(
                {
                    "selected": "cloud-2",
                    "models": {
                        "cloud": {
                            "display_name": "Cloud",
                            "provider_type": "openai-compatible",
                            "model": "gpt-4",
                            "base_url": "https://api.example.com/v1",
                        },
                        "cloud-2": {
                            "display_name": "Cloud 2",
                            "provider_type": "openai-compatible",
                            "model": "gpt-4o",
                            "base_url": "https://api.example.com/v1/",
                            "api_key": "secret",
                        },
                    },
                }
            )
        )

        catalog = catalog_service.load_catalog()

        assert catalog.selected_id == "cloud-2"
        assert list(catalog.providers) == ["api-example-com"]
        assert catalog.models["cloud"].api_key == "secret"
        assert catalog.models["cloud-2"].api_key == "secret"
        assert catalog.models["cloud-2"].base_url == "https://api.example.com/v1"
        assert catalog.models["cloud"].provider_id == "api-example-com"

    def test_legacy_catalog_keeps_models_with_distinct_provider_types_apart(
        self, catalog_service, catalog_path
    ):
        """The same URL under two provider types becomes two providers."""
        catalog_path.write_text(
            json.dumps(
                {
                    "selected": "",
                    "models": {
                        "a": {
                            "display_name": "A",
                            "provider_type": "openai-compatible",
                            "model": "gpt-4",
                            "base_url": "http://localhost:11434/v1",
                        },
                        "b": {
                            "display_name": "B",
                            "provider_type": "other",
                            "model": "gpt-4",
                            "base_url": "http://localhost:11434/v1",
                        },
                    },
                }
            )
        )

        catalog = catalog_service.load_catalog()

        assert len(catalog.providers) == 2
        assert catalog.models["a"].provider_type == "openai-compatible"
        assert catalog.models["b"].provider_type == "other"

    def test_legacy_catalog_is_rewritten_in_provider_shape(
        self, catalog_service, catalog_path
    ):
        """The next mutation persists the migrated provider layout."""
        catalog_path.write_text(
            json.dumps(
                {
                    "selected": "cloud",
                    "models": {
                        "cloud": {
                            "display_name": "Cloud",
                            "provider_type": "openai-compatible",
                            "model": "gpt-4",
                            "base_url": "https://api.example.com/v1",
                            "api_key": "secret",
                            "api_key_required": True,
                        }
                    },
                }
            )
        )

        catalog_service.set_selected_model("cloud")

        saved = json.loads(catalog_path.read_text())
        assert saved["selected"] == "cloud"
        assert saved["providers"]["api-example-com"]["api_key"] == "secret"
        assert saved["models"]["cloud"] == {
            "provider_id": "api-example-com",
            "display_name": "Cloud",
            "model": "gpt-4",
            "accepts_audio_input": False,
        }

    def test_add_user_model_reuses_provider_for_same_base_url(
        self, catalog_service, catalog_path
    ):
        """Models on one endpoint share a single provider and its key."""
        first = catalog_service.add_user_model(
            NewLLMModel(
                display_name="Cloud",
                base_url="https://api.example.com/v1",
                model="gpt-4",
                api_key="secret",
            )
        )
        second = catalog_service.add_user_model(
            NewLLMModel(
                display_name="Cloud 2",
                base_url="https://api.example.com/v1/",
                model="gpt-4o",
            )
        )

        assert first.provider_id == second.provider_id == "api-example-com"
        saved = json.loads(catalog_path.read_text())
        assert list(saved["providers"]) == ["api-example-com"]
        assert second.api_key == "secret"

    def test_update_model_api_key_updates_the_shared_provider(
        self, catalog_service, catalog_path
    ):
        """A key update through one model is visible to its siblings."""
        first = catalog_service.add_user_model(
            NewLLMModel(
                display_name="Cloud",
                base_url="https://api.example.com/v1",
                model="gpt-4",
            )
        )
        catalog_service.add_user_model(
            NewLLMModel(
                display_name="Cloud 2",
                base_url="https://api.example.com/v1",
                model="gpt-4o",
            )
        )

        catalog_service.update_model_api_key("cloud", "rotated")

        assert catalog_service.get_model(first.id).api_key == "rotated"
        assert catalog_service.get_model("cloud-2").api_key == "rotated"
        saved = json.loads(catalog_path.read_text())
        assert saved["providers"]["api-example-com"]["api_key"] == "rotated"


class TestProviderManagement:
    """Tests for provider and model CRUD on the catalog service."""

    def test_create_provider_persists_details(self, catalog_service, catalog_path):
        """A provider stores its endpoint, key, and derived id."""
        provider = catalog_service.create_provider(
            display_name="Local Ollama",
            base_url="http://localhost:11434/v1/",
            api_key="secret",
        )

        assert provider.id == "localhost-11434"
        assert provider.base_url == "http://localhost:11434/v1"
        saved = json.loads(catalog_path.read_text())
        assert saved["providers"]["localhost-11434"] == {
            "display_name": "Local Ollama",
            "base_url": "http://localhost:11434/v1",
            "provider_type": "openai-compatible",
            "api_key": "secret",
        }

    def test_create_provider_rejects_duplicate_base_url(self, catalog_service):
        """Two providers cannot share one endpoint."""
        catalog_service.create_provider(
            display_name="One", base_url="https://api.example.com/v1"
        )

        with pytest.raises(ValueError, match="already exists"):
            catalog_service.create_provider(
                display_name="Two", base_url="https://api.example.com/v1/"
            )

    def test_update_provider_keeps_key_when_omitted(
        self, catalog_service, catalog_path
    ):
        """An update without a key leaves the stored key in place."""
        provider = catalog_service.create_provider(
            display_name="Cloud",
            base_url="https://api.example.com/v1",
            api_key="secret",
        )

        updated = catalog_service.update_provider(
            provider.id,
            display_name="Cloud API",
            base_url="https://api.example.com/v2",
        )

        assert updated.display_name == "Cloud API"
        assert updated.base_url == "https://api.example.com/v2"
        assert updated.api_key == "secret"
        saved = json.loads(catalog_path.read_text())
        assert saved["providers"][provider.id]["api_key"] == "secret"

    def test_update_provider_sets_and_clears_key(self, catalog_service):
        """A submitted key replaces the stored one; the flag removes it."""
        provider = catalog_service.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )

        catalog_service.update_provider(
            provider.id,
            display_name="Cloud",
            base_url="https://api.example.com/v1",
            api_key="secret",
        )
        assert catalog_service.get_provider(provider.id).api_key == "secret"

        catalog_service.update_provider(
            provider.id,
            display_name="Cloud",
            base_url="https://api.example.com/v1",
            clear_api_key=True,
        )
        assert catalog_service.get_provider(provider.id).api_key is None

    def test_add_model_links_provider_and_selects_it(self, catalog_service):
        """A new model references its provider and becomes selected."""
        provider = catalog_service.create_provider(
            display_name="Cloud",
            base_url="https://api.example.com/v1",
            api_key="secret",
        )

        entry = catalog_service.add_model(
            provider.id,
            display_name="Cloud Audio",
            model="gpt-4o-audio",
            accepts_audio_input=True,
        )

        assert entry.provider_id == provider.id
        assert entry.base_url == "https://api.example.com/v1"
        assert entry.api_key == "secret"
        assert entry.accepts_audio_input is True
        assert catalog_service.get_selected_model_id() == entry.id

    def test_add_model_rejects_unknown_provider(self, catalog_service):
        """Models cannot reference a provider that does not exist."""
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            catalog_service.add_model("missing", display_name="Ghost", model="gpt-4")

    def test_update_model_changes_fields(self, catalog_service):
        """Model labels, names, and flags are editable."""
        provider = catalog_service.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )
        entry = catalog_service.add_model(
            provider.id, display_name="Cloud", model="gpt-4"
        )

        updated = catalog_service.update_model(
            provider.id,
            entry.id,
            display_name="Cloud Audio",
            model="gpt-4o-audio",
            accepts_audio_input=True,
        )

        assert updated.display_name == "Cloud Audio"
        assert updated.model == "gpt-4o-audio"
        assert updated.accepts_audio_input is True

    def test_update_model_rejects_a_foreign_provider(self, catalog_service):
        """A provider cannot edit a model that belongs to another provider."""
        first = catalog_service.create_provider(
            display_name="One", base_url="https://one.example.com/v1"
        )
        second = catalog_service.create_provider(
            display_name="Two", base_url="https://two.example.com/v1"
        )
        entry = catalog_service.add_model(
            first.id, display_name="One model", model="gpt-4"
        )

        with pytest.raises(ValueError, match="Unknown LLM model"):
            catalog_service.update_model(
                second.id, entry.id, display_name="Nope", model="gpt-4"
            )

    def test_delete_model_resets_selection(self, catalog_service):
        """Removing the selected model clears the selection."""
        provider = catalog_service.create_provider(
            display_name="Cloud", base_url="https://api.example.com/v1"
        )
        entry = catalog_service.add_model(
            provider.id, display_name="Cloud", model="gpt-4"
        )

        assert catalog_service.delete_model(entry.id) is None
        assert catalog_service.get_model(entry.id) is None
        assert catalog_service.get_selected_model_id() is None

    def test_delete_provider_removes_its_models(self, catalog_service, catalog_path):
        """Deleting a provider drops only its models and clears the selection."""
        first = catalog_service.create_provider(
            display_name="One", base_url="https://one.example.com/v1"
        )
        second = catalog_service.create_provider(
            display_name="Two", base_url="https://two.example.com/v1"
        )
        kept = catalog_service.add_model(second.id, display_name="Kept", model="gpt-4")
        removed = catalog_service.add_model(
            first.id, display_name="Removed", model="gpt-4"
        )
        catalog_service.set_selected_model(removed.id)

        assert catalog_service.delete_provider(first.id) is None

        catalog = catalog_service.load_catalog()
        assert first.id not in catalog.providers
        assert set(catalog.models) == {kept.id}
        assert catalog.selected_id is None
        saved = json.loads(catalog_path.read_text())
        assert saved["selected"] == ""


class TestLLMModelHelpers:
    """Tests for id slugification and generation."""

    def test_slugify_model_id_normalizes_text(self):
        """Display names become lowercase hyphenated slugs."""
        assert slugify_model_id("  Work GPT-4!! ") == "work-gpt-4"

    def test_slugify_model_id_empty_for_symbols_only(self):
        """Names without usable characters yield an empty slug."""
        assert slugify_model_id("###") == ""

    def test_generate_model_id_falls_back_when_empty(self):
        """Empty slugs fall back to the default base id."""
        assert generate_model_id("###", set()) == "model"

    def test_generate_model_id_avoids_reserved_sentinel(self):
        """The reserved custom sentinel is never used verbatim."""
        assert generate_model_id("custom", set()) == f"{CUSTOM_PRESET_ID}-model"

    def test_generate_model_id_appends_suffix_on_collision(self):
        """Existing ids force a numeric suffix."""
        assert generate_model_id("Cloud", {"cloud", "cloud-2"}) == "cloud-3"

    def test_generate_provider_id_uses_url_host(self):
        """Provider ids are slugs of the base URL host."""
        assert generate_provider_id("https://api.example.com/v1", set()) == (
            "api-example-com"
        )

    def test_generate_provider_id_appends_suffix_on_collision(self):
        """Existing provider ids force a numeric suffix."""
        existing = {"api-example-com", "api-example-com-2"}
        assert generate_provider_id("https://api.example.com/v1", existing) == (
            "api-example-com-3"
        )

    def test_provider_display_name_falls_back_to_raw_url(self):
        """URLs without a host keep their raw form as the label."""
        assert provider_display_name_from_url("http://localhost") == "localhost"
        assert provider_display_name_from_url("not a url") == "not a url"
