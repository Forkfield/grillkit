# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""FastAPI dependencies for question-voice API handlers."""

from typing import Annotated

from fastapi import Depends

from app.question_voice.queries.voice_status import VoiceStatus
from app.shared.infrastructure.artifact_composition import (
    get_default_piper_voice_service,
)
from app.shared.infrastructure.gateways.piper_voice import PiperVoiceService


def get_piper_voice_service() -> PiperVoiceService:
    """Return the shared Piper voice service instance (FastAPI dependency)."""
    return get_default_piper_voice_service()


PiperVoiceServiceDep = Annotated[
    PiperVoiceService,
    Depends(get_piper_voice_service),
]


def get_voice_status_service() -> type[VoiceStatus]:
    """Return the voice status service class used by API handlers."""
    return VoiceStatus


VoiceStatusServiceDep = Annotated[
    type[VoiceStatus],
    Depends(get_voice_status_service),
]
