# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""LLM catalog repository: read/write ``data/llm_models.json``.

The repository owns all filesystem access to the interview model catalog. It
maps the file directly to an :class:`LLMCatalog` domain object and back, and
guarantees atomic writes so a partial write never leaves a corrupt JSON file
behind. The canonical path is resolved lazily on each call, so tests can
override it via monkeypatch.
"""

from __future__ import annotations

from contextlib import suppress
import json
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Any

from app.ai.llm_models import LLMCatalog, LLMModelEntry, generate_model_id
from app.platform.domain.llm_catalog import LLMCatalogRepositoryProtocol
from app.shared.paths import DATA_DIR, LLM_MODELS_PATH

if TYPE_CHECKING:
    from app.platform.schemas import NewLLMModel


class LLMCatalogRepository(LLMCatalogRepositoryProtocol):
    """Read and persist the interview model catalog in ``llm_models.json``.

    The repository is the single entry point for catalog I/O. It maps the file
    directly to an :class:`LLMCatalog` domain object and back, and guarantees
    atomic writes via a temp file plus ``os.replace``.
    """

    def __init__(self, path: Path | None = None, data_dir: Path | None = None) -> None:
        """Initialize the repository with the target catalog file path.

        When a path is omitted, the canonical :data:`LLM_MODELS_PATH` and
        :data:`DATA_DIR` are resolved lazily on each call, so tests can
        override them via monkeypatch.

        Args:
            path: Absolute path of the ``llm_models.json`` file, if overriding.
            data_dir: Parent directory created on first write, if overriding.
        """
        self._path = path
        self._data_dir = data_dir

    def _resolve_path(self) -> Path:
        """Return the effective catalog file path."""
        return self._path if self._path is not None else LLM_MODELS_PATH

    def _resolve_data_dir(self) -> Path:
        """Return the effective parent data directory."""
        return self._data_dir if self._data_dir is not None else DATA_DIR

    def load(self) -> LLMCatalog:
        """Load the catalog from disk, seeding an empty file when missing.

        Returns:
            Catalog with selected id and all saved models.
        """
        data = self._read()
        models = _parse_models(data["models"])
        selected_id = str(data["selected"]).strip() or None
        return LLMCatalog(selected_id=selected_id, models=models)

    def set_selected(self, model_id: str) -> None:
        """Persist the active interview model id.

        Args:
            model_id: Catalog model id to mark as selected.

        Raises:
            ValueError: If the model id is unknown.
        """
        data = self._read()
        if model_id not in data["models"]:
            raise ValueError(f"Unsupported LLM model: {model_id}")
        data["selected"] = model_id
        self._write(data)

    def add_user_model(self, payload: NewLLMModel) -> LLMModelEntry:
        """Append a model to the catalog and select it.

        The catalog id is derived from the display name and made unique against
        existing entries, so adding a model never fails on id collisions.

        Args:
            payload: Validated add-model form values.

        Returns:
            Persisted catalog entry.
        """
        data = self._read()
        models = dict(data["models"])
        model_id = generate_model_id(payload.display_name, models)

        api_key = payload.api_key
        api_key_required = payload.api_key_required or bool(api_key)
        entry_dict = _model_dict(
            display_name=payload.display_name,
            model_name=payload.model,
            base_url=payload.base_url,
            api_key_required=api_key_required,
            api_key=api_key,
            accepts_audio_input=payload.accepts_audio_input,
        )
        models[model_id] = entry_dict
        data["models"] = models
        data["selected"] = model_id
        self._write(data)
        return _parse_model(model_id, entry_dict)

    def update_model_api_key(self, model_id: str, api_key: str | None) -> None:
        """Persist an API key for a catalog model.

        Args:
            model_id: Catalog model id.
            api_key: API key to store, or ``None`` to remove it.
        """
        data = self._read()
        models = dict(data["models"])
        raw_entry = models.get(model_id)
        if not isinstance(raw_entry, dict):
            return
        entry = dict(raw_entry)
        if api_key:
            entry["api_key"] = api_key
            entry["api_key_required"] = True
        else:
            entry.pop("api_key", None)
        models[model_id] = entry
        data["models"] = models
        self._write(data)

    def _read(self) -> dict[str, Any]:
        """Return catalog JSON, seeding an empty file when missing."""
        path = self._resolve_path()
        if not path.exists():
            self._write({"selected": "", "models": {}})
            return {"selected": "", "models": {}}
        data: dict[str, Any] = json.loads(path.read_text())
        data.setdefault("selected", "")
        data.setdefault("models", {})
        return data

    def _write(self, data: dict[str, Any]) -> None:
        """Persist catalog JSON atomically to disk."""
        data_dir = self._resolve_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "selected": str(data["selected"]).strip(),
            "models": data["models"],
        }
        self._atomic_write(json.dumps(payload, indent=2), data_dir)

    def _atomic_write(self, content: str, data_dir: Path) -> None:
        """Write ``content`` atomically via a temp file and ``os.replace``.

        Args:
            content: Serialized JSON payload to persist.
            data_dir: Directory that holds the target file (for the temp file).
        """
        path = self._resolve_path()
        fd, tmp_name = tempfile.mkstemp(
            dir=str(data_dir),
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(content)
            os.replace(tmp_name, path)
        except BaseException:
            with suppress(FileNotFoundError):
                os.unlink(tmp_name)
            raise


def _model_dict(
    *,
    display_name: str,
    model_name: str,
    base_url: str,
    api_key_required: bool,
    api_key: str | None = None,
    provider_type: str = "openai-compatible",
    accepts_audio_input: bool = False,
) -> dict[str, Any]:
    """Build a catalog entry dictionary for persistence."""
    entry: dict[str, Any] = {
        "display_name": display_name,
        "provider_type": provider_type,
        "model": model_name,
        "base_url": base_url,
        "api_key_required": api_key_required,
        "accepts_audio_input": accepts_audio_input,
    }
    if api_key:
        entry["api_key"] = api_key
    return entry


def _parse_models(raw: dict[str, Any]) -> dict[str, LLMModelEntry]:
    """Parse a models mapping from catalog JSON."""
    parsed: dict[str, LLMModelEntry] = {}
    for model_id, item in raw.items():
        if isinstance(item, dict):
            parsed[model_id] = _parse_model(model_id, item)
    return parsed


def _parse_model(model_id: str, item: dict[str, Any]) -> LLMModelEntry:
    """Parse one catalog model entry."""
    base_url = str(item.get("base_url", "")).strip().rstrip("/")
    raw_api_key = item.get("api_key")
    api_key = str(raw_api_key).strip() if raw_api_key else None
    return LLMModelEntry(
        id=model_id,
        display_name=str(item.get("display_name", model_id)),
        provider_type=str(item.get("provider_type", "openai-compatible")),
        model=str(item.get("model", "")),
        base_url=base_url,
        api_key_required=bool(item.get("api_key_required", False)),
        api_key=api_key,
        accepts_audio_input=bool(item.get("accepts_audio_input", False)),
    )
