# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for first-time configuration flow (S1 scenarios)."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.ai.llm_models import LLMModelEntry
from app.platform.domain.config import AppConfig


class TestFirstTimeConfigFlow:
    """S1: First-time Configuration Flow."""

    def _catalog_entry(self):
        return LLMModelEntry(
            id="cloud",
            display_name="Cloud",
            provider_type="openai-compatible",
            model="gpt-4",
            base_url="https://api.openai.com",
            api_key_required=True,
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

    def _patch_parse(self, success=True, message="OK"):
        catalog = SimpleNamespace(
            load_catalog=lambda: SimpleNamespace(
                models={"cloud": self._catalog_entry()}
            ),
            get_model=lambda _model_id: self._catalog_entry(),
            get_selected_model_id=lambda: "cloud",
            list_models=lambda: [self._catalog_entry()],
        )
        return [
            patch(
                "app.platform.use_cases.save_config.normalize_model_id",
                return_value="cloud",
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
                return_value=(success, message),
            ),
        ]

    def _enter_parse_patches(self, stack: ExitStack, success=True, message="OK"):
        for cm in self._patch_parse(success=success, message=message):
            stack.enter_context(cm)

    def _config_service_patch(self, config):
        return patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=config,
        )

    def test_dashboard_renders_without_config(self, client):
        """S1.1: GET /api/dashboard returns JSON even without provider config."""
        with ExitStack() as stack:
            stack.enter_context(self._config_service_patch(None))
            stack.enter_context(
                patch(
                    "app.interview.queries.dashboard.InterviewDashboard.list_rows",
                    return_value=[],
                )
            )
            response = client.get("/api/dashboard")
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")

    def test_setup_unconfigured(self, client):
        """S1.2: GET /api/setup signals no provider config."""
        with ExitStack() as stack:
            stack.enter_context(self._config_service_patch(None))
            response = client.get("/api/setup")
        assert response.status_code == 200
        assert response.json() == {"configured": False}

    def test_config_get_returns_json_without_config(self, client):
        """S1.3: GET /api/config returns JSON context even with empty config."""
        with ExitStack() as stack:
            stack.enter_context(self._config_service_patch(None))
            response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert data["config"] is None
        assert data["llm_presets"] is not None

    def test_config_save_fails_with_unreachable_ollama(self, client):
        """S1.4: Save with unreachable Ollama shows connection error."""
        with ExitStack() as stack:
            stack.enter_context(self._config_service_patch(None))
            self._enter_parse_patches(
                stack, success=False, message="Connection refused"
            )
            response = client.post(
                "/api/config",
                json=self._config_body(llm_preset_id="local"),
            )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert "Connection refused" in body["message"]

    def test_config_test_connection_success(self, client):
        """S1.5: POST /api/config/test returns success with valid provider."""
        with ExitStack() as stack:
            self._enter_parse_patches(
                stack, success=True, message="Connection successful"
            )
            response = client.post(
                "/api/config/test",
                json=self._config_body(),
            )
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_config_test_connection_failure(self, client):
        """S1.5: POST /api/config/test returns error with invalid provider."""
        with ExitStack() as stack:
            self._enter_parse_patches(stack, success=False, message="Invalid API key")
            response = client.post(
                "/api/config/test",
                json=self._config_body(api_key="bad-key"),
            )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert "Invalid API key" in body["message"]

    def test_add_model_to_catalog_success(self, client):
        """S1.6: Add a new model to catalog via POST /api/config/llm-models."""
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
            mock_catalog.return_value.add_user_model.return_value = (
                self._catalog_entry()
            )
            mock_catalog.return_value.list_models.return_value = [self._catalog_entry()]
            response = client.post(
                "/api/config/llm-models",
                json={
                    "display_name": "GPT-4 Test",
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4",
                    "api_key": "test-key",
                    "api_key_required": True,
                },
            )
        assert response.status_code == 200
        mock_catalog.return_value.add_user_model.assert_called_once()
        assert response.json()["selected_preset_id"] == "cloud"

    def test_add_model_to_catalog_rejects_invalid_url(self, client):
        """S1.6: Adding model with invalid URL fails validation."""
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
                },
            )
        assert response.status_code == 200
        assert response.json()["error"] is not None

    def test_config_save_success(self, client):
        """S1.7: Save valid config and verify success response."""
        with ExitStack() as stack:
            stack.enter_context(self._config_service_patch(None))
            self._enter_parse_patches(stack)
            mock_save = stack.enter_context(
                patch("app.platform.domain.config.ConfigService.save_config")
            )
            stack.enter_context(
                patch(
                    "app.platform.domain.speech_runtime.SpeechRuntimeCoordinator.reload_after_config_save",
                    new=AsyncMock(return_value=[]),
                )
            )
            response = client.post("/api/config", json=self._config_body())
        assert response.status_code == 200
        body = response.json()
        mock_save.assert_called_once()
        assert body["success"] is True

    def test_config_save_warns_when_speech_model_fails_to_load(self, client):
        """S1.7b: Config saved but warning shown when a speech model fails to load."""
        with ExitStack() as stack:
            stack.enter_context(self._config_service_patch(None))
            self._enter_parse_patches(stack)
            mock_save = stack.enter_context(
                patch("app.platform.domain.config.ConfigService.save_config")
            )
            stack.enter_context(
                patch(
                    "app.platform.domain.speech_runtime.SpeechRuntimeCoordinator.reload_after_config_save",
                    new=AsyncMock(return_value=["Whisper failed to load"]),
                )
            )
            response = client.post("/api/config", json=self._config_body())
        assert response.status_code == 200
        body = response.json()
        mock_save.assert_called_once()
        assert "Whisper failed to load" in body["message"]

    def test_after_save_setup_no_longer_redirects(self, client):
        """S1.8: After config saved, GET /api/setup returns the setup page."""
        mock_config = AppConfig(
            locale="en",
        )
        with ExitStack() as stack:
            stack.enter_context(self._config_service_patch(mock_config))
            stack.enter_context(
                patch("app.interview.api.setup.list_tracks", return_value=["python"])
            )
            stack.enter_context(
                patch("app.interview.api.setup.list_levels", return_value=["junior"])
            )
            stack.enter_context(
                patch(
                    "app.interview.api.setup.list_categories", return_value=["basics"]
                )
            )
            response = client.get("/api/setup")
        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is True
        assert "track_sections" in body

    def test_delete_config_then_setup_unconfigured(self, client):
        """S1.9: After DELETE /api/config, GET /api/setup reports unconfigured."""
        with ExitStack() as stack:
            mock_delete = stack.enter_context(
                patch("app.platform.domain.config.ConfigService.delete_config")
            )
            response = client.delete("/api/config")
        assert response.status_code == 200
        mock_delete.assert_called_once()

        # After deletion, setup should report unconfigured
        with ExitStack() as stack:
            stack.enter_context(self._config_service_patch(None))
            response = client.get("/api/setup")
        assert response.status_code == 200
        assert response.json() == {"configured": False}
