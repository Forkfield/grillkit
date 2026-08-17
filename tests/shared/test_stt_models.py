# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for speech model domain metadata."""

import pytest

from app.shared.stt_models import (
    STT_MODEL_BY_SIZE,
    normalize_stt_model_size,
    stt_model_spec_for_size,
)


def test_all_sizes_have_specs():
    """Every supported size has metadata and a Hugging Face repo id."""
    for size in ("small", "medium", "large"):
        spec = stt_model_spec_for_size(size)
        assert spec.size == size
        assert spec.hf_repo_id.startswith("Systran/")


def test_normalize_stt_model_size():
    """Size codes are normalized to lowercase."""
    assert normalize_stt_model_size(" Medium ") == "medium"


def test_normalize_rejects_unknown_size():
    """Unknown sizes raise ValueError."""
    with pytest.raises(ValueError, match="Unsupported stt model size"):
        normalize_stt_model_size("xl")


def test_specs_cover_expected_sizes():
    """Registry contains small, medium, and large entries."""
    assert set(STT_MODEL_BY_SIZE) == {"small", "medium", "large"}
