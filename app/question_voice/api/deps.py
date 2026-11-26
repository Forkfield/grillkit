# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""FastAPI dependencies for question-voice API handlers."""

from typing import Annotated

from fastapi import Depends

from app.question_voice.queries.voice_status import VoiceStatus
from app.shared.infrastructure.artifact_composition import (
    get_default_silero_voice_service,
)
from app.shared.infrastructure.gateways.silero_voice import SileroVoiceService


def get_silero_voice_service() -> SileroVoiceService:
    """Return the shared Silero voice service instance (FastAPI dependency)."""
    return get_default_silero_voice_service()


SileroVoiceServiceDep = Annotated[
    SileroVoiceService,
    Depends(get_silero_voice_service),
]


def get_voice_status_service() -> type[VoiceStatus]:
    """Return the voice status service class used by API handlers."""
    return VoiceStatus


VoiceStatusServiceDep = Annotated[
    type[VoiceStatus],
    Depends(get_voice_status_service),
]
