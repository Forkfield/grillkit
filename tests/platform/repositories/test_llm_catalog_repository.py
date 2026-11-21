# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for LLMCatalogRepository atomic write behaviour (S12)."""

import json
from unittest.mock import patch

import pytest

from app.platform.repo.llm_catalog_repository import LLMCatalogRepository
from app.platform.schemas import NewLLMModel


def _repo(tmp_path) -> tuple[LLMCatalogRepository, object]:
    """Build a catalog repository bound to a temporary JSON file."""
    path = tmp_path / "llm_models.json"
    return LLMCatalogRepository(path=path, data_dir=tmp_path), path


def test_save_replaces_file_leaving_valid_json(tmp_path):
    """set_selected rewrites the file via os.replace, leaving valid JSON."""
    repo, path = _repo(tmp_path)
    repo.add_user_model(
        NewLLMModel(
            display_name="Cloud",
            base_url="https://api.example.com/v1",
            model="gpt-4",
        )
    )
    repo.add_user_model(
        NewLLMModel(
            display_name="Local",
            base_url="http://localhost",
            model="llama",
        )
    )

    catalog = repo.load()
    assert catalog.selected_id is not None
    assert len(catalog.models) == 2
    # File is valid JSON with no leftover temp files.
    json.loads(path.read_text())
    assert [p for p in tmp_path.iterdir() if p.suffix == ".tmp"] == []


def test_write_cleans_temp_on_failure(tmp_path):
    """A failed write cleans up its temp file and leaves no partial target."""
    repo = _repo(tmp_path)[0]
    payload = NewLLMModel(
        display_name="Cloud",
        base_url="https://api.example.com/v1",
        model="gpt-4",
    )
    repo.add_user_model(payload)

    with patch("os.replace", side_effect=OSError("boom")), pytest.raises(OSError):
        repo.set_selected("cloud")

    assert [p for p in tmp_path.iterdir() if p.suffix == ".tmp"] == []
