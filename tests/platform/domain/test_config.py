# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for configuration service."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.base import AudioCapableProvider
from app.ai.llm_models import LLMModelEntry
from app.platform.domain.config import (
    CLEAR_API_KEY_MARKER,
    ApiKeyDecision,
    ApiKeyKind,
    AppConfig,
    ConfigService,
    provider_config_changed,
    resolve_api_key_from_form,
    resolve_tts_voice_id,
)
from app.platform.domain.effective_config import EffectiveModelConfig
from app.platform.domain.llm_catalog import LLMCatalogService
from app.platform.repo.config_repository import ConfigRepository
from app.platform.repo.llm_catalog_repository import LLMCatalogRepository
from app.platform.schemas import NewLLMModel


@pytest.fixture
def config_path(tmp_path):
    """Fixture for configuration file path."""
    test_config_path = tmp_path / "test_config.json"
    yield test_config_path
    if test_config_path.exists():
        test_config_path.unlink()


@pytest.fixture
def mock_provider_factory():
    """Fixture for mocking ProviderFactory."""
    with patch("app.platform.domain.config.ProviderFactory") as mock_factory:
        mock_provider = AsyncMock(spec=AudioCapableProvider)
        mock_provider.validate = AsyncMock(return_value=True)
        mock_provider.close = AsyncMock()
        mock_factory.from_effective.return_value = mock_provider
        yield mock_factory


class TestAppConfig:
    """Tests for AppConfig dataclass."""

    def test_effective_uses_catalog_base_url(self):
        """effective() resolves catalog model and base URL."""
        entry = LLMModelEntry(
            id="cloud",
            display_name="Cloud",
            provider_type="openai-compatible",
            model="gpt-4",
            base_url="https://api.example.com/v1",
            api_key_required=True,
            api_key="secret",
        )
        config = AppConfig(llm_preset_id="cloud", timeout=60.0)
        effective = ConfigService(
            ConfigRepository(), SimpleNamespace(get_model=lambda _m: entry)
        ).resolve_effective_config(config)
        assert isinstance(effective, EffectiveModelConfig)
        assert effective.base_url == "https://api.example.com/v1"
        assert effective.model == "gpt-4"
        assert effective.api_key == "secret"
        assert effective.timeout == 60.0

    def test_resolve_api_key_from_form_uses_catalog_key(self, monkeypatch):
        """Blank form values preserve API keys stored in the model catalog."""
        entry = LLMModelEntry(
            id="work",
            display_name="Work",
            provider_type="openai-compatible",
            model="gpt-4",
            base_url="https://api.example.com/v1",
            api_key_required=True,
            api_key="catalog-secret",
        )
        decision = resolve_api_key_from_form("", entry)
        assert decision.kind is ApiKeyKind.KEEP
        assert decision.value == "catalog-secret"

    def test_resolve_api_key_from_form_accepts_new_key(self):
        """Non-empty form value replaces the stored API key."""
        decision = resolve_api_key_from_form("new-key", None)
        assert decision.kind is ApiKeyKind.SET
        assert decision.value == "new-key"

    def test_resolve_api_key_from_form_clears_when_empty_and_no_catalog_key(
        self, monkeypatch
    ):
        """Empty form with no stored catalog key yields no API key."""
        entry = LLMModelEntry(
            id="work",
            display_name="Work",
            provider_type="openai-compatible",
            model="gpt-4",
            base_url="https://api.example.com/v1",
            api_key_required=False,
        )
        decision = resolve_api_key_from_form("", entry)
        assert decision.kind is ApiKeyKind.KEEP
        assert decision.value is None

    def test_resolve_api_key_from_form_clears_with_marker(self):
        """The explicit clear marker removes a stored API key."""
        entry = LLMModelEntry(
            id="work",
            display_name="Work",
            provider_type="openai-compatible",
            model="gpt-4",
            base_url="https://api.example.com/v1",
            api_key_required=True,
            api_key="catalog-secret",
        )
        decision = resolve_api_key_from_form(CLEAR_API_KEY_MARKER, entry)
        assert decision.kind is ApiKeyKind.CLEAR
        assert decision.value is None

    def test_resolve_tts_voice_keeps_chosen_voice_for_same_locale(self):
        """Same locale keeps the previously user-selected voice."""
        existing = AppConfig(locale="ru", tts_voice_id="ru_RU-dmitri-medium")
        assert resolve_tts_voice_id(existing, "ru") == "ru_RU-dmitri-medium"

    def test_resolve_tts_voice_defaults_on_locale_change(self):
        """Locale change falls back to the default voice for the new locale."""
        existing = AppConfig(locale="ru", tts_voice_id="ru_RU-dmitri-medium")
        assert resolve_tts_voice_id(existing, "en") == "en_US-lessac-medium"

    def test_resolve_tts_voice_defaults_without_existing_config(self):
        """No existing config uses the default voice for the locale."""
        assert resolve_tts_voice_id(None, "fr") == "fr_FR-siwis-medium"

    def _effective(self, **overrides) -> EffectiveModelConfig:
        base = {
            "provider_type": "openai-compatible",
            "base_url": "https://api.example.com/v1",
            "model": "gpt-4",
            "api_key": None,
            "timeout": 30.0,
        }
        base.update(overrides)
        return EffectiveModelConfig(**base)

    def test_provider_changed_with_no_previous_config(self):
        """Nothing saved yet always requires a probe."""
        assert provider_config_changed(None, self._effective()) is True

    def test_provider_unchanged_when_all_connectivity_fields_equal(self):
        """Identical provider fields do not require a probe."""
        previous = self._effective()
        proposed = self._effective()
        assert provider_config_changed(previous, proposed) is False

    def test_provider_changed_on_model_switch(self):
        """A different model name requires a probe."""
        previous = self._effective()
        proposed = self._effective(model="gpt-4o")
        assert provider_config_changed(previous, proposed) is True

    def test_provider_changed_on_base_url_change(self):
        """A different base URL requires a probe."""
        previous = self._effective()
        proposed = self._effective(base_url="https://other.example.com/v1")
        assert provider_config_changed(previous, proposed) is True

    def test_provider_changed_on_api_key_change(self):
        """A new API key requires a probe."""
        previous = self._effective()
        proposed = self._effective(api_key="sk-new")
        assert provider_config_changed(previous, proposed) is True

    def test_provider_unchanged_despite_timeout_change(self):
        """A timeout-only change does not require a probe."""
        previous = self._effective()
        proposed = self._effective(timeout=120.0)
        assert provider_config_changed(previous, proposed) is False


class TestConfigService:
    """Tests for ConfigService class."""

    @pytest.fixture
    def mock_config_path(self, tmp_path):
        """Fixture creating a temp config file and its catalog file.

        Returns:
            Path of the config file; the catalog lives next to it.
        """
        test_path = tmp_path / "test_config.json"
        catalog_path = tmp_path / "llm_models.json"
        catalog_path.write_text(
            json.dumps(
                {
                    "selected": "cloud",
                    "models": {
                        "cloud": {
                            "display_name": "Cloud",
                            "provider_type": "openai-compatible",
                            "model": "gpt-4",
                            "base_url": "http://localhost",
                            "api_key_required": True,
                            "api_key": "test_key",
                        }
                    },
                }
            )
        )
        return test_path

    def _build_catalog_service(self, data_dir):
        """Build a catalog service bound to the given temp directory."""
        return LLMCatalogService(
            LLMCatalogRepository(
                path=data_dir / "llm_models.json", data_dir=data_dir
            )
        )

    @pytest.fixture
    def config_service(self, mock_config_path):
        """Build a ConfigService bound to temp config and catalog repositories."""
        test_path = mock_config_path
        repo = ConfigRepository(path=test_path, data_dir=test_path.parent)
        return ConfigService(
            repo, self._build_catalog_service(test_path.parent)
        )

    def test_save_and_get_config(self, config_service, mock_config_path):
        """Test saving app settings and selected model."""
        _config_path = mock_config_path
        user_path = _config_path.parent / "llm_models.json"
        config = AppConfig(llm_preset_id="cloud")
        config_service.save_config(config)

        retrieved_config = config_service.get_config()
        assert retrieved_config is not None
        assert retrieved_config.llm_preset_id == "cloud"
        assert not hasattr(retrieved_config, "model")
        stored = json.loads(_config_path.read_text())
        assert "llm_preset_id" not in stored
        assert "base_url" not in stored
        llm_data = json.loads(user_path.read_text())
        assert llm_data["selected"] == "cloud"

    def test_save_config_clears_key_with_clear_decision(
        self, config_service, mock_config_path
    ):
        """A CLEAR decision removes the stored API key from the catalog."""
        user_path = mock_config_path.parent / "llm_models.json"
        config = AppConfig(llm_preset_id="cloud")

        config_service.save_config(
            config, ApiKeyDecision(ApiKeyKind.CLEAR)
        )

        stored = json.loads(user_path.read_text())
        assert "api_key" not in stored["models"]["cloud"]

    def test_save_config_keeps_key_when_decision_is_none(
        self, config_service, mock_config_path
    ):
        """Saving without a decision leaves the stored API key untouched."""
        user_path = mock_config_path.parent / "llm_models.json"
        config = AppConfig(llm_preset_id="cloud")

        config_service.save_config(config)

        stored = json.loads(user_path.read_text())
        assert stored["models"]["cloud"]["api_key"] == "test_key"

    def test_save_config_sets_key_with_set_decision(
        self, config_service, mock_config_path
    ):
        """A SET decision replaces the stored API key."""
        user_path = mock_config_path.parent / "llm_models.json"
        config = AppConfig(llm_preset_id="cloud")

        config_service.save_config(
            config, ApiKeyDecision(ApiKeyKind.SET, "new-secret")
        )

        stored = json.loads(user_path.read_text())
        assert stored["models"]["cloud"]["api_key"] == "new-secret"

    def test_get_config_no_file(self, config_service, mock_config_path):
        """Test retrieving config when file does not exist."""
        assert config_service.get_config() is None

    def test_load_active_returns_config_and_model_with_one_catalog_read(
        self, tmp_path
    ):
        """load_active returns the selected entry without re-reading the catalog."""
        data_dir = tmp_path
        catalog_repo = LLMCatalogRepository(
            path=data_dir / "llm_models.json", data_dir=data_dir
        )
        catalog = LLMCatalogService(catalog_repo)
        _ = catalog.add_user_model(
            NewLLMModel(
                display_name="Cloud",
                base_url="https://api.example.com/v1",
                model="gpt-4",
            )
        )
        config_repo = ConfigRepository(
            path=data_dir / "config.json", data_dir=data_dir
        )
        config_repo.save(AppConfig(llm_preset_id="cloud"))
        load = MagicMock(wraps=catalog_repo.load)
        catalog_repo.load = load

        config, entry = ConfigService(config_repo, catalog).load_active()

        assert config is not None
        assert config.llm_preset_id == "cloud"
        assert entry is not None
        assert entry.id == "cloud"
        assert load.call_count == 1

    def test_delete_config(self, config_service, mock_config_path):
        """Test deleting configuration file."""
        config = AppConfig(llm_preset_id="cloud")
        config_service.save_config(config)
        assert mock_config_path.exists()

        config_service.delete_config()
        assert not mock_config_path.exists()

    @pytest.mark.asyncio
    async def test_test_model_connection_success(
        self, config_service, mock_config_path, mock_provider_factory, monkeypatch
    ):
        """Text-only model: provider validates and returns success."""
        entry = LLMModelEntry(
            id="cloud",
            display_name="Cloud",
            provider_type="openai-compatible",
            model="gpt-4",
            base_url="http://localhost",
            api_key_required=True,
            api_key="test_key",
        )
        monkeypatch.setattr(
            config_service._catalog_service, "get_model", lambda _model_id: entry
        )
        probe = EffectiveModelConfig(
            provider_type="openai-compatible",
            base_url="http://localhost",
            model="gpt-4",
            api_key="test_key",
            timeout=60.0,
        )
        success, message = await config_service.test_model(probe)
        assert success is True
        assert message == "Connection successful"
        mock_provider_factory.from_effective.assert_called_once_with(probe)
        mock_provider_factory.from_effective.return_value.validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_model_invalid_api_key(
        self, config_service, mock_config_path, mock_provider_factory, monkeypatch
    ):
        """Test failed provider validation due to invalid API key."""
        entry = LLMModelEntry(
            id="cloud",
            display_name="Cloud",
            provider_type="openai-compatible",
            model="gpt-4",
            base_url="http://localhost",
            api_key_required=True,
            api_key="invalid_key",
        )
        monkeypatch.setattr(
            config_service._catalog_service, "get_model", lambda _model_id: entry
        )
        mock_provider_factory.from_effective.return_value.validate.side_effect = (
            ValueError("Authentication failed: Invalid API key")
        )
        probe = EffectiveModelConfig(
            provider_type="openai-compatible",
            base_url="http://localhost",
            model="gpt-4",
            api_key="invalid_key",
            timeout=60.0,
        )
        success, message = await config_service.test_model(probe)
        assert success is False
        assert message == "Authentication failed: Invalid API key"

    @pytest.mark.asyncio
    async def test_test_model_provider_construction_exception(
        self, config_service, mock_config_path, mock_provider_factory, monkeypatch
    ):
        """Test failed provider construction due to an exception."""
        entry = LLMModelEntry(
            id="cloud",
            display_name="Cloud",
            provider_type="openai-compatible",
            model="gpt-4",
            base_url="http://localhost",
            api_key_required=True,
            api_key="test_key",
        )
        monkeypatch.setattr(
            config_service._catalog_service, "get_model", lambda _model_id: entry
        )
        mock_provider_factory.from_effective.side_effect = ValueError("Test Error")
        probe = EffectiveModelConfig(
            provider_type="openai-compatible",
            base_url="http://localhost",
            model="gpt-4",
            api_key="test_key",
            timeout=60.0,
        )
        success, message = await config_service.test_model(probe)
        assert success is False
        assert message == "Test Error"

    @pytest.mark.asyncio
    async def test_create_provider_from_config_success(
        self, config_service, mock_config_path, mock_provider_factory
    ):
        """Test creating provider from saved config."""
        user_path = mock_config_path.parent / "llm_models.json"
        user_path.write_text(
            json.dumps(
                {
                    "selected": "cloud",
                    "models": {
                        "cloud": {
                            "display_name": "Cloud",
                            "provider_type": "openai-compatible",
                            "model": "gpt-4",
                            "base_url": "http://localhost",
                            "api_key_required": True,
                            "api_key": "test_key",
                        }
                    },
                }
            )
        )
        config = AppConfig(llm_preset_id="cloud")
        config_service.save_config(config)

        provider = config_service.create_provider_from_config()
        assert provider is not None
        mock_provider_factory.from_effective.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_provider_from_config_no_config(
        self, config_service, mock_config_path
    ):
        """Test creating provider when no config exists."""
        if mock_config_path.exists():
            mock_config_path.unlink()  # Ensure no config file exists
        with pytest.raises(ValueError, match="No configuration found"):
            config_service.create_provider_from_config()

    @pytest.mark.asyncio
    async def test_test_model_audio_success(
        self, config_service, mock_provider_factory
    ):
        """Audio-capable model: text + audio probes both succeed."""
        mock_provider = AsyncMock(spec=AudioCapableProvider)
        mock_provider.validate = AsyncMock(return_value=True)
        mock_provider.probe_audio_input = AsyncMock(return_value=True)
        mock_provider.close = AsyncMock()
        mock_provider_factory.from_effective.return_value = mock_provider
        probe = EffectiveModelConfig(
            provider_type="openai-compatible",
            base_url="http://localhost",
            model="gpt-4o",
            api_key="test_key",
            timeout=60.0,
            accepts_audio_input=True,
        )
        success, message = await config_service.test_model(probe)
        assert success is True
        assert message == "Audio connection successful"
        mock_provider.validate.assert_awaited_once()
        mock_provider.probe_audio_input.assert_awaited_once()
        mock_provider.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_test_model_audio_probe_rejected(
        self, config_service, mock_provider_factory
    ):
        """Audio-capable model: text passes but the audio probe is rejected."""
        mock_provider = AsyncMock(spec=AudioCapableProvider)
        mock_provider.validate = AsyncMock(return_value=True)
        mock_provider.probe_audio_input = AsyncMock(return_value=False)
        mock_provider.close = AsyncMock()
        mock_provider_factory.from_effective.return_value = mock_provider
        probe = EffectiveModelConfig(
            provider_type="openai-compatible",
            base_url="http://localhost",
            model="gpt-4o",
            api_key="test_key",
            timeout=60.0,
            accepts_audio_input=True,
        )
        success, message = await config_service.test_model(probe)
        assert success is False
        assert message == "Model does not accept audio input or rejected the audio probe."

    @pytest.mark.asyncio
    async def test_test_model_audio_skipped_when_text_fails(
        self, config_service, mock_provider_factory
    ):
        """When the text test fails, the audio probe is never run."""
        mock_provider = AsyncMock(spec=AudioCapableProvider)
        mock_provider.validate = AsyncMock(return_value=False)
        mock_provider.probe_audio_input = AsyncMock(return_value=True)
        mock_provider.close = AsyncMock()
        mock_provider_factory.from_effective.return_value = mock_provider
        probe = EffectiveModelConfig(
            provider_type="openai-compatible",
            base_url="http://localhost",
            model="gpt-4o",
            api_key="test_key",
            timeout=60.0,
            accepts_audio_input=True,
        )
        success, message = await config_service.test_model(probe)
        assert success is False
        assert message == "Invalid API key or unreachable endpoint"
        mock_provider.probe_audio_input.assert_not_called()
