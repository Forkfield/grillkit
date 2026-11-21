# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Whisper speech model download and on-disk installation."""

import asyncio
from collections.abc import Callable
from pathlib import Path

from huggingface_hub import snapshot_download

from app.shared.infrastructure.artifact_download import ArtifactDownloadService
from app.shared.infrastructure.artifact_status import ArtifactStatusBuilder
from app.shared.infrastructure.gateways.whisper import WhisperSttRuntime
from app.shared.infrastructure.gateways.whisper_storage import (
    is_installed,
    is_valid_model_dir,
    model_dir,
)
from app.shared.infrastructure.hf_download_progress import hf_progress_tqdm_factory
from app.shared.infrastructure.model_download import (
    cleanup_staging_dir,
    prepare_staging_dir,
    promote_staging_dir,
)
from app.shared.locales import SUPPORTED_LOCALES, normalize_locale
from app.shared.paths import WHISPER_MODELS_ROOT
from app.shared.stt_models import (
    SttModelSpec,
    normalize_stt_model_size,
    stt_model_spec_for_size,
)
from app.speech.schemas.status import WhisperModelStatusRead


class WhisperModelService(ArtifactDownloadService):
    """Download and verify offline Whisper models under ``data/whisper-models/``."""

    _DOWNLOADING_MESSAGE = "Downloading speech model…"
    _MISSING_MESSAGE = "Speech model is not installed."
    _READY_LOADING_MESSAGE = "Speech model installed on disk; loading into memory…"
    _READY_LOADED_TEMPLATE = "Speech model ready for dictation in {locale_label}."
    _READY_LOAD_FAILED_TEMPLATE = (
        "Speech model files are installed but could not be loaded: {error}"
    )

    def get_status(self, size: str, locale: str) -> WhisperModelStatusRead:
        """Build current model status for UI and API consumers.

        Args:
            size: Speech model size from provider configuration.
            locale: Interview locale for transcription language label.

        Returns:
            Status snapshot for JSON responses.
        """
        model_size = normalize_stt_model_size(size)
        code = normalize_locale(locale)
        spec = stt_model_spec_for_size(model_size)
        locale_label = SUPPORTED_LOCALES[code]

        built = ArtifactStatusBuilder.build(
            key=model_size,
            service=self,
            is_installed=lambda: is_installed(model_size),
            is_loaded=lambda: WhisperSttRuntime.is_loaded(model_size),
            load_error=WhisperSttRuntime.load_error,
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
        return WhisperModelStatusRead(
            size=model_size,
            locale=code,
            locale_label=locale_label,
            state=built.state,
            percent=built.percent,
            message=built.message,
            model_display_name=spec.display_name,
            loaded_in_memory=built.loaded_in_memory,
        )

    async def start_download(self, size: str, locale: str) -> WhisperModelStatusRead:
        """Start a background download when the model is not yet installed.

        Args:
            size: Speech model size from provider configuration.
            locale: Interview locale for status messaging.

        Returns:
            Immediate status after scheduling or skipping work.
        """
        model_size = normalize_stt_model_size(size)
        locale_code = normalize_locale(locale)
        if is_installed(model_size):
            if not WhisperSttRuntime.is_loaded(model_size):
                _ = await WhisperSttRuntime.load_size(model_size)
            return self.get_status(model_size, locale_code)

        _ = await self.schedule_download(
            model_size,
            self._run_download,
        )
        return self.get_status(model_size, locale_code)

    async def _run_download(self, size: str) -> None:
        """Execute download and installation, updating shared progress state."""
        await self._download_and_install(size)
        _ = await WhisperSttRuntime.load_size(size)

    async def _download_and_install(self, size: str) -> None:
        """Download the Hugging Face snapshot into ``data/whisper-models/<size>/``."""
        spec = stt_model_spec_for_size(size)
        target_dir = model_dir(size)
        WHISPER_MODELS_ROOT.mkdir(parents=True, exist_ok=True)
        staging_dir = prepare_staging_dir(WHISPER_MODELS_ROOT, f".staging-{size}")

        try:
            self.set_download_percent(1)
            await asyncio.to_thread(
                self._snapshot_download,
                spec,
                staging_dir,
                self.set_download_percent,
            )
            self.set_download_percent(95)
            if not is_valid_model_dir(staging_dir):
                raise ValueError(
                    f"Downloaded snapshot does not contain a valid Whisper model: "
                    f"{spec.hf_repo_id}"
                )

            promote_staging_dir(staging_dir, target_dir)
            self.set_download_percent(100)
        finally:
            cleanup_staging_dir(staging_dir)

    def _snapshot_download(
        self,
        spec: SttModelSpec,
        destination: Path,
        set_percent: Callable[[int], None],
    ) -> None:
        """Download model files from Hugging Face into ``destination``."""
        expected_bytes = spec.approx_download_mb * 1_000_000
        progress_tqdm = hf_progress_tqdm_factory(
            set_percent,
            percent_min=5,
            percent_max=90,
            expected_bytes=expected_bytes,
        )
        _ = snapshot_download(
            repo_id=spec.hf_repo_id,
            local_dir=str(destination),
            tqdm_class=progress_tqdm,
        )
