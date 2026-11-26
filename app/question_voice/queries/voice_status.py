# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Silero voice status resolution for API responses."""

from app.platform.domain.config import AppConfig
from app.question_voice.schemas import VoiceStatusRead
from app.shared.infrastructure.artifact_composition import (
    get_default_silero_voice_service,
)
from app.shared.locales import DEFAULT_LOCALE, normalize_locale
from app.shared.tts_voices import (
    default_voice_for_locale,
    normalize_tts_voice_id,
)


class VoiceStatus:
    """Resolve Silero voice status from provider configuration."""

    @staticmethod
    def resolve_tts_target(
        config: AppConfig | None,
        *,
        locale: str | None = None,
        voice_id: str | None = None,
    ) -> tuple[str, str]:
        """Resolve Silero voice id and locale from saved config or query defaults.

        Args:
            config: Saved provider configuration, if any.
            locale: Optional locale override when config is unset.
            voice_id: Optional voice id override when config is unset.

        Returns:
            Silero voice id and normalized interview locale.
        """
        if locale is not None:
            resolved_locale = normalize_locale(locale)
        elif config is not None:
            resolved_locale = config.locale
        else:
            resolved_locale = DEFAULT_LOCALE

        if voice_id is not None:
            resolved_voice = normalize_tts_voice_id(voice_id)
        elif locale is not None:
            resolved_voice = default_voice_for_locale(resolved_locale)
        elif config is not None:
            resolved_voice = config.tts_voice_id
        else:
            resolved_voice = default_voice_for_locale(resolved_locale)

        return resolved_voice, resolved_locale

    @staticmethod
    def resolve_for_config(
        config: AppConfig | None,
        *,
        locale: str | None = None,
        voice_id: str | None = None,
    ) -> tuple[VoiceStatusRead, bool]:
        """Build voice status and whether question voice is enabled.

        Args:
            config: Saved provider configuration, if any.
            locale: Optional locale override when config is unset.
            voice_id: Optional voice id override when config is unset.

        Returns:
            Voice status read model and enabled flag for API consumers.
        """
        resolved_voice, resolved_locale = VoiceStatus.resolve_tts_target(
            config,
            locale=locale,
            voice_id=voice_id,
        )
        status = get_default_silero_voice_service().get_status(
            resolved_voice, resolved_locale
        )
        enabled = config is not None and config.question_voice_enabled
        return status, enabled

    @staticmethod
    def api_payload(
        status: VoiceStatusRead,
        *,
        enabled: bool,
    ) -> dict[str, object]:
        """Serialize Silero voice status for JSON responses.

        Args:
            status: Silero voice status read model.
            enabled: Whether question voice is enabled in configuration.

        Returns:
            JSON-serializable status dictionary.
        """
        payload = status.model_dump()
        payload["enabled"] = enabled
        return payload
