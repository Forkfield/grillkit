# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Config edge cases: locale change, delete config preserves sessions, invalid URL."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.ai.llm_models import LLMModelEntry
from app.platform.domain.config import AppConfig


class TestConfigEdgeCases:
    """Tests for configuration edge cases."""

    def _catalog_entry(self):
        return LLMModelEntry(
            id="cloud",
            display_name="Cloud",
            provider_type="openai-compatible",
            model="gpt-4",
            base_url="https://api.openai.com",
            api_key="stored-secret",
        )

    def _config_body(self, **overrides):
        data = {
            "llm_preset_id": "cloud",
            "api_key": "test-key",
            "timeout": 60.0,
            "locale": "en",
        }
        data.update(overrides)
        return data

    def _config_service_patch(self, config):
        return patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=config,
        )

    def _enter_parse_patches(self, stack, entry, preset_id="cloud", success=True):
        catalog = SimpleNamespace(
            load_catalog=lambda: SimpleNamespace(models={preset_id: entry}),
            get_model=lambda _model_id: entry,
            get_selected_model_id=lambda: preset_id,
            list_models=lambda: [entry],
        )
        for cm in [
            patch(
                "app.platform.use_cases.save_config.normalize_model_id",
                return_value=preset_id,
            ),
            patch(
                "app.platform.repo.config_composition.get_default_catalog_service",
                return_value=catalog,
            ),
            patch(
                "app.platform.queries.llm_page.get_default_catalog_service",
                return_value=catalog,
            ),
            patch(
                "app.platform.domain.config.ConfigService.test_model",
                return_value=(success, "OK"),
            ),
        ]:
            stack.enter_context(cm)

    def _enter_save_helpers(self, stack):
        mock_save = stack.enter_context(
            patch("app.platform.domain.config.ConfigService.save_config")
        )
        stack.enter_context(
            patch(
                "app.platform.domain.speech_runtime.SpeechRuntimeCoordinator.reload_after_config_save",
                new=AsyncMock(return_value=[]),
            )
        )
        return mock_save

    def test_locale_change_saved(self, client, isolated_db):
        """Locale change written to config and used in new sessions."""
        with ExitStack() as stack:
            self._enter_parse_patches(stack, self._catalog_entry())
            mock_save = self._enter_save_helpers(stack)
            response = client.post(
                "/api/config",
                json=self._config_body(locale="ru"),
            )
        assert response.status_code == 200
        saved = mock_save.call_args[0][0]
        assert saved.locale == "ru"

    def test_config_delete_keeps_sessions(self, client, isolated_db):
        """Deleting config does not affect existing interviews."""
        from app.shared.infrastructure.models import Interview
        from tests.helpers.interview_seed import persist_interview_with_answers
        from tests.helpers.selection import minimal_selection_spec

        interview_id = persist_interview_with_answers(
            Interview(
                id="cfg-delete-1",
                locale="en",
                selection_spec=minimal_selection_spec(),
                status="active",
            ),
            [],
            question_count=5,
        )

        with ExitStack() as stack:
            mock_delete = stack.enter_context(
                patch("app.platform.domain.config.ConfigService.delete_config")
            )
            client.delete("/api/config")
            mock_delete.assert_called_once()

        # Existing session still reachable
        from app.interview.repositories.uow import InterviewUnitOfWork

        with InterviewUnitOfWork() as uow:
            interview = uow.interviews.get_aggregate(interview_id)
            assert interview is not None
            assert interview.status == "active"

    def test_add_model_rejects_invalid_url(self, client, isolated_db):
        """Adding model with unreachable URL fails validation."""
        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "app.platform.domain.config.ConfigService.test_model",
                    return_value=(False, "Connection refused"),
                )
            )
            stack.enter_context(self._config_service_patch(None))
            response = client.post(
                "/api/config/llm-models",
                json={
                    "display_name": "Broken",
                    "base_url": "http://invalid-url-test",
                    "model": "none",
                    "api_key": "",
                    "api_key_required": False,
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["error"] is not None

    def test_add_model_with_accepts_audio_input_flag(self, client, isolated_db):
        """S12.2: Adding model with accepts_audio_input=true stores the flag."""
        added_entry = LLMModelEntry(
            id="audio-model-id",
            display_name="Audio Model",
            provider_type="openai-compatible",
            model="gpt-4o-audio",
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            accepts_audio_input=True,
        )
        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "app.platform.domain.config.ConfigService.test_model",
                    return_value=(True, "OK"),
                )
            )
            stack.enter_context(self._config_service_patch(None))
            mock_catalog = stack.enter_context(
                patch(
                    "app.platform.repo.config_composition.get_default_catalog_service"
                )
            )
            mock_catalog.return_value.add_user_model.return_value = added_entry
            mock_catalog.return_value.list_models.return_value = [added_entry]
            response = client.post(
                "/api/config/llm-models",
                json={
                    "display_name": "Audio Model",
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4o-audio",
                    "api_key": "test-key",
                    "api_key_required": True,
                    "accepts_audio_input": True,
                },
            )
        assert response.status_code == 200
        mock_catalog.return_value.add_user_model.assert_called_once()
        payload = mock_catalog.return_value.add_user_model.call_args[0][0]
        assert payload.accepts_audio_input is True

    def test_config_save_without_api_key_when_not_required(self, client, isolated_db):
        """S12.5: Saving config with an empty API key works without a key."""
        ollama_entry = LLMModelEntry(
            id="local",
            display_name="Ollama Local",
            provider_type="openai-compatible",
            model="llama3",
            base_url="http://localhost:11434/v1",
            api_key=None,
        )
        with ExitStack() as stack:
            stack.enter_context(self._config_service_patch(None))
            self._enter_parse_patches(stack, ollama_entry, preset_id="local")
            mock_save = self._enter_save_helpers(stack)
            response = client.post(
                "/api/config",
                json=self._config_body(
                    llm_preset_id="local",
                    api_key="",
                ),
            )
        assert response.status_code == 200
        saved = mock_save.call_args[0][0]
        assert saved.llm_preset_id == "local"

    def test_speech_model_size_change_stored(self, client, isolated_db):
        """S12.4: Changing speech_model_size is persisted in config."""
        existing = AppConfig(
            llm_preset_id="cloud",
            speech_model_size="small",
        )
        with ExitStack() as stack:
            stack.enter_context(self._config_service_patch(existing))
            self._enter_parse_patches(stack, self._catalog_entry())
            mock_save = self._enter_save_helpers(stack)
            response = client.post(
                "/api/config",
                json=self._config_body(
                    api_key="",
                    speech_model_size="medium",
                    question_voice_enabled=False,
                ),
            )
        assert response.status_code == 200
        saved = mock_save.call_args[0][0]
        assert saved.speech_model_size == "medium"
