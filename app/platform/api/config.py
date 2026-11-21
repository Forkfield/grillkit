# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Configuration API endpoints (JSON)."""

from fastapi import APIRouter

from app.platform.api.deps import (
    AddLLMModelUseCaseDep,
    ConfigServiceDep,
    DeleteConfigUseCaseDep,
    SaveConfigUseCaseDep,
)
from app.platform.queries.platform_page import build_page_context
from app.platform.schemas import (
    AddLLMModelResponse,
    ConfigPageContext,
    ConfigSaveResponse,
    ConfigTestResponse,
    NewLLMModel,
    SaveConfigBody,
)
from app.question_voice.api.deps import VoiceStatusServiceDep
from app.speech.api.deps import WhisperModelServiceDep

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def config_page(
    config_service: ConfigServiceDep,
    whisper_model_service: WhisperModelServiceDep,
    voice_status_service: VoiceStatusServiceDep,
) -> ConfigPageContext:
    """Return the full configuration page context."""
    return await build_page_context(
        config=config_service.get_config(),
        whisper_model_service=whisper_model_service,
        voice_status_service=voice_status_service,
    )


@router.post("")
async def save_config(
    body: SaveConfigBody,
    save_config: SaveConfigUseCaseDep,
) -> ConfigSaveResponse:
    """Validate and persist the configuration, then return fresh context."""
    return await save_config.execute(body)


@router.delete("")
async def delete_config(
    config_service: ConfigServiceDep,
    whisper_model_service: WhisperModelServiceDep,
    voice_status_service: VoiceStatusServiceDep,
    delete_config: DeleteConfigUseCaseDep,
) -> ConfigSaveResponse:
    """Remove the configuration and return fresh (empty) context."""
    delete_config.execute()
    page = await build_page_context(
        config=config_service.get_config(),
        whisper_model_service=whisper_model_service,
        voice_status_service=voice_status_service,
        message="Configuration removed",
    )
    return ConfigSaveResponse(
        success=True,
        message="Configuration removed",
        page=page,
    )


@router.post("/test")
async def test_config(
    body: SaveConfigBody,
    save_config: SaveConfigUseCaseDep,
) -> ConfigTestResponse:
    """Test the connection without saving."""
    return await save_config.test(body)


@router.post("/llm-models")
async def add_llm_model(
    body: NewLLMModel,
    config_service: ConfigServiceDep,
    whisper_model_service: WhisperModelServiceDep,
    voice_status_service: VoiceStatusServiceDep,
    add_model: AddLLMModelUseCaseDep,
) -> AddLLMModelResponse:
    """Add a user-defined OpenAI-compatible model to the catalog."""
    result = await add_model.execute(body)
    page = await build_page_context(
        config=config_service.get_config(),
        whisper_model_service=whisper_model_service,
        voice_status_service=voice_status_service,
        error=result.error,
        message=result.message,
        selected_llm_preset_id=result.selected_preset_id,
    )
    return AddLLMModelResponse(
        error=result.error,
        message=result.message,
        selected_preset_id=result.selected_preset_id,
        page=page,
    )
