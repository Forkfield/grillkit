# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""On-disk paths and validation for installed Silero voices."""

from pathlib import Path

from app.shared.paths import SILERO_VOICES_ROOT
from app.shared.tts_voices import normalize_tts_voice_id, voice_spec_for_id


def voice_dir(voice_id: str) -> Path:
    """Return the installation directory for a Silero voice id."""
    code = normalize_tts_voice_id(voice_id)
    return SILERO_VOICES_ROOT / code


def model_path(voice_id: str) -> Path:
    """Return the on-disk ``.pt`` package path for a Silero voice id."""
    spec = voice_spec_for_id(voice_id)
    return voice_dir(voice_id) / f"{spec.model_id}.pt"


def is_valid_voice_dir(path: Path, voice_id: str) -> bool:
    """Return whether ``path`` contains the Silero model package for ``voice_id``.

    Args:
        path: Directory that may hold ``<model_id>.pt``.
        voice_id: Silero voice identifier (file name prefix, not ``path.name``).
    """
    if not path.is_dir():
        return False
    code = normalize_tts_voice_id(voice_id)
    spec = voice_spec_for_id(code)
    return (path / f"{spec.model_id}.pt").is_file()


def is_voice_installed(voice_id: str) -> bool:
    """Return whether a valid Silero voice is present for the id."""
    return is_valid_voice_dir(voice_dir(voice_id), voice_id)
