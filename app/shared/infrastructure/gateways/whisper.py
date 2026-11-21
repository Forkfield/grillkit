# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""In-process speech transcriber loading and hot-reload."""

import gc
import logging
import os

from faster_whisper import WhisperModel

from app.ai.stt import Stt
from app.ai.whisper_stt import WhisperStt
from app.shared.infrastructure.gateways.whisper_storage import is_installed, model_dir
from app.shared.infrastructure.in_process_runtime import InProcessArtifactRuntime
from app.shared.stt_models import normalize_stt_model_size

logger = logging.getLogger(__name__)

WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")


class WhisperSttGateway(InProcessArtifactRuntime):
    """Hold a loaded :class:`Stt` in this process.

    Satisfies the :class:`SttModelLoader` protocol, so it can be injected into the
    :class:`SpeechRuntimeCoordinator` as the STT backend.
    """

    def _normalize_key(self, key: str) -> str:
        """Normalize a stt model size identifier."""
        return normalize_stt_model_size(key)

    def _is_installed(self, key: str) -> bool:
        """Return whether a valid Whisper model is on disk for ``key``."""
        return is_installed(key)

    def _load_sync(self, key: str) -> Stt:
        """Load ``WhisperModel`` and wrap it in a transcriber (blocking)."""
        path = model_dir(key)
        model = WhisperModel(
            str(path),
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
        return WhisperStt(model)

    def is_installed(self, size: str) -> bool:
        """Return whether a valid Whisper model is on disk for ``size``."""
        return self._is_installed(size)

    def is_loaded(self, size: str) -> bool:
        """Return whether the model for ``size`` is loaded in memory."""
        return self._has_loaded_key(size)

    def get(self) -> Stt | None:
        """Return the currently loaded transcriber, if any."""
        return self._artifact

    async def load_size(self, size: str) -> bool:
        """Load or reload the Whisper model for ``size`` from disk.

        Args:
            size: Speech model size identifier.

        Returns:
            True if a transcriber is loaded for the size after this call.
        """
        loaded = await self._load(size)
        if loaded:
            logger.info(
                "Loaded Whisper model %s from %s",
                self._normalize_key(size),
                model_dir(self._normalize_key(size)),
            )
        return loaded

    def on_loaded(self, key: str, artifact: Stt) -> None:
        """Log a successful load."""
        del artifact
        logger.debug("Whisper model %s loaded into memory", key)

    def on_unloaded(self) -> None:
        """Log when the transcriber is dropped."""
        logger.debug("Whisper model unloaded from memory")
        _ = gc.collect()


# Single in-process runtime instance shared by the coordinator and status services.
WhisperSttRuntime = WhisperSttGateway()
