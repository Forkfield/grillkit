# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the Silero voice catalog."""

import pytest

from app.shared.locales import SUPPORTED_LOCALES
from app.shared.tts_voices import (
    LEGACY_PIPER_VOICE_REMAP,
    SILERO_VOICES_BY_ID,
    default_voice_for_locale,
    normalize_tts_voice_id,
    voice_spec_for_id,
)


class TestNormalizeTtsVoiceId:
    """Tests for normalize_tts_voice_id."""

    def test_accepts_catalog_ids(self):
        """Catalog ids normalize to themselves."""
        assert normalize_tts_voice_id("ru-aidar") == "ru-aidar"

    @pytest.mark.parametrize(
        "legacy_id, expected",
        sorted(LEGACY_PIPER_VOICE_REMAP.items()),
    )
    def test_remaps_legacy_piper_ids(self, legacy_id, expected):
        """Legacy Piper ids from old config files map to Silero voices."""
        assert normalize_tts_voice_id(legacy_id) == expected

    def test_strips_whitespace(self):
        """Surrounding whitespace is ignored."""
        assert normalize_tts_voice_id("  ru-aidar  ") == "ru-aidar"

    def test_rejects_unknown_ids(self):
        """Unknown ids raise with a supported-ids message."""
        with pytest.raises(ValueError, match="Unsupported TTS voice id"):
            _ = normalize_tts_voice_id("xx-nonexistent")


class TestVoiceSpecs:
    """Tests for catalog entry invariants."""

    def test_every_entry_has_silero_package_url(self):
        """All catalog entries point at the Silero model host."""
        for spec in SILERO_VOICES_BY_ID.values():
            assert spec.package_url.startswith("https://models.silero.ai/models/tts/")

    def test_every_entry_has_download_metadata(self):
        """All catalog entries carry size and sample-rate hints."""
        for spec in SILERO_VOICES_BY_ID.values():
            assert spec.approx_download_mb > 0
            assert spec.sample_rate in (8000, 24000, 48000)
            assert spec.speaker
            assert spec.model_id

    def test_spec_lookup_round_trip(self):
        """voice_spec_for_id returns the catalog entry for its own id."""
        spec = voice_spec_for_id("ru-aidar")
        assert spec.model_id == "v5_5_ru"
        assert spec.speaker == "aidar"


class TestDefaultVoiceForLocale:
    """Tests for default_voice_for_locale."""

    @pytest.mark.parametrize("locale", sorted(SUPPORTED_LOCALES))
    def test_every_supported_locale_has_a_default(self, locale):
        """Each supported interview locale has a default Silero voice."""
        voice_id = default_voice_for_locale(locale)
        assert voice_id in SILERO_VOICES_BY_ID
        assert SILERO_VOICES_BY_ID[voice_id].locale == locale

    def test_rejects_unsupported_locale(self):
        """Unsupported locales raise."""
        with pytest.raises(ValueError, match="Unsupported locale"):
            _ = default_voice_for_locale("xx")
