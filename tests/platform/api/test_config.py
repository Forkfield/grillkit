# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for platform config API routes (JSON)."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.llm_models import LLMModelEntry
from app.platform.domain.config import AppConfig


class TestConfigRouter:
    """Tests for config router endpoints."""

    _catalog_entry = LLMModelEntry(
        id="cloud",
        display_name="Cloud",
        provider_type="openai-compatible",
        model="gpt-4",
        base_url="https://api.openai.com",
        api_key_required=True,
        api_key="stored-secret",
    )

    def _config_body(self, **overrides):
        """Build a valid config JSON payload."""
        data = {
            "llm_preset_id": "cloud",
            "api_key": "test-key",
            "timeout": 60.0,
            "locale": "en",
        }
        data.update(overrides)
        return data

    def _catalog_stub(self):
        """Build a catalog service stub used by the parse/test handlers."""
        return SimpleNamespace(
            load_catalog=lambda: SimpleNamespace(
                models={self._catalog_entry.id: self._catalog_entry}
            ),
            get_model=lambda _model_id: self._catalog_entry,
            get_selected_model_id=lambda: "cloud",
            list_models=lambda: [self._catalog_entry],
        )

    def _patch_parse(self, success=True, message="OK"):
        """Patch the pieces of parse_and_test used by the save/test handlers."""
        catalog = self._catalog_stub()
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
        """Enter the parse_and_test patches into ``stack``."""
        for cm in self._patch_parse(success=success, message=message):
            stack.enter_context(cm)

    def _config_service_patch(self, config):
        return patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=config,
        )

    def test_config_page_get(self, client):
        """Test GET /api/config returns JSON context."""
        mock_config = AppConfig(llm_preset_id="cloud")

        with ExitStack() as stack:
            stack.enter_context(self._config_service_patch(mock_config))
            stack.enter_context(
                patch(
                    "app.platform.queries.platform_page.get_default_catalog_service",
                    return_value=self._catalog_stub(),
                )
            )
            stack.enter_context(
                patch(
                    "app.platform.queries.llm_page.get_default_catalog_service",
                    return_value=self._catalog_stub(),
                )
            )
            response = client.get("/api/config")

        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")
        data = response.json()
        assert data["llm_presets"]
        assert data["config"] is not None
        assert data["config"]["model"] == "gpt-4"

    def test_config_page_get_no_config(self, client):
        """Test GET /api/config without existing config."""
        with ExitStack() as stack:
            stack.enter_context(self._config_service_patch(None))
            response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["config"] is None
        assert data["locales"]
        assert data["speech_model_specs"]

    @pytest.mark.asyncio
    async def test_save_config_preserves_api_key_when_field_empty(self, client):
        """POST /api/config keeps the stored key when the password field is left blank."""
        existing = AppConfig(llm_preset_id="cloud")
        with ExitStack() as stack:
            stack.enter_context(self._config_service_patch(existing))
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
            response = client.post(
                "/api/config",
                json=self._config_body(api_key=""),
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        saved = mock_save.call_args[0][0]
        assert saved.llm_preset_id == "cloud"

    @pytest.mark.asyncio
    async def test_save_config_success(self, client):
        """Test POST /api/config with successful connection test."""
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
        assert body["success"] is True
        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_config_failure(self, client):
        """Test POST /api/config with failed connection test."""
        with ExitStack() as stack:
            stack.enter_context(self._config_service_patch(None))
            self._enter_parse_patches(stack, success=False, message="Connection failed")
            response = client.post("/api/config", json=self._config_body())

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert "Connection failed" in body["message"]

    @pytest.mark.asyncio
    async def test_save_config_warns_when_speech_model_fails_to_load(self, client):
        """POST /api/config returns a warning when a speech model fails to load."""
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
        assert body["success"] is True
        assert "Whisper failed to load" in body["message"]
        mock_save.assert_called_once()

    def test_delete_config(self, client):
        """Test DELETE /api/config endpoint."""
        with ExitStack() as stack:
            mock_delete = stack.enter_context(
                patch("app.platform.domain.config.ConfigService.delete_config")
            )
            response = client.delete("/api/config")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_config_success(self, client):
        """Test POST /api/config/test with successful connection."""
        with ExitStack() as stack:
            self._enter_parse_patches(
                stack, success=True, message="Connection successful"
            )
            response = client.post("/api/config/test", json=self._config_body())

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True

    @pytest.mark.asyncio
    async def test_test_config_failure(self, client):
        """Test POST /api/config/test with failed connection."""
        with ExitStack() as stack:
            self._enter_parse_patches(stack, success=False, message="Invalid API key")
            response = client.post(
                "/api/config/test",
                json=self._config_body(api_key="invalid-key"),
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert "Invalid API key" in body["message"]

    def test_add_model_to_catalog_success(self, client):
        """Test POST /api/config/llm-models adds a model and returns context."""
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
            mock_catalog.return_value.add_user_model.return_value = self._catalog_entry
            mock_catalog.return_value.list_models.return_value = [self._catalog_entry]
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
        body = response.json()
        mock_catalog.return_value.add_user_model.assert_called_once()
        assert body["selected_preset_id"] == "cloud"
        assert body["error"] is None
        assert "page" in body

    def test_add_model_to_catalog_rejects_invalid_url(self, client):
        """Test POST /api/config/llm-models fails connection probe and reports error."""
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
