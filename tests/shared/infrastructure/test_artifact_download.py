# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for shared artifact download state."""

from app.shared.infrastructure.gateways.piper_voice import PiperVoiceService
from app.shared.infrastructure.gateways.whisper_model import WhisperModelService


def test_whisper_and_piper_have_separate_download_state():
    """Whisper and Piper must not share download lock or active key."""
    whisper = WhisperModelService()
    piper = PiperVoiceService()

    whisper.reset_download_state()
    piper.reset_download_state()

    assert whisper._download_lock is not piper._download_lock

    whisper._active_key = "small"
    whisper._percent = 42

    assert whisper.is_downloading("small")
    assert not piper.is_downloading("small")
    assert piper.download_percent() == 0

    whisper.reset_download_state()
    piper.reset_download_state()
