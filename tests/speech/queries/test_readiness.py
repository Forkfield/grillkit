# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for SttModelReadiness."""

from unittest.mock import patch

import pytest

from app.speech.queries.readiness import SttModelReadiness


class TestSttModelReadiness:
    """Tests for SttModelReadiness checks."""

    def test_is_model_installed_true(self):
        """Returns True when model is installed on disk."""
        with patch(
            "app.speech.queries.readiness.is_installed", return_value=True
        ) as mock_installed:
            result = SttModelReadiness.is_model_installed("small")

        assert result is True
        mock_installed.assert_called_once_with("small")

    def test_is_model_installed_false(self):
        """Returns False when model is not installed."""
        with patch(
            "app.speech.queries.readiness.is_installed", return_value=False
        ) as mock_installed:
            result = SttModelReadiness.is_model_installed("medium")

        assert result is False
        mock_installed.assert_called_once_with("medium")

    def test_normalizes_size(self):
        """Normalizes the speech model size before checking."""
        with patch(
            "app.speech.queries.readiness.is_installed", return_value=True
        ) as mock_installed:
            result = SttModelReadiness.is_model_installed(" LARGE ")

        assert result is True
        mock_installed.assert_called_once_with("large")

    def test_invalid_size_raises(self):
        """Raises ValueError for unsupported model sizes."""
        with pytest.raises(ValueError, match="Unsupported stt model size"):
            SttModelReadiness.is_model_installed("huge")
