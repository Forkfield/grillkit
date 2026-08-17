# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Whisper speech model metadata and normalization shared across features."""

from dataclasses import dataclass
from typing import Final, Literal

SttModelSize = Literal["small", "medium", "large"]
DEFAULT_STT_MODEL_SIZE: Final[SttModelSize] = "small"
STT_MODEL_SIZES: Final[tuple[SttModelSize, ...]] = (
    "small",
    "medium",
    "large",
)


@dataclass(frozen=True)
class SttModelSpec:
    """Published faster-whisper model for one size tier.

    Attributes:
        size: Model size identifier.
        display_name: Human-readable label for UI.
        hf_repo_id: Hugging Face repository id for snapshot download.
        approx_download_mb: Approximate download size for trade-off hints.
        ram_hint: Suggested RAM for running the model.
        speed_hint: Relative speed expectation on CPU.
        quality_hint: Relative transcription quality.
    """

    size: SttModelSize
    display_name: str
    hf_repo_id: str
    approx_download_mb: int
    ram_hint: str
    speed_hint: str
    quality_hint: str


STT_MODEL_BY_SIZE: Final[dict[SttModelSize, SttModelSpec]] = {
    "small": SttModelSpec(
        size="small",
        display_name="Whisper small",
        hf_repo_id="Systran/faster-whisper-small",
        approx_download_mb=500,
        ram_hint="~1 GB",
        speed_hint="Fastest on CPU",
        quality_hint="Good for short answers",
    ),
    "medium": SttModelSpec(
        size="medium",
        display_name="Whisper medium",
        hf_repo_id="Systran/faster-whisper-medium",
        approx_download_mb=1500,
        ram_hint="~2–3 GB",
        speed_hint="Slower on CPU",
        quality_hint="Better accuracy and noise handling",
    ),
    "large": SttModelSpec(
        size="large",
        display_name="Whisper large",
        hf_repo_id="Systran/faster-whisper-large-v3",
        approx_download_mb=3000,
        ram_hint="~4+ GB",
        speed_hint="Slowest; best with GPU",
        quality_hint="Highest accuracy",
    ),
}


def normalize_stt_model_size(size: str) -> SttModelSize:
    """Return a supported stt model size or raise ``ValueError``.

    Args:
        size: Requested size (e.g. ``small``, ``medium``).

    Returns:
        Normalized size present in ``STT_MODEL_BY_SIZE``.

    Raises:
        ValueError: If the size is not supported.
    """
    code = size.strip().lower()
    if code not in STT_MODEL_BY_SIZE:
        supported = ", ".join(STT_MODEL_SIZES)
        raise ValueError(
            f"Unsupported stt model size '{size}'. Choose one of: {supported}"
        )
    return code


def stt_model_spec_for_size(size: str) -> SttModelSpec:
    """Return stt model metadata for a supported size.

    Args:
        size: Stt model size identifier.

    Returns:
        Model metadata for the size.

    Raises:
        ValueError: If the size is not supported.
    """
    code = normalize_stt_model_size(size)
    return STT_MODEL_BY_SIZE[code]
