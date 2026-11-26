# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for Silero voice download and status."""

from pathlib import Path

import httpx
import pytest

from app.shared.infrastructure.gateways import silero_storage, silero_voice
from app.shared.infrastructure.gateways.silero_voice import SileroVoiceService
from app.shared.tts_voices import voice_spec_for_id


def _mock_transport(payload: bytes) -> httpx.MockTransport:
    """Build a transport serving ``payload`` for any request."""

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            content=payload,
            headers={"Content-Length": str(len(payload))},
        )

    return httpx.MockTransport(handler)


def _error_transport(status_code: int) -> httpx.MockTransport:
    """Build a transport failing every request with ``status_code``."""

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(status_code)

    return httpx.MockTransport(handler)


class TestDownloadModelPackage:
    """Tests for the low-level package stream."""

    def test_streams_package_into_destination(self, tmp_path):
        """Bytes land in the staging file with monotonic progress."""
        service = SileroVoiceService()
        percents: list[int] = []
        spec = voice_spec_for_id("ru-aidar")
        payload = b"package-bytes" * 100
        service._download_model_package(
            spec,
            tmp_path,
            percents.append,
            transport=_mock_transport(payload),
        )
        package = tmp_path / "v5_5_ru.pt"
        assert package.read_bytes() == payload
        assert percents == sorted(percents)
        assert percents[-1] == 90

    def test_http_error_raises(self, tmp_path):
        """Non-2xx responses raise an HTTP status error."""
        service = SileroVoiceService()
        spec = voice_spec_for_id("ru-aidar")
        with pytest.raises(httpx.HTTPStatusError):
            service._download_model_package(
                spec,
                tmp_path,
                lambda percent: None,
                transport=_error_transport(404),
            )
        assert not (tmp_path / "v5_5_ru.pt").exists()


class TestDownloadAndInstall:
    """Tests for the staged install flow."""

    @staticmethod
    def _write_stub_package(*args: object, **kwargs: object) -> None:
        """Write the expected model file into the staging directory."""
        spec = args[0]
        destination = Path(str(args[1]))
        (destination / f"{spec.model_id}.pt").write_bytes(b"package-bytes")

    async def test_promotes_staging_into_target_dir(self, tmp_path, monkeypatch):
        """A finished download is promoted into the voice directory."""
        monkeypatch.setattr(silero_voice, "SILERO_VOICES_ROOT", tmp_path)
        monkeypatch.setattr(silero_storage, "SILERO_VOICES_ROOT", tmp_path)
        service = SileroVoiceService()
        monkeypatch.setattr(
            service,
            "_download_model_package",
            self._write_stub_package,
        )
        await service._download_and_install("ru-aidar")
        assert (tmp_path / "ru-aidar" / "v5_5_ru.pt").read_bytes() == b"package-bytes"
        assert not (tmp_path / ".staging-ru-aidar").exists()
        assert service.download_percent() == 100


class TestGetStatus:
    """Tests for status resolution."""

    def test_reports_missing_when_not_installed(self, monkeypatch):
        """Voice without on-disk files reports the missing state."""
        monkeypatch.setattr(silero_voice, "is_voice_installed", lambda voice_id: False)
        service = SileroVoiceService()
        status = service.get_status("ru-aidar", "ru")
        assert status.state == "missing"
        assert status.voice_id == "ru-aidar"
        assert status.voice_display_name == "Aidar (Russian)"

    def test_accepts_legacy_piper_id(self, monkeypatch):
        """Legacy Piper ids resolve to their Silero replacement."""
        monkeypatch.setattr(silero_voice, "is_voice_installed", lambda voice_id: False)
        service = SileroVoiceService()
        status = service.get_status("ru_RU-dmitri-medium", "ru")
        assert status.voice_id == "ru-aidar"
        assert status.state == "missing"
