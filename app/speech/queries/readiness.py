# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Speech runtime readiness checks for cross-feature orchestration."""

from app.shared.infrastructure.gateways.whisper_storage import is_installed
from app.shared.stt_models import normalize_stt_model_size


class SttModelReadiness:
    """Check whether configured Whisper artifacts are available on disk."""

    @staticmethod
    def is_model_installed(speech_model_size: str) -> bool:
        """Return whether the configured Whisper model is installed locally.

        Args:
            speech_model_size: Whisper size slug from application settings.

        Returns:
            True when model files exist under ``data/whisper-models/``.
        """
        size = normalize_stt_model_size(speech_model_size)
        return is_installed(size)
