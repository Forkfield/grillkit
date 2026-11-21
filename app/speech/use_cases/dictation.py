# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Dictation session for buffered PCM audio."""

from app.ai.stt import Stt
from app.shared.infrastructure.audio_wav import (
    CANONICAL_AUDIO_SAMPLE_RATE_HZ,
    pcm16le_to_float32,
)

DICTATION_SAMPLE_RATE_HZ: int = CANONICAL_AUDIO_SAMPLE_RATE_HZ


class DictationSession:
    """Buffered PCM audio transcribed on finalize via a :class:`Stt`.

    Expects 16-bit signed little-endian mono PCM at ``DICTATION_SAMPLE_RATE_HZ``.
    """

    def __init__(self) -> None:
        """Create an empty dictation buffer."""
        self._buffer = bytearray()

    def append_pcm(self, chunk: bytes) -> None:
        """Append raw PCM samples to the session buffer.

        Args:
            chunk: Raw 16-bit LE mono PCM samples.
        """
        if chunk:
            self._buffer.extend(chunk)

    async def finalize(self, transcriber: Stt, locale: str) -> str:
        """Transcribe buffered audio and return the full transcript.

        Args:
            transcriber: Loaded STT engine implementation.
            locale: Interview locale code for recognition language.

        Returns:
            Final recognized text (may be empty).
        """
        if not self._buffer:
            return ""

        audio = pcm16le_to_float32(bytes(self._buffer))
        return await transcriber.transcribe(audio, locale)
