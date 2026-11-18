# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Configuration page context builder."""

from app.platform.domain.config import AppConfig
from app.platform.domain.effective_config import EffectiveModelConfig
from app.platform.queries.config_read import app_config_read_from
from app.platform.queries.llm_page import list_preset_options
from app.platform.repo.config_composition import get_default_catalog_service
from app.platform.schemas import (
    ConfigPageContext,
    speech_model_specs_for_config,
)
from app.question_voice.queries.voice_status import VoiceStatus
from app.shared.infrastructure.artifact_composition import (
    get_default_whisper_model_service,
)
from app.shared.infrastructure.gateways.whisper_model import WhisperModelService
from app.shared.locales import DEFAULT_LOCALE, SUPPORTED_LOCALES
from app.shared.stt_models import DEFAULT_STT_MODEL_SIZE


async def build_page_context(
    *,
    config: AppConfig | None,
    whisper_model_service: WhisperModelService | None = None,
    voice_status_service: type[VoiceStatus] = VoiceStatus,
    error: str | None = None,
    message: str | None = None,
    mask_secret: bool = True,
    selected_llm_preset_id: str | None = None,
) -> ConfigPageContext:
    """Assemble the full config page context into a single DTO.

    Reads the Whisper (STT) and Piper (TTS) status snapshots and combines them
    with the saved provider config into one immutable ``ConfigPageContext``.

    Args:
        config: Saved provider configuration, if any.
        whisper_model_service: Whisper model service instance (injectable).
        voice_status_service: Voice status service class (injectable in tests).
        error: Optional form validation or connection error message.
        message: Optional success or informational message.
        mask_secret: Whether to mask the API key in the config dict.
        selected_llm_preset_id: Override selected preset after catalog edits.

    Returns:
        Frozen page context for the config page.
    """
    whisper = whisper_model_service or get_default_whisper_model_service()
    size = config.speech_model_size if config else DEFAULT_STT_MODEL_SIZE
    locale = config.locale if config else DEFAULT_LOCALE
    speech_model_status = whisper.get_status(size, locale)

    tts_voice_status, tts_enabled = voice_status_service.resolve_for_config(config)
    tts_show_banner = (
        tts_enabled
        and (
            tts_voice_status.state in ("missing", "error", "downloading")
            or (
                tts_voice_status.state == "ready"
                and not tts_voice_status.loaded_in_memory
            )
        )
    )

    preset_id: str | None
    if selected_llm_preset_id is not None:
        preset_id = selected_llm_preset_id
    elif config is not None and config.llm_preset_id:
        preset_id = config.llm_preset_id
    else:
        selected = get_default_catalog_service().get_selected_model()
        preset_id = selected.id if selected is not None else None

    model = None
    if config is not None and config.llm_preset_id:
        entry = get_default_catalog_service().get_model(config.llm_preset_id)
        if entry is not None:
            model = EffectiveModelConfig.from_entry(entry, timeout=config.timeout)

    return ConfigPageContext(
        config=(
            app_config_read_from(config, model, mask_secret=mask_secret)
            if config
            else None
        ),
        locales=dict(SUPPORTED_LOCALES),
        speech_model_specs=speech_model_specs_for_config(),
        speech_model_status=speech_model_status,
        speech_model_banner=speech_model_status.state == "missing",
        status=speech_model_status,
        tts_voice_status=tts_voice_status,
        tts_voice_banner=tts_show_banner,
        llm_presets=list_preset_options(),
        selected_llm_preset_id=preset_id,
        error=error,
        message=message,
    )
