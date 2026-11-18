# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Config repository: read/write ``data/config.json`` as a domain object.

This module owns all filesystem access to the application configuration file.
It maps the persistable application settings (timeout, locale, speech model
size, question voice, TTS voice) to and from an :class:`AppConfig` domain
object and performs atomic writes so a partial write never leaves a corrupt
JSON file behind.

Mapping and I/O live here (the infrastructure layer) rather than inside the
domain :class:`AppConfig`, which stays a plain runtime object.
"""

from __future__ import annotations

from contextlib import suppress
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from app.platform.domain.config import AppConfig, ConfigRepositoryProtocol
from app.shared.locales import DEFAULT_LOCALE, normalize_locale
from app.shared.paths import CONFIG_PATH, DATA_DIR
from app.shared.stt_models import (
    DEFAULT_STT_MODEL_SIZE,
    normalize_stt_model_size,
)
from app.shared.tts_voices import (
    default_voice_for_locale,
    normalize_tts_voice_id,
)


class ConfigRepository(ConfigRepositoryProtocol):
    """Read and persist application configuration in ``config.json``.

    The repository is the single entry point for ``config.json`` I/O. It maps
    the file directly to an :class:`AppConfig` domain object and back, and
    guarantees atomic writes via a temp file plus ``os.replace``.
    """

    def __init__(self, path: Path | None = None, data_dir: Path | None = None) -> None:
        """Initialize the repository with the target config file path.

        When a path is omitted, the canonical :data:`CONFIG_PATH` and
        :data:`DATA_DIR` are resolved lazily on each call, so tests can
        override them via monkeypatch.

        Args:
            path: Absolute path of the ``config.json`` file, if overriding.
            data_dir: Parent directory created on first write, if overriding.
        """
        self._path = path
        self._data_dir = data_dir

    def _resolve_path(self) -> Path:
        """Return the effective config file path."""
        return self._path if self._path is not None else CONFIG_PATH

    def _resolve_data_dir(self) -> Path:
        """Return the effective parent data directory."""
        return self._data_dir if self._data_dir is not None else DATA_DIR

    def exists(self) -> bool:
        """Return whether a configuration file exists on disk."""
        return self._resolve_path().exists()

    def load(self) -> AppConfig | None:
        """Load the configuration from disk.

        Returns:
            :class:`AppConfig` when ``config.json`` exists, otherwise ``None``.
        """
        path = self._resolve_path()
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return self._to_domain(data)

    def save(self, config: AppConfig) -> None:
        """Persist application settings atomically to ``config.json``.

        Args:
            config: Domain configuration to persist.
        """
        data_dir = self._resolve_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        payload = self._to_storage(config)
        self._atomic_write(json.dumps(payload, indent=2), data_dir)

    def delete(self) -> None:
        """Remove the configuration file if present."""
        path = self._resolve_path()
        if path.exists():
            path.unlink()

    def _atomic_write(self, content: str, data_dir: Path) -> None:
        """Write ``content`` atomically via a temp file and ``os.replace``.

        Args:
            content: Serialized JSON payload to persist.
            data_dir: Directory that holds the target file (for the temp file).
        """
        fd, tmp_name = tempfile.mkstemp(
            dir=str(data_dir),
            prefix=f".{self._resolve_path().name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(content)
            os.replace(tmp_name, self._resolve_path())
        except BaseException:
            with suppress(FileNotFoundError):
                os.unlink(tmp_name)
            raise

    def _to_domain(self, data: dict[str, Any]) -> AppConfig:
        """Map a ``config.json`` dictionary to an :class:`AppConfig` domain object.

        Args:
            data: Persistable application settings read from disk.

        Returns:
            ``AppConfig`` with provider fields left empty (they are resolved
            from the catalog separately).
        """
        locale = normalize_locale(data.get("locale", DEFAULT_LOCALE))
        raw_voice_id = data.get("tts_voice_id")
        if raw_voice_id:
            tts_voice_id = normalize_tts_voice_id(str(raw_voice_id))
        else:
            tts_voice_id = default_voice_for_locale(locale)
        return AppConfig(
            timeout=data.get("timeout", 60.0),
            locale=locale,
            speech_model_size=normalize_stt_model_size(
                data.get("speech_model_size", DEFAULT_STT_MODEL_SIZE)
            ),
            question_voice_enabled=bool(data.get("question_voice_enabled", False)),
            tts_voice_id=tts_voice_id,
        )

    def _to_storage(self, config: AppConfig) -> dict[str, Any]:
        """Map an :class:`AppConfig` to the persistable ``config.json`` dictionary.

        Args:
            config: Domain configuration to persist.

        Returns:
            Application settings only (LLM provider data lives in the catalog).
        """
        return {
            "timeout": config.timeout,
            "locale": config.locale,
            "speech_model_size": config.speech_model_size,
            "question_voice_enabled": config.question_voice_enabled,
            "tts_voice_id": config.tts_voice_id,
        }
