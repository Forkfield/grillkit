# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Configuration API endpoints (JSON)."""

from fastapi import APIRouter

from app.platform.api.deps import (
    AddLLMModelUseCaseDep,
    ConfigServiceDep,
    DeleteConfigUseCaseDep,
    ManageCatalogUseCaseDep,
    SaveConfigUseCaseDep,
)
from app.platform.domain.config import ConfigService
from app.platform.queries.platform_page import build_page_context
from app.platform.schemas import (
    AddLLMModelResponse,
    CatalogActionResult,
    ConfigPageContext,
    ConfigSaveResponse,
    ConfigTestResponse,
    DiscoverModelsResponse,
    LLMModelForm,
    LLMProviderForm,
    NewLLMModel,
    SaveConfigBody,
)
from app.platform.use_cases.manage_catalog import CatalogActionResult as _Result
from app.question_voice.api.deps import VoiceStatusServiceDep
from app.question_voice.queries.voice_status import VoiceStatus
from app.shared.infrastructure.gateways.whisper_model import WhisperModelService
from app.speech.api.deps import WhisperModelServiceDep

router = APIRouter(prefix="/api/config", tags=["config"])


async def _catalog_action_response(
    result: _Result,
    config_service: ConfigService,
    whisper_model_service: WhisperModelService,
    voice_status_service: type[VoiceStatus],
) -> CatalogActionResult:
    """Build the catalog mutation response with a fresh page context."""
    page = await build_page_context(
        config=config_service.get_config(),
        whisper_model_service=whisper_model_service,
        voice_status_service=voice_status_service,
        error=result.error,
        message=result.message,
    )
    return CatalogActionResult(
        error=result.error,
        message=result.message,
        page=page,
    )


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


@router.post("/providers")
async def create_provider(
    body: LLMProviderForm,
    config_service: ConfigServiceDep,
    whisper_model_service: WhisperModelServiceDep,
    voice_status_service: VoiceStatusServiceDep,
    manage_catalog: ManageCatalogUseCaseDep,
) -> CatalogActionResult:
    """Add a provider after probing its endpoint."""
    result = await manage_catalog.create_provider(body)
    return await _catalog_action_response(
        result, config_service, whisper_model_service, voice_status_service
    )


@router.put("/providers/{provider_id}")
async def update_provider(
    provider_id: str,
    body: LLMProviderForm,
    config_service: ConfigServiceDep,
    whisper_model_service: WhisperModelServiceDep,
    voice_status_service: VoiceStatusServiceDep,
    manage_catalog: ManageCatalogUseCaseDep,
) -> CatalogActionResult:
    """Update a provider, probing changed connection details."""
    result = await manage_catalog.update_provider(provider_id, body)
    return await _catalog_action_response(
        result, config_service, whisper_model_service, voice_status_service
    )


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    config_service: ConfigServiceDep,
    whisper_model_service: WhisperModelServiceDep,
    voice_status_service: VoiceStatusServiceDep,
    manage_catalog: ManageCatalogUseCaseDep,
) -> CatalogActionResult:
    """Remove a provider and all of its models."""
    result = manage_catalog.delete_provider(provider_id)
    return await _catalog_action_response(
        result, config_service, whisper_model_service, voice_status_service
    )


@router.post("/providers/{provider_id}/models")
async def add_provider_model(
    provider_id: str,
    body: LLMModelForm,
    config_service: ConfigServiceDep,
    whisper_model_service: WhisperModelServiceDep,
    voice_status_service: VoiceStatusServiceDep,
    manage_catalog: ManageCatalogUseCaseDep,
) -> CatalogActionResult:
    """Add a model under a provider after probing it."""
    result = await manage_catalog.add_model(provider_id, body)
    return await _catalog_action_response(
        result, config_service, whisper_model_service, voice_status_service
    )


@router.put("/providers/{provider_id}/models/{model_id}")
async def update_provider_model(
    provider_id: str,
    model_id: str,
    body: LLMModelForm,
    config_service: ConfigServiceDep,
    whisper_model_service: WhisperModelServiceDep,
    voice_status_service: VoiceStatusServiceDep,
    manage_catalog: ManageCatalogUseCaseDep,
) -> CatalogActionResult:
    """Update a model that belongs to a provider."""
    result = await manage_catalog.update_model(provider_id, model_id, body)
    return await _catalog_action_response(
        result, config_service, whisper_model_service, voice_status_service
    )


@router.delete("/providers/{provider_id}/models/{model_id}")
async def delete_provider_model(
    provider_id: str,
    model_id: str,
    config_service: ConfigServiceDep,
    whisper_model_service: WhisperModelServiceDep,
    voice_status_service: VoiceStatusServiceDep,
    manage_catalog: ManageCatalogUseCaseDep,
) -> CatalogActionResult:
    """Remove a model from a provider."""
    result = manage_catalog.delete_model(provider_id, model_id)
    return await _catalog_action_response(
        result, config_service, whisper_model_service, voice_status_service
    )


@router.post("/providers/{provider_id}/discover-models")
async def discover_provider_models(
    provider_id: str,
    manage_catalog: ManageCatalogUseCaseDep,
) -> DiscoverModelsResponse:
    """List the models the provider endpoint reports."""
    result = await manage_catalog.discover_models(provider_id)
    return DiscoverModelsResponse(models=result.models, error=result.error)
