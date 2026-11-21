# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""FastAPI dependencies for speech feature API handlers."""

from typing import Annotated

from fastapi import Depends

from app.shared.infrastructure.artifact_composition import (
    get_default_whisper_model_service,
)
from app.shared.infrastructure.gateways.whisper_model import WhisperModelService


def get_whisper_model_service() -> WhisperModelService:
    """Return the shared Whisper model service instance (FastAPI dependency)."""
    return get_default_whisper_model_service()


WhisperModelServiceDep = Annotated[
    WhisperModelService,
    Depends(get_whisper_model_service),
]
