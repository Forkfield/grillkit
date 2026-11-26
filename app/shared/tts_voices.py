# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Silero TTS voice metadata shared across platform and question-voice features."""

from dataclasses import dataclass
from typing import Final

from app.shared.locales import normalize_locale

DEFAULT_TTS_VOICE_ID: Final[str] = "en-en_0"
DEFAULT_TTS_SAMPLE_RATE_HZ: Final[int] = 24000


@dataclass(frozen=True)
class SileroVoiceSpec:
    """Published Silero voice for one locale tier.

    Attributes:
        voice_id: Silero voice identifier (directory name under silero-voices).
        locale: GrillKit interview locale code this voice supports.
        model_id: Silero model generation serving this voice (e.g. ``v5_5_ru``).
        speaker: Speaker name inside the model package (e.g. ``aidar``).
        display_name: Human-readable label for UI.
        package_url: Direct ``models.silero.ai`` URL of the ``.pt`` package.
        approx_download_mb: Approximate download size for trade-off hints.
        sample_rate: Synthesis sample rate in hertz.
        quality_hint: Relative synthesis quality expectation.
    """

    voice_id: str
    locale: str
    model_id: str
    speaker: str
    display_name: str
    package_url: str
    approx_download_mb: int
    sample_rate: int
    quality_hint: str


SILERO_VOICES_BY_ID: Final[dict[str, SileroVoiceSpec]] = {
    "en-en_0": SileroVoiceSpec(
        voice_id="en-en_0",
        locale="en",
        model_id="v3_en",
        speaker="en_0",
        display_name="en_0 (US English)",
        package_url="https://models.silero.ai/models/tts/en/v3_en.pt",
        approx_download_mb=57,
        sample_rate=DEFAULT_TTS_SAMPLE_RATE_HZ,
        quality_hint="Clear English; good default for interviews",
    ),
    "ru-aidar": SileroVoiceSpec(
        voice_id="ru-aidar",
        locale="ru",
        model_id="v5_5_ru",
        speaker="aidar",
        display_name="Aidar (Russian)",
        package_url="https://models.silero.ai/models/tts/ru/v5_5_ru.pt",
        approx_download_mb=139,
        sample_rate=DEFAULT_TTS_SAMPLE_RATE_HZ,
        quality_hint="Natural Russian with auto-stress and question intonation",
    ),
    "fr-fr_0": SileroVoiceSpec(
        voice_id="fr-fr_0",
        locale="fr",
        model_id="v3_fr",
        speaker="fr_0",
        display_name="fr_0 (French)",
        package_url="https://models.silero.ai/models/tts/fr/v3_fr.pt",
        approx_download_mb=57,
        sample_rate=DEFAULT_TTS_SAMPLE_RATE_HZ,
        quality_hint="Standard French pronunciation",
    ),
    "es-es_0": SileroVoiceSpec(
        voice_id="es-es_0",
        locale="es",
        model_id="v3_es",
        speaker="es_0",
        display_name="es_0 (Spanish)",
        package_url="https://models.silero.ai/models/tts/es/v3_es.pt",
        approx_download_mb=57,
        sample_rate=DEFAULT_TTS_SAMPLE_RATE_HZ,
        quality_hint="European Spanish",
    ),
    "de-eva_k": SileroVoiceSpec(
        voice_id="de-eva_k",
        locale="de",
        model_id="v3_de",
        speaker="eva_k",
        display_name="eva_k (German)",
        package_url="https://models.silero.ai/models/tts/de/v3_de.pt",
        approx_download_mb=57,
        sample_rate=DEFAULT_TTS_SAMPLE_RATE_HZ,
        quality_hint="Standard German pronunciation",
    ),
}

LEGACY_PIPER_VOICE_REMAP: Final[dict[str, str]] = {
    "en_US-lessac-medium": "en-en_0",
    "ru_RU-dmitri-medium": "ru-aidar",
    "fr_FR-siwis-medium": "fr-fr_0",
    "es_ES-davefx-medium": "es-es_0",
    "de_DE-thorsten-medium": "de-eva_k",
}

_DEFAULT_VOICE_BY_LOCALE: Final[dict[str, str]] = {
    spec.locale: spec.voice_id for spec in SILERO_VOICES_BY_ID.values()
}


def normalize_tts_voice_id(voice_id: str) -> str:
    """Return a supported Silero voice id or raise ``ValueError``.

    Legacy Piper voice ids stored in previously saved ``config.json`` files
    are remapped to their Silero replacements instead of raising, so existing
    installations keep loading without a manual config migration. The
    remapped id is persisted on the next config save.

    Args:
        voice_id: Requested Silero voice identifier (or a legacy Piper id).

    Returns:
        Normalized voice id present in ``SILERO_VOICES_BY_ID``.

    Raises:
        ValueError: If the voice id is not in the catalog.
    """
    code = voice_id.strip()
    if code in SILERO_VOICES_BY_ID:
        return code
    if code in LEGACY_PIPER_VOICE_REMAP:
        return LEGACY_PIPER_VOICE_REMAP[code]
    supported = ", ".join(sorted(SILERO_VOICES_BY_ID))
    raise ValueError(
        f"Unsupported TTS voice id '{voice_id}'. Choose one of: {supported}"
    )


def voice_spec_for_id(voice_id: str) -> SileroVoiceSpec:
    """Return Silero voice metadata for a supported voice id.

    Args:
        voice_id: Silero voice identifier.

    Returns:
        Voice metadata for the id.

    Raises:
        ValueError: If the voice id is not supported.
    """
    code = normalize_tts_voice_id(voice_id)
    return SILERO_VOICES_BY_ID[code]


def default_voice_for_locale(locale: str) -> str:
    """Return the default Silero voice id for a supported locale.

    Args:
        locale: Interview locale code.

    Returns:
        Default ``voice_id`` for the locale.

    Raises:
        ValueError: If the locale is not supported or has no default voice.
    """
    code = normalize_locale(locale)
    voice_id = _DEFAULT_VOICE_BY_LOCALE.get(code)
    if voice_id is None:
        raise ValueError(f"No default TTS voice configured for locale '{locale}'")
    return voice_id
