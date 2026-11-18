# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for ConfigRepository."""

import json
from unittest.mock import patch

import pytest

from app.platform.domain.config import AppConfig
from app.platform.repo.config_repository import ConfigRepository


def _config(**overrides: object) -> AppConfig:
    """Build an AppConfig with defaults overridable per test."""
    base: dict[str, object] = {
        "timeout": 60.0,
        "locale": "en",
        "speech_model_size": "small",
        "question_voice_enabled": False,
        "tts_voice_id": "en_US-lessac-medium",
    }
    base.update(overrides)
    return AppConfig(**base)


def test_load_returns_none_when_missing(tmp_path):
    """load() yields None when config.json does not exist."""
    repo = ConfigRepository(path=tmp_path / "config.json", data_dir=tmp_path)
    assert repo.exists() is False
    assert repo.load() is None


def test_save_then_load_round_trips_stored_fields(tmp_path):
    """save() then load() restores the persistable application settings."""
    repo = ConfigRepository(path=tmp_path / "config.json", data_dir=tmp_path)
    config = _config(timeout=30.0, locale="ru", speech_model_size="large")

    repo.save(config)

    assert repo.exists() is True
    loaded = repo.load()
    assert loaded is not None
    assert loaded.timeout == 30.0
    assert loaded.locale == "ru"
    assert loaded.speech_model_size == "large"
    assert loaded.question_voice_enabled is False
    assert loaded.tts_voice_id == config.tts_voice_id


def test_save_persists_only_shared_fields(tmp_path):
    """save() writes only app settings, not LLM provider data."""
    repo = ConfigRepository(path=tmp_path / "config.json", data_dir=tmp_path)
    repo.save(_config())

    raw = json.loads((tmp_path / "config.json").read_text())
    assert set(raw) == {
        "timeout",
        "locale",
        "speech_model_size",
        "question_voice_enabled",
        "tts_voice_id",
    }
    assert "provider_type" not in raw
    assert "base_url" not in raw
    assert "model" not in raw
    assert "api_key" not in raw
    assert "llm_preset_id" not in raw


def test_load_normalizes_locale_and_voice(tmp_path):
    """load() normalizes locale and picks default voice when voice is unset."""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"timeout": 60.0, "locale": "RU", "tts_voice_id": ""})
    )
    repo = ConfigRepository(path=path, data_dir=tmp_path)

    loaded = repo.load()
    assert loaded is not None
    assert loaded.locale == "ru"  # normalized
    assert loaded.tts_voice_id  # default voice filled in


def test_delete_removes_file(tmp_path):
    """delete() removes config.json when present and is a no-op otherwise."""
    path = tmp_path / "config.json"
    repo = ConfigRepository(path=path, data_dir=tmp_path)
    repo.save(_config())
    assert path.exists()

    repo.delete()
    assert path.exists() is False

    # Delete again must not raise.
    repo.delete()


def test_atomic_write_replaces_file(tmp_path):
    """_atomic_write replaces the target via os.replace, leaving valid JSON."""
    path = tmp_path / "config.json"
    repo = ConfigRepository(path=path, data_dir=tmp_path)
    repo.save(_config(locale="en"))
    repo.save(_config(locale="ru"))

    loaded = repo.load()
    assert loaded is not None
    assert loaded.locale == "ru"


def test_atomic_write_cleans_temp_on_failure(tmp_path):
    """A failed write cleans up its temp file and leaves no partial target."""
    path = tmp_path / "config.json"
    repo = ConfigRepository(path=path, data_dir=tmp_path)

    with patch("os.replace", side_effect=OSError("boom")), pytest.raises(OSError):
        repo.save(_config())

    # No temp files left behind.
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
