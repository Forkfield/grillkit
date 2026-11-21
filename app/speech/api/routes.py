# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Speech model download and status endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.platform.api.deps import ConfigServiceDep
from app.platform.domain.config import AppConfig
from app.shared.locales import DEFAULT_LOCALE, normalize_locale
from app.shared.stt_models import (
    DEFAULT_STT_MODEL_SIZE,
    STT_MODEL_BY_SIZE,
    normalize_stt_model_size,
)
from app.speech.api.deps import WhisperModelServiceDep
from app.speech.schemas.options import SttModelOptionRead

router = APIRouter(prefix="/speech", tags=["speech"])


def _resolve_speech_model_target(
    config: AppConfig | None,
    *,
    size: str | None,
    locale: str | None,
) -> tuple[str, str]:
    """Resolve Whisper size and locale from saved config or query defaults.

    Args:
        config: Saved provider configuration, if any.
        size: Optional size override when config is unset.
        locale: Optional locale override when config is unset.

    Returns:
        Normalized speech model size and locale codes.
    """
    if size is not None:
        resolved_size = normalize_stt_model_size(size)
    elif config is not None:
        resolved_size = normalize_stt_model_size(config.speech_model_size)
    else:
        resolved_size = DEFAULT_STT_MODEL_SIZE

    if locale is not None:
        resolved_locale = normalize_locale(locale)
    elif config is not None:
        resolved_locale = config.locale
    else:
        resolved_locale = DEFAULT_LOCALE

    return resolved_size, resolved_locale


@router.get("/model/status")
async def speech_model_status(
    config_service: ConfigServiceDep,
    whisper_model_service: WhisperModelServiceDep,
    size: Annotated[str | None, Query()] = None,
    locale: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    """Return installation status for the configured Whisper model size.

    Args:
        config_service: Provider configuration service.
        whisper_model_service: Whisper model download service.
        size: Whisper size when provider config is not saved yet.
        locale: Interview locale when provider config is not saved yet.

    Returns:
        JSON status payload.
    """
    config = config_service.get_config()
    speech_model_size, speech_locale = _resolve_speech_model_target(
        config,
        size=size,
        locale=locale,
    )
    status = whisper_model_service.get_status(speech_model_size, speech_locale)
    return JSONResponse(status.model_dump())


@router.post("/model/download")
async def speech_model_download(
    config_service: ConfigServiceDep,
    whisper_model_service: WhisperModelServiceDep,
    size: Annotated[str | None, Query()] = None,
    locale: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    """Start downloading the Whisper model for the configured size.

    Args:
        config_service: Provider configuration service.
        whisper_model_service: Whisper model download service.
        size: Whisper size when provider config is not saved yet.
        locale: Interview locale when provider config is not saved yet.

    Returns:
        JSON status payload after scheduling work.
    """
    config = config_service.get_config()
    speech_model_size, speech_locale = _resolve_speech_model_target(
        config,
        size=size,
        locale=locale,
    )
    status = await whisper_model_service.start_download(
        speech_model_size,
        speech_locale,
    )
    return JSONResponse(status.model_dump())


@router.get("/model/options")
async def speech_model_options() -> JSONResponse:
    """Return speech model size metadata for UI trade-off hints.

    Returns:
        JSON list of size options with download and performance hints.
    """
    options = [
        SttModelOptionRead(
            size=spec.size,
            display_name=spec.display_name,
            approx_download_mb=spec.approx_download_mb,
            ram_hint=spec.ram_hint,
            speed_hint=spec.speed_hint,
            quality_hint=spec.quality_hint,
        ).model_dump()
        for spec in STT_MODEL_BY_SIZE.values()
    ]
    return JSONResponse({"options": options})
