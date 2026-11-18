# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Composition root for the Whisper/Piper artifact download services.

This module wires :class:`WhisperModelService` and :class:`PiperVoiceService`
as application-wide lazy singletons so any application-layer call site can
reach the shared runtime instance without FastAPI dependency injection. A
single neutral module avoids import cycles between feature ``api.deps`` and
``queries`` modules.
"""

from __future__ import annotations

from app.shared.infrastructure.gateways.piper_voice import PiperVoiceService
from app.shared.infrastructure.gateways.whisper_model import WhisperModelService

_default_whisper_model_service: WhisperModelService | None = None
_default_piper_voice_service: PiperVoiceService | None = None


def get_default_whisper_model_service() -> WhisperModelService:
    """Return the application-wide ``WhisperModelService`` singleton.

    Returns:
        The shared instance, creating it lazily on first access.
    """
    global _default_whisper_model_service
    if _default_whisper_model_service is None:
        _default_whisper_model_service = WhisperModelService()
    return _default_whisper_model_service


def set_default_whisper_model_service(service: WhisperModelService | None) -> None:
    """Override the shared Whisper model service (used by tests).

    Args:
        service: Replacement instance, or ``None`` to reset to a fresh default.
    """
    global _default_whisper_model_service
    _default_whisper_model_service = service


def get_default_piper_voice_service() -> PiperVoiceService:
    """Return the application-wide ``PiperVoiceService`` singleton.

    Returns:
        The shared instance, creating it lazily on first access.
    """
    global _default_piper_voice_service
    if _default_piper_voice_service is None:
        _default_piper_voice_service = PiperVoiceService()
    return _default_piper_voice_service


def set_default_piper_voice_service(service: PiperVoiceService | None) -> None:
    """Override the shared Piper voice service (used by tests).

    Args:
        service: Replacement instance, or ``None`` to reset to a fresh default.
    """
    global _default_piper_voice_service
    _default_piper_voice_service = service
