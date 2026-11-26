# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Silero voice download and on-disk installation."""

import asyncio
from collections.abc import Callable
from pathlib import Path

import httpx

from app.question_voice.schemas import VoiceStatusRead
from app.shared.infrastructure.artifact_download import ArtifactDownloadService
from app.shared.infrastructure.artifact_status import ArtifactStatusBuilder
from app.shared.infrastructure.gateways.silero import SileroTtsRuntime
from app.shared.infrastructure.gateways.silero_storage import (
    is_valid_voice_dir,
    is_voice_installed,
    voice_dir,
)
from app.shared.infrastructure.model_download import (
    cleanup_staging_dir,
    prepare_staging_dir,
    promote_staging_dir,
)
from app.shared.locales import SUPPORTED_LOCALES, normalize_locale
from app.shared.paths import SILERO_VOICES_ROOT
from app.shared.tts_voices import (
    SileroVoiceSpec,
    normalize_tts_voice_id,
    voice_spec_for_id,
)

_DOWNLOAD_CONNECT_TIMEOUT_S = 30.0
_DOWNLOAD_READ_TIMEOUT_S = 120.0
_READ_CHUNK_BYTES = 1 << 20

# Percent layout matches the Whisper flow:
# 1 start, 5-90 body, 95 validate, 100 done.
_PERCENT_START = 1
_PERCENT_BODY_MIN = 5
_PERCENT_BODY_MAX = 90
_PERCENT_VALIDATE = 95
_PERCENT_DONE = 100


class SileroVoiceService(ArtifactDownloadService):
    """Download and verify offline Silero voices under ``data/silero-voices/``."""

    _DOWNLOADING_MESSAGE = "Downloading question voice…"
    _MISSING_MESSAGE = "Question voice is not installed."
    _READY_LOADING_MESSAGE = "Question voice installed on disk; loading into memory…"
    _READY_LOADED_TEMPLATE = "Question voice ready for {locale_label}."
    _READY_LOAD_FAILED_TEMPLATE = (
        "Question voice files are installed but could not be loaded: {error}"
    )

    def get_status(self, voice_id: str, locale: str) -> VoiceStatusRead:
        """Build current voice status for UI and API consumers.

        Args:
            voice_id: Silero voice id from provider configuration.
            locale: Interview locale for status messaging.

        Returns:
            Status snapshot for JSON responses.
        """
        code = normalize_tts_voice_id(voice_id)
        locale_code = normalize_locale(locale)
        spec = voice_spec_for_id(code)
        locale_label = SUPPORTED_LOCALES[locale_code]

        built = ArtifactStatusBuilder.build(
            key=code,
            service=self,
            is_installed=lambda: is_voice_installed(code),
            is_loaded=lambda: SileroTtsRuntime.is_loaded(code),
            load_error=SileroTtsRuntime.load_error,
            downloading_message=self._DOWNLOADING_MESSAGE,
            missing_message=self._MISSING_MESSAGE,
            ready_loaded_message=self._READY_LOADED_TEMPLATE.format(
                locale_label=locale_label
            ),
            ready_loading_message=self._READY_LOADING_MESSAGE,
            ready_load_failed_message=lambda err: (
                self._READY_LOAD_FAILED_TEMPLATE.format(error=err)
            ),
        )
        return VoiceStatusRead(
            voice_id=code,
            locale=locale_code,
            locale_label=locale_label,
            state=built.state,
            percent=built.percent,
            message=built.message,
            voice_display_name=spec.display_name,
            loaded_in_memory=built.loaded_in_memory,
        )

    async def start_download(self, voice_id: str, locale: str) -> VoiceStatusRead:
        """Start a background download when the voice is not yet installed.

        Args:
            voice_id: Silero voice id from provider configuration.
            locale: Interview locale for status messaging.

        Returns:
            Immediate status after scheduling or skipping work.
        """
        code = normalize_tts_voice_id(voice_id)
        locale_code = normalize_locale(locale)
        if is_voice_installed(code):
            if not SileroTtsRuntime.is_loaded(code):
                _ = await SileroTtsRuntime.load_voice(code)
            return self.get_status(code, locale_code)

        _ = await self.schedule_download(
            code,
            self._run_download,
        )
        return self.get_status(code, locale_code)

    async def _run_download(self, voice_id: str) -> None:
        """Execute download and installation, updating shared progress state."""
        await self._download_and_install(voice_id)
        _ = await SileroTtsRuntime.load_voice(voice_id)

    async def _download_and_install(self, voice_id: str) -> None:
        """Download the Silero package into ``data/silero-voices/<voice_id>/``."""
        voice_spec_for_id(voice_id)
        target_dir = voice_dir(voice_id)
        SILERO_VOICES_ROOT.mkdir(parents=True, exist_ok=True)
        staging_dir = prepare_staging_dir(SILERO_VOICES_ROOT, f".staging-{voice_id}")

        try:
            self.set_download_percent(_PERCENT_START)
            await asyncio.to_thread(
                self._download_model_package,
                voice_spec_for_id(voice_id),
                staging_dir,
                self.set_download_percent,
            )
            self.set_download_percent(_PERCENT_VALIDATE)
            if not is_valid_voice_dir(staging_dir, voice_id):
                raise ValueError(
                    f"Downloaded files do not contain a valid Silero voice: {voice_id}"
                )

            promote_staging_dir(staging_dir, target_dir)
            self.set_download_percent(_PERCENT_DONE)
        finally:
            cleanup_staging_dir(staging_dir)

    def _download_model_package(
        self,
        spec: SileroVoiceSpec,
        destination_dir: Path,
        set_percent: Callable[[int], None],
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Stream the ``.pt`` package from ``models.silero.ai`` into staging.

        Args:
            spec: Silero voice spec with the package URL.
            destination_dir: Staging directory for the download.
            set_percent: Callback receiving 5-90 as bytes arrive.
            transport: Optional httpx transport override (used by tests).
        """
        destination = destination_dir / f"{spec.model_id}.pt"
        expected_bytes = max(1, spec.approx_download_mb * 1_000_000)
        timeout = httpx.Timeout(
            _DOWNLOAD_CONNECT_TIMEOUT_S, read=_DOWNLOAD_READ_TIMEOUT_S
        )
        with (
            httpx.Client(
                timeout=timeout, follow_redirects=True, transport=transport
            ) as client,
            client.stream("GET", spec.package_url) as response,
        ):
            response.raise_for_status()
            content_length = response.headers.get("Content-Length")
            if content_length is not None and content_length.isdigit():
                expected_bytes = max(1, int(content_length))
            span = _PERCENT_BODY_MAX - _PERCENT_BODY_MIN
            downloaded = 0
            with destination.open("wb") as package_file:
                for chunk in response.iter_bytes(_READ_CHUNK_BYTES):
                    package_file.write(chunk)
                    downloaded += len(chunk)
                    ratio = min(1.0, downloaded / expected_bytes)
                    set_percent(_PERCENT_BODY_MIN + int(span * ratio))
