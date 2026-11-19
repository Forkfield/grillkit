# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Question-voice page context builder for JSON/API responses."""

from app.platform.domain.config import AppConfig
from app.question_voice.queries.voice_status import VoiceStatus
from app.question_voice.schemas import PiperVoiceStatusRead, QuestionVoicePageContext
from app.shared.infrastructure.artifact_composition import (
    get_default_piper_voice_service,
)


class VoicePage:
    """Build Piper question-voice status context."""

    @staticmethod
    def _show_voice_banner(status: PiperVoiceStatusRead) -> bool:
        """Return whether the interview page should show a question-voice banner."""
        if status.state in ("missing", "error", "downloading"):
            return True
        return status.state == "ready" and not status.loaded_in_memory

    @staticmethod
    async def build_page_context(
        config: AppConfig | None,
    ) -> QuestionVoicePageContext:
        """Build Piper voice status keys shared by config and interview pages.

        Args:
            config: Saved provider configuration, or None when unset.

        Returns:
            Frozen page context.
        """
        voice_id, locale = VoiceStatus.resolve_tts_target(config)
        status = get_default_piper_voice_service().get_status(voice_id, locale)
        show_banner = config is not None and config.question_voice_enabled
        return QuestionVoicePageContext(
            tts_voice_status=status,
            tts_voice_banner=show_banner and VoicePage._show_voice_banner(status),
        )
