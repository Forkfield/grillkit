# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the question-audio cache."""

import pytest

from app.shared.infrastructure.gateways import tts_cache
from app.shared.infrastructure.gateways.tts_cache import TtsCacheService
from app.shared.infrastructure.gateways.tts_exceptions import (
    QuestionVoiceSynthesisError,
)


class FakeEngine:
    """Minimal TtsEngine double recording synthesized text."""

    def __init__(self, *, installed: bool = True) -> None:
        """Initialize with install state and an empty synthesis log."""
        self._installed = installed
        self.synthesized: list[str] = []

    def is_installed(self, voice_id: str) -> bool:
        """Report whether the voice is on disk."""
        del voice_id
        return self._installed

    def is_loaded(self, voice_id: str) -> bool:
        """Report the voice as always loaded."""
        del voice_id
        return True

    def load_error(self) -> str | None:
        """No load errors."""
        return None

    def unload(self) -> None:
        """Nothing to unload."""

    async def load_voice(self, voice_id: str) -> bool:
        """Voice is loaded."""
        del voice_id
        return True

    async def synthesize_wav_bytes(self, text: str) -> bytes:
        """Record the prepared text and return a WAV payload."""
        self.synthesized.append(text)
        return b"RIFF-fake-wav"


class TestCachePath:
    """Tests for cache path layout."""

    def test_uses_v3_directory_per_locale(self):
        """Files live under tts-cache/v3/{locale}/ with .wav suffix."""
        path = TtsCacheService.cache_path("ru", "текст")
        parts = path.parts
        assert "v3" in parts
        assert "ru" in parts
        assert path.name.endswith(".wav")

    def test_ignores_whitespace_differences(self):
        """Whitespace-only changes share one cache key."""
        first = TtsCacheService.cache_path("ru", "один  два")
        second = TtsCacheService.cache_path("ru", " один два ")
        assert first == second


class TestGetOrFetch:
    """Tests for get_or_fetch."""

    @pytest.fixture
    def cache_dir(self, tmp_path, monkeypatch):
        """Redirect the cache root to a temporary directory."""
        monkeypatch.setattr(tts_cache, "TTS_CACHE_DIR", tmp_path)
        return tmp_path

    async def test_applies_substitutions_before_synthesis(self, cache_dir):
        """The engine receives Cyrillic-expanded text for the locale."""
        engine = FakeEngine()
        path = await TtsCacheService.get_or_fetch(
            engine,
            "ru-aidar",
            "ru",
            "Что такое Kubernetes?",
        )
        assert engine.synthesized == ["Что такое кубернетес?"]
        assert path.is_file()
        assert path.read_bytes() == b"RIFF-fake-wav"
        assert "v3" in path.parts

    async def test_second_call_hits_cache(self, cache_dir):
        """A cached path is returned without re-synthesis."""
        engine = FakeEngine()
        text = "Что такое Kubernetes?"
        first = await TtsCacheService.get_or_fetch(engine, "ru-aidar", "ru", text)
        second = await TtsCacheService.get_or_fetch(engine, "ru-aidar", "ru", text)
        assert first == second
        assert engine.synthesized == ["Что такое кубернетес?"]

    async def test_raises_when_voice_not_installed(self, cache_dir):
        """Missing installation fails with a user-facing error."""
        engine = FakeEngine(installed=False)
        with pytest.raises(QuestionVoiceSynthesisError):
            await TtsCacheService.get_or_fetch(
                engine,
                "ru-aidar",
                "ru",
                "текст",
            )
        assert engine.synthesized == []
