# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for question-voice HTTP routes (TTS status and download)."""

from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest

from app.platform.domain.config import AppConfig
from app.question_voice.schemas import VoiceStatusRead


@pytest.fixture
def voice_config(minimal_app_config):
    """Provider config with question voice enabled."""
    return replace(
        minimal_app_config,
        locale="en",
        question_voice_enabled=True,
    )


class TestTtsStatusRoute:
    """Tests for GET /speech/tts/status."""

    def test_status_returns_json_when_voice_disabled(self, client):
        """Status reports unavailable when voice is off."""
        config = AppConfig(
            question_voice_enabled=False,
        )
        missing = VoiceStatusRead(
            voice_id="en-en_0",
            locale="en",
            locale_label="English",
            state="missing",
            percent=0,
            message="Question voice is not installed.",
            voice_display_name="en_0 (US English)",
        )
        with (
            patch(
                "app.platform.domain.config.ConfigService.get_config",
                return_value=config,
            ),
            patch(
                "app.shared.infrastructure.gateways.silero_voice.SileroVoiceService.get_status",
                return_value=missing,
            ),
        ):
            response = client.get(
                "/speech/tts/status",
                headers={"Accept": "application/json"},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "missing"
        assert payload["enabled"] is False

    def test_status_returns_json_when_voice_ready(self, client, voice_config):
        """Status reports ready when the Silero voice is installed."""
        ready = VoiceStatusRead(
            voice_id="en-en_0",
            locale="en",
            locale_label="English",
            state="ready",
            percent=100,
            message="Question voice ready for English.",
            voice_display_name="en_0 (US English)",
            loaded_in_memory=True,
        )
        with (
            patch(
                "app.platform.domain.config.ConfigService.get_config",
                return_value=voice_config,
            ),
            patch(
                "app.shared.infrastructure.gateways.silero_voice.SileroVoiceService.get_status",
                return_value=ready,
            ),
        ):
            response = client.get(
                "/speech/tts/status",
                headers={"Accept": "application/json"},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "ready"
        assert payload["enabled"] is True
        assert payload["loaded_in_memory"] is True

    def test_status_returns_json(self, client, voice_config):
        """Status route always returns a JSON payload."""
        ready = VoiceStatusRead(
            voice_id="en-en_0",
            locale="en",
            locale_label="English",
            state="ready",
            percent=100,
            message="Question voice ready for English.",
            voice_display_name="en_0 (US English)",
        )
        with (
            patch(
                "app.platform.domain.config.ConfigService.get_config",
                return_value=voice_config,
            ),
            patch(
                "app.shared.infrastructure.gateways.silero_voice.SileroVoiceService.get_status",
                return_value=ready,
            ),
        ):
            response = client.get("/speech/tts/status")
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        payload = response.json()
        assert payload["state"] == "ready"
        assert payload["enabled"] is True

    def test_status_locale_query_overrides_saved_config(self, client, voice_config):
        """Status endpoint honors locale query param over saved config."""
        missing = VoiceStatusRead(
            voice_id="ru-aidar",
            locale="ru",
            locale_label="Russian",
            state="missing",
            percent=0,
            message="Question voice is not installed.",
            voice_display_name="Aidar (Russian)",
        )
        with (
            patch(
                "app.platform.domain.config.ConfigService.get_config",
                return_value=voice_config,
            ),
            patch(
                "app.shared.infrastructure.gateways.silero_voice.SileroVoiceService.get_status",
                return_value=missing,
            ) as get_status,
        ):
            response = client.get(
                "/speech/tts/status?locale=ru",
                headers={"Accept": "application/json"},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["voice_id"] == "ru-aidar"
        assert payload["locale"] == "ru"
        get_status.assert_called_once_with("ru-aidar", "ru")

    def test_status_voice_id_query_overrides_defaults(self, client, voice_config):
        """Status endpoint honors voice_id query param."""
        missing = VoiceStatusRead(
            voice_id="fr-fr_0",
            locale="fr",
            locale_label="French",
            state="missing",
            percent=0,
            message="Question voice is not installed.",
            voice_display_name="fr_0 (French)",
        )
        with (
            patch(
                "app.platform.domain.config.ConfigService.get_config",
                return_value=voice_config,
            ),
            patch(
                "app.shared.infrastructure.gateways.silero_voice.SileroVoiceService.get_status",
                return_value=missing,
            ) as get_status,
        ):
            response = client.get(
                "/speech/tts/status?locale=fr&voice_id=fr-fr_0",
                headers={"Accept": "application/json"},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["voice_id"] == "fr-fr_0"
        get_status.assert_called_once_with("fr-fr_0", "fr")


class TestTtsVoiceDownloadRoute:
    """Tests for POST /speech/tts/voice/download."""

    def test_voice_download_without_config_uses_defaults(self, client):
        """Download schedules work before provider config is saved."""
        downloading = VoiceStatusRead(
            voice_id="en-en_0",
            locale="en",
            locale_label="English",
            state="downloading",
            percent=5,
            message="Downloading question voice…",
            voice_display_name="en_0 (US English)",
        )
        with (
            patch(
                "app.platform.domain.config.ConfigService.get_config",
                return_value=None,
            ),
            patch(
                "app.shared.infrastructure.gateways.silero_voice.SileroVoiceService.start_download",
                new_callable=AsyncMock,
                return_value=downloading,
            ) as start_download,
        ):
            response = client.post(
                "/speech/tts/voice/download",
                headers={"Accept": "application/json"},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "downloading"
        assert payload["enabled"] is False
        start_download.assert_called_once_with("en-en_0", "en")

    def test_voice_download_schedules_work(self, client, voice_config):
        """Download returns status after scheduling Silero voice install."""
        downloading = VoiceStatusRead(
            voice_id="en-en_0",
            locale="en",
            locale_label="English",
            state="downloading",
            percent=5,
            message="Downloading question voice…",
            voice_display_name="en_0 (US English)",
        )
        with (
            patch(
                "app.platform.domain.config.ConfigService.get_config",
                return_value=voice_config,
            ),
            patch(
                "app.shared.infrastructure.gateways.silero_voice.SileroVoiceService.start_download",
                new_callable=AsyncMock,
                return_value=downloading,
            ) as start_download,
        ):
            response = client.post(
                "/speech/tts/voice/download",
                headers={"Accept": "application/json"},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "downloading"
        assert payload["enabled"] is True
        start_download.assert_called_once_with("en-en_0", "en")

    def test_voice_download_with_locale_override(self, client, voice_config):
        """Download endpoint honors locale and voice_id query params."""
        downloading = VoiceStatusRead(
            voice_id="ru-aidar",
            locale="ru",
            locale_label="Russian",
            state="downloading",
            percent=5,
            message="Downloading question voice…",
            voice_display_name="Aidar (Russian)",
        )
        with (
            patch(
                "app.platform.domain.config.ConfigService.get_config",
                return_value=voice_config,
            ),
            patch(
                "app.shared.infrastructure.gateways.silero_voice.SileroVoiceService.start_download",
                new_callable=AsyncMock,
                return_value=downloading,
            ) as start_download,
        ):
            response = client.post(
                "/speech/tts/voice/download?locale=ru&voice_id=ru-aidar",
                headers={"Accept": "application/json"},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["voice_id"] == "ru-aidar"
        start_download.assert_called_once_with("ru-aidar", "ru")

    def test_voice_download_returns_json(self, client, voice_config):
        """Download route returns a JSON payload."""
        downloading = VoiceStatusRead(
            voice_id="en-en_0",
            locale="en",
            locale_label="English",
            state="downloading",
            percent=5,
            message="Downloading question voice…",
            voice_display_name="en_0 (US English)",
        )
        with (
            patch(
                "app.platform.domain.config.ConfigService.get_config",
                return_value=voice_config,
            ),
            patch(
                "app.shared.infrastructure.gateways.silero_voice.SileroVoiceService.start_download",
                new_callable=AsyncMock,
                return_value=downloading,
            ),
        ):
            response = client.post("/speech/tts/voice/download")
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        payload = response.json()
        assert payload["state"] == "downloading"
