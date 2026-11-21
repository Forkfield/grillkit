# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Domain-to-read-model mapping for the configuration UI.

This module is the single boundary for turning the domain (:class:`AppConfig`
plus an optional :class:`EffectiveModelConfig`) into the pydantic read model
``AppConfigRead``. It owns transport concerns only — API-key masking for
display — and must not contain business logic. Per the project's data-model
convention pydantic is the read model/outbound contract, so no intermediate DTO
layer is introduced here.
"""

from app.platform.domain.config import MASKED_API_KEY_PLACEHOLDER, AppConfig
from app.platform.domain.effective_config import EffectiveModelConfig
from app.platform.schemas import AppConfigRead


def app_config_read_from(
    config: AppConfig,
    model: EffectiveModelConfig | None,
    *,
    mask_secret: bool = False,
) -> AppConfigRead:
    """Map ``AppConfig`` plus the effective model to a read model.

    Args:
        config: Loaded or submitted application settings.
        model: Effective provider settings for the selected model, if any.
        mask_secret: Whether to mask the API key for display.

    Returns:
        Immutable read model for the configuration UI.
    """
    return AppConfigRead(
        provider_type=model.provider_type if model else "openai-compatible",
        base_url=model.base_url if model else "",
        model=model.model if model else "",
        api_key=_serialized_api_key(model.api_key if model else None, mask_secret),
        timeout=config.timeout,
        locale=config.locale,
        speech_model_size=config.speech_model_size,
        question_voice_enabled=config.question_voice_enabled,
        tts_voice_id=config.tts_voice_id,
        llm_preset_id=config.llm_preset_id,
    )


def _serialized_api_key(api_key: str | None, mask_secret: bool) -> str | None:
    """Serialize api_key for UI output."""
    if mask_secret and api_key:
        return MASKED_API_KEY_PLACEHOLDER
    return api_key
