# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Speech model page context builder for JSON/API responses."""

from app.platform.domain.config import AppConfig
from app.shared.infrastructure.artifact_composition import (
    get_default_whisper_model_service,
)
from app.shared.infrastructure.gateways.whisper_model import WhisperModelService
from app.shared.locales import DEFAULT_LOCALE
from app.shared.stt_models import DEFAULT_STT_MODEL_SIZE
from app.speech.schemas.page import SttModelPageContext


class SttModelPageService:
    """Build Whisper install/load status context."""

    @staticmethod
    def build_page_context(
        config: AppConfig | None,
        whisper_model_service: WhisperModelService | None = None,
    ) -> SttModelPageContext:
        """Build speech model keys shared by config, setup, and interview pages.

        Args:
            config: Saved provider configuration, or None when unset.
            whisper_model_service: Whisper model service instance (injectable).

        Returns:
            Frozen page context.
        """
        service = whisper_model_service or get_default_whisper_model_service()
        size = config.speech_model_size if config else DEFAULT_STT_MODEL_SIZE
        locale = config.locale if config else DEFAULT_LOCALE
        status = service.get_status(size, locale)
        return SttModelPageContext(
            speech_model_status=status,
            speech_model_banner=status.state == "missing",
            status=status,
        )
