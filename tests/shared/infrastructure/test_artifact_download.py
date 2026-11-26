# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for shared artifact download state."""

from app.shared.infrastructure.gateways.silero_voice import SileroVoiceService
from app.shared.infrastructure.gateways.whisper_model import WhisperModelService


def test_whisper_and_silero_have_separate_download_state():
    """Whisper and Silero must not share download lock or active key."""
    whisper = WhisperModelService()
    silero = SileroVoiceService()

    whisper.reset_download_state()
    silero.reset_download_state()

    assert whisper._download_lock is not silero._download_lock

    whisper._active_key = "small"
    whisper._percent = 42

    assert whisper.is_downloading("small")
    assert not silero.is_downloading("small")
    assert silero.download_percent() == 0

    whisper.reset_download_state()
    silero.reset_download_state()
