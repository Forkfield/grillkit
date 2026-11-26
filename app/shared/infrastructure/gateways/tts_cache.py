# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Disk cache for synthesized question audio."""

import hashlib
from pathlib import Path
import re

from app.shared.infrastructure.gateways.tts_exceptions import (
    QuestionVoiceSynthesisError,
)
from app.shared.locales import normalize_locale
from app.shared.paths import TTS_CACHE_DIR
from app.shared.tts_terms import apply_term_substitutions
from app.speech.domain.tts_engine import TtsEngine

_WHITESPACE_RE = re.compile(r"\s+")
_CACHE_VERSION = "v3"


class TtsCacheService:
    """Store and retrieve WAV files under ``data/tts-cache/v3/{locale}/``."""

    @staticmethod
    def normalize_text(text: str) -> str:
        """Collapse whitespace for stable cache keys.

        Args:
            text: Prepared question text snapshot.

        Returns:
            Normalized text used for hashing.
        """
        return _WHITESPACE_RE.sub(" ", text.strip())

    @staticmethod
    def cache_path(locale: str, text: str) -> Path:
        """Build the on-disk path for a cached WAV file.

        Args:
            locale: Interview locale code.
            text: Prepared question text (term substitutions applied).

        Returns:
            Path to ``{sha256}.wav`` under the locale directory.
        """
        code = normalize_locale(locale)
        digest = hashlib.sha256(
            TtsCacheService.normalize_text(text).encode("utf-8")
        ).hexdigest()
        return TTS_CACHE_DIR / _CACHE_VERSION / code / f"{digest}.wav"

    @staticmethod
    async def get_or_fetch(
        engine: TtsEngine,
        voice_id: str,
        locale: str,
        text: str,
    ) -> Path:
        """Return a cached WAV path, synthesizing on miss.

        The raw question text is prepared with the terms dictionary first, so
        the cache key covers both the question text and the current
        substitutions, and the engine never receives dropped Latin terms.

        Args:
            engine: TTS engine used to synthesize on a cache miss.
            voice_id: Silero voice id from provider configuration.
            locale: Interview locale code.
            text: Raw question text snapshot.

        Returns:
            Path to an existing or newly written WAV file.

        Raises:
            QuestionVoiceSynthesisError: When the voice is missing or synthesis fails.
        """
        prepared = apply_term_substitutions(text, locale)
        path = TtsCacheService.cache_path(locale, prepared)
        if path.is_file():
            return path

        if not engine.is_installed(voice_id):
            raise QuestionVoiceSynthesisError(
                "Question voice is not installed. Download it on the Configuration page."
            )

        if not engine.is_loaded(voice_id):
            loaded = await engine.load_voice(voice_id)
            if not loaded:
                detail = engine.load_error() or "Could not load question voice."
                raise QuestionVoiceSynthesisError(detail)

        try:
            audio = await engine.synthesize_wav_bytes(prepared)
        except Exception as exc:
            raise QuestionVoiceSynthesisError("TTS synthesis failed.") from exc

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        return path
