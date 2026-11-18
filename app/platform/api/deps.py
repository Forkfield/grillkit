# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""FastAPI dependencies for platform (config) API handlers."""

from typing import Annotated

from fastapi import Depends, Request

from app.platform.domain.speech_runtime import SpeechRuntimeCoordinator
from app.platform.repo.config_composition import ConfigServiceDep, LLMCatalogServiceDep
from app.platform.use_cases.add_llm_model import AddLLMModelUseCase
from app.platform.use_cases.delete_config import DeleteConfigUseCase
from app.platform.use_cases.save_config import SaveConfigUseCase
from app.question_voice.api.deps import VoiceStatusServiceDep
from app.speech.api.deps import WhisperModelServiceDep

# Re-export the shared config service dependency so API routers can `Depends`
# on it from ``app.platform.api.deps`` as before.
__all__ = ["ConfigServiceDep"]


def get_add_llm_model_use_case(
    config_service: ConfigServiceDep,
    catalog_service: LLMCatalogServiceDep,
) -> AddLLMModelUseCase:
    """Return the add-model use case wired with its services."""
    return AddLLMModelUseCase(
        config_service=config_service,
        llm_catalog_service=catalog_service,
    )


AddLLMModelUseCaseDep = Annotated[
    AddLLMModelUseCase,
    Depends(get_add_llm_model_use_case),
]


def get_save_config_use_case(
    request: Request,
    config_service: ConfigServiceDep,
    catalog_service: LLMCatalogServiceDep,
    whisper_model_service: WhisperModelServiceDep,
    voice_status_service: VoiceStatusServiceDep,
) -> SaveConfigUseCase:
    """Return the save-config use case wired with app-lifetime services."""
    return SaveConfigUseCase(
        config_service=config_service,
        catalog_service=catalog_service,
        coordinator=request.app.state.speech_runtime,
        whisper_model_service=whisper_model_service,
        voice_status_service=voice_status_service,
    )


SaveConfigUseCaseDep = Annotated[
    SaveConfigUseCase,
    Depends(get_save_config_use_case),
]


def get_delete_config_use_case(
    request: Request,
    config_service: ConfigServiceDep,
) -> DeleteConfigUseCase:
    """Return the delete-config use case wired with app-lifetime services."""
    return DeleteConfigUseCase(
        config_service=config_service,
        coordinator=request.app.state.speech_runtime,
    )


DeleteConfigUseCaseDep = Annotated[
    DeleteConfigUseCase,
    Depends(get_delete_config_use_case),
]


def get_speech_runtime(request: Request) -> SpeechRuntimeCoordinator:
    """Return the app-lifetime speech runtime coordinator."""
    coordinator = request.app.state.speech_runtime
    assert isinstance(coordinator, SpeechRuntimeCoordinator), (
        "speech runtime not initialized"
    )
    return coordinator


SpeechRuntimeDep = Annotated[
    SpeechRuntimeCoordinator,
    Depends(get_speech_runtime),
]
