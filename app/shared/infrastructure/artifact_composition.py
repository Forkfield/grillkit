# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Composition root for the Whisper/Silero artifact download services.

This module wires :class:`WhisperModelService` and :class:`SileroVoiceService`
as application-wide lazy singletons so any application-layer call site can
reach the shared runtime instance without FastAPI dependency injection. A
single neutral module avoids import cycles between feature ``api.deps`` and
``queries`` modules.
"""

from __future__ import annotations

from app.shared.infrastructure.gateways.silero_voice import SileroVoiceService
from app.shared.infrastructure.gateways.whisper_model import WhisperModelService

_default_whisper_model_service: WhisperModelService | None = None
_default_silero_voice_service: SileroVoiceService | None = None


def get_default_whisper_model_service() -> WhisperModelService:
    """Return the application-wide ``WhisperModelService`` singleton.

    Returns:
        The shared instance, creating it lazily on first access.
    """
    global _default_whisper_model_service
    if _default_whisper_model_service is None:
        _default_whisper_model_service = WhisperModelService()
    return _default_whisper_model_service


def get_default_silero_voice_service() -> SileroVoiceService:
    """Return the application-wide ``SileroVoiceService`` singleton.

    Returns:
        The shared instance, creating it lazily on first access.
    """
    global _default_silero_voice_service
    if _default_silero_voice_service is None:
        _default_silero_voice_service = SileroVoiceService()
    return _default_silero_voice_service
