# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""LLM catalog repository: read/write ``data/llm_models.json``.

The repository owns all filesystem access to the interview model catalog. It
maps the file directly to an :class:`LLMCatalog` domain object and back, and
guarantees atomic writes so a partial write never leaves a corrupt JSON file
behind. The canonical path is resolved lazily on each call, so tests can
override it via monkeypatch.

Providers own the connection details (base URL and API key) and models
reference them by id. Legacy flat catalogs — one entry per model, each with its
own ``base_url``/``api_key`` — are migrated in memory on read and rewritten in
the provider shape on the next mutation.
"""

from __future__ import annotations

from contextlib import suppress
import json
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Any

from app.ai.llm_models import (
    LLMCatalog,
    LLMModelEntry,
    LLMProvider,
    generate_model_id,
    generate_provider_id,
    provider_display_name_from_url,
)
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
            Catalog with the selected id, providers, and resolved models.
        """
        return _parse_catalog(self._read())

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

        The provider is reused when the base URL already exists, otherwise a
        provider is created from the submitted base URL. The model id is
        derived from the display name and made unique against existing entries.

        Args:
            payload: Validated add-model form values.

        Returns:
            Persisted catalog entry with provider fields resolved.
        """
        data = self._read()
        models = dict(data["models"])
        providers = dict(data["providers"])
        provider_id = _find_or_create_provider(
            providers,
            base_url=payload.base_url,
            api_key=payload.api_key,
        )
        model_id = generate_model_id(payload.display_name, models)
        models[model_id] = {
            "provider_id": provider_id,
            "display_name": payload.display_name,
            "model": payload.model,
            "accepts_audio_input": payload.accepts_audio_input,
        }
        data["models"] = models
        data["providers"] = providers
        data["selected"] = model_id
        self._write(data)
        return _parse_catalog(data).models[model_id]

    def update_model_api_key(self, model_id: str, api_key: str | None) -> None:
        """Persist an API key on the provider that owns a model.

        The key belongs to the provider, so every model of that provider sees
        the update.

        Args:
            model_id: Catalog model id.
            api_key: API key to store, or ``None`` to remove it.
        """
        data = self._read()
        raw_model = data["models"].get(model_id)
        if not isinstance(raw_model, dict):
            return
        provider_id = str(raw_model.get("provider_id", ""))
        providers = dict(data["providers"])
        raw_provider = providers.get(provider_id)
        if not isinstance(raw_provider, dict):
            return
        provider = dict(raw_provider)
        key = _optional_str(api_key)
        if key:
            provider["api_key"] = key
        else:
            provider.pop("api_key", None)
        providers[provider_id] = provider
        data["providers"] = providers
        self._write(data)

    def create_provider(
        self,
        *,
        display_name: str,
        base_url: str,
        provider_type: str,
        api_key: str | None,
    ) -> LLMProvider:
        """Append a provider to the catalog.

        Args:
            display_name: Human-readable provider label.
            base_url: OpenAI-compatible base URL.
            provider_type: Provider adapter id.
            api_key: Optional API key stored on the provider.

        Returns:
            Persisted provider.

        Raises:
            ValueError: If a provider with the same base URL already exists.
        """
        data = self._read()
        providers = dict(data["providers"])
        normalized = _normalize_base_url(base_url)
        for raw in providers.values():
            if isinstance(raw, dict) and (
                _normalize_base_url(raw.get("base_url", "")) == normalized
            ):
                raise ValueError("A provider with this base URL already exists.")
        provider_id = generate_provider_id(base_url, providers)
        provider: dict[str, Any] = {
            "display_name": display_name,
            "base_url": normalized,
            "provider_type": provider_type,
        }
        key = _optional_str(api_key)
        if key:
            provider["api_key"] = key
        providers[provider_id] = provider
        data["providers"] = providers
        self._write(data)
        return _parse_provider(provider_id, provider)

    def update_provider(
        self,
        provider_id: str,
        *,
        display_name: str,
        base_url: str,
        provider_type: str,
        api_key: str | None,
        clear_api_key: bool,
    ) -> LLMProvider:
        """Update a provider's connection details.

        An empty ``api_key`` keeps the stored key; ``clear_api_key`` removes it.

        Args:
            provider_id: Provider to update.
            display_name: New human-readable label.
            base_url: New base URL.
            provider_type: New provider adapter id.
            api_key: Replacement key, or ``None``/empty to keep the stored one.
            clear_api_key: Whether to remove the stored key.

        Returns:
            Updated provider.

        Raises:
            ValueError: If the provider id is unknown.
        """
        data = self._read()
        providers = dict(data["providers"])
        raw = providers.get(provider_id)
        if not isinstance(raw, dict):
            raise ValueError(f"Unknown LLM provider: {provider_id}")
        updated = dict(raw)
        updated["display_name"] = display_name
        updated["base_url"] = _normalize_base_url(base_url)
        updated["provider_type"] = provider_type
        if clear_api_key:
            updated.pop("api_key", None)
        else:
            key = _optional_str(api_key)
            if key:
                updated["api_key"] = key
        providers[provider_id] = updated
        data["providers"] = providers
        self._write(data)
        return _parse_provider(provider_id, updated)

    def delete_provider(self, provider_id: str) -> str | None:
        """Remove a provider together with all of its models.

        Args:
            provider_id: Provider to remove.

        Returns:
            The new selected model id (``None`` when the selection was removed).

        Raises:
            ValueError: If the provider id is unknown.
        """
        data = self._read()
        providers = dict(data["providers"])
        if provider_id not in providers:
            raise ValueError(f"Unknown LLM provider: {provider_id}")
        models = dict(data["models"])
        removed = [
            model_id
            for model_id, raw in models.items()
            if isinstance(raw, dict) and raw.get("provider_id") == provider_id
        ]
        del providers[provider_id]
        for model_id in removed:
            del models[model_id]
        selected = str(data.get("selected", ""))
        if selected in removed:
            selected = ""
        data["providers"] = providers
        data["models"] = models
        data["selected"] = selected
        self._write(data)
        return selected or None

    def add_model(
        self,
        provider_id: str,
        *,
        display_name: str,
        model: str,
        accepts_audio_input: bool,
    ) -> LLMModelEntry:
        """Append a model under an existing provider and select it.

        Args:
            provider_id: Provider that owns the model.
            display_name: Human-readable model label.
            model: Provider model name.
            accepts_audio_input: Whether the model supports audio answers.

        Returns:
            Persisted catalog entry with provider fields resolved.

        Raises:
            ValueError: If the provider id is unknown.
        """
        data = self._read()
        if provider_id not in data["providers"]:
            raise ValueError(f"Unknown LLM provider: {provider_id}")
        models = dict(data["models"])
        model_id = generate_model_id(display_name, models)
        models[model_id] = {
            "provider_id": provider_id,
            "display_name": display_name,
            "model": model,
            "accepts_audio_input": accepts_audio_input,
        }
        data["models"] = models
        data["selected"] = model_id
        self._write(data)
        return _parse_catalog(data).models[model_id]

    def update_model(
        self,
        provider_id: str,
        model_id: str,
        *,
        display_name: str,
        model: str,
        accepts_audio_input: bool,
    ) -> LLMModelEntry:
        """Update a model that belongs to a provider.

        Args:
            provider_id: Provider that should own the model.
            model_id: Catalog model id to update.
            display_name: New human-readable label.
            model: New provider model name.
            accepts_audio_input: New audio-input capability flag.

        Returns:
            Updated catalog entry with provider fields resolved.

        Raises:
            ValueError: If the model is unknown or belongs to another provider.
        """
        data = self._read()
        models = dict(data["models"])
        raw = models.get(model_id)
        if not isinstance(raw, dict) or raw.get("provider_id") != provider_id:
            raise ValueError(f"Unknown LLM model: {model_id}")
        models[model_id] = {
            **raw,
            "display_name": display_name,
            "model": model,
            "accepts_audio_input": accepts_audio_input,
        }
        data["models"] = models
        self._write(data)
        return _parse_catalog(data).models[model_id]

    def import_provider_models(self, provider_id: str, models: list[str]) -> int:
        """Bulk-add discovered model names under a provider.

        Models already in the catalog (matched by provider model name) are
        skipped; imported ones default to ``accepts_audio_input=False`` and a
        display name equal to the model name. The selection never changes.

        Args:
            provider_id: Provider that owns the imported models.
            models: Model names reported by the provider endpoint.

        Returns:
            Number of models actually added.

        Raises:
            ValueError: If the provider id is unknown.
        """
        data = self._read()
        if provider_id not in data["providers"]:
            raise ValueError(f"Unknown LLM provider: {provider_id}")
        models_dict = dict(data["models"])
        known = {
            str(raw.get("model", ""))
            for raw in models_dict.values()
            if isinstance(raw, dict) and raw.get("provider_id") == provider_id
        }
        added = 0
        for name in models:
            model_name = str(name or "").strip()
            if not model_name or model_name in known:
                continue
            model_id = generate_model_id(model_name, models_dict)
            models_dict[model_id] = {
                "provider_id": provider_id,
                "display_name": model_name,
                "model": model_name,
                "accepts_audio_input": False,
            }
            known.add(model_name)
            added += 1
        if added:
            data["models"] = models_dict
            self._write(data)
        return added

    def set_provider_discovery_error(self, provider_id: str, error: str | None) -> None:
        """Persist the last model-discovery outcome on a provider.

        Args:
            provider_id: Provider to mark.
            error: Error message from the failed attempt, or ``None`` to clear.

        Raises:
            ValueError: If the provider id is unknown.
        """
        data = self._read()
        providers = dict(data["providers"])
        raw = providers.get(provider_id)
        if not isinstance(raw, dict):
            raise ValueError(f"Unknown LLM provider: {provider_id}")
        updated = dict(raw)
        if error:
            updated["discovery_error"] = str(error)
        else:
            updated.pop("discovery_error", None)
        providers[provider_id] = updated
        data["providers"] = providers
        self._write(data)
        return None

    def delete_model(self, model_id: str) -> str | None:
        """Remove a model from the catalog.

        Args:
            model_id: Catalog model id to remove.

        Returns:
            The new selected model id (``None`` when the selection was removed).

        Raises:
            ValueError: If the model id is unknown.
        """
        data = self._read()
        models = dict(data["models"])
        if model_id not in models:
            raise ValueError(f"Unknown LLM model: {model_id}")
        del models[model_id]
        selected = str(data.get("selected", ""))
        if selected == model_id:
            selected = ""
        data["models"] = models
        data["selected"] = selected
        self._write(data)
        return selected or None

    def _read(self) -> dict[str, Any]:
        """Return catalog JSON, seeding an empty file when missing.

        Legacy flat files are migrated in memory; the new shape is written on
        the next mutation.
        """
        path = self._resolve_path()
        if not path.exists():
            empty: dict[str, Any] = {"selected": "", "providers": {}, "models": {}}
            self._write(empty)
            return empty
        data: dict[str, Any] = json.loads(path.read_text())
        return _normalize_catalog(data)

    def _write(self, data: dict[str, Any]) -> None:
        """Persist catalog JSON atomically to disk."""
        data_dir = self._resolve_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "selected": str(data["selected"]).strip(),
            "providers": data.get("providers") or {},
            "models": data.get("models") or {},
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


def _find_or_create_provider(
    providers: dict[str, Any],
    *,
    base_url: str,
    api_key: str | None,
) -> str:
    """Return the provider id for ``base_url``, creating it when needed.

    A submitted API key updates the matched provider so the key stays shared
    across all of its models.
    """
    normalized = _normalize_base_url(base_url)
    for provider_id, raw in providers.items():
        if not isinstance(raw, dict):
            continue
        if _normalize_base_url(raw.get("base_url", "")) != normalized:
            continue
        key = _optional_str(api_key)
        if key:
            updated = dict(raw)
            updated["api_key"] = key
            providers[provider_id] = updated
        return provider_id

    provider_id = generate_provider_id(base_url, providers)
    provider: dict[str, Any] = {
        "display_name": provider_display_name_from_url(base_url),
        "base_url": normalized,
        "provider_type": "openai-compatible",
    }
    key = _optional_str(api_key)
    if key:
        provider["api_key"] = key
    providers[provider_id] = provider
    return provider_id


def _normalize_catalog(data: dict[str, Any]) -> dict[str, Any]:
    """Return catalog data in the provider shape, migrating legacy files.

    The provider shape is detected by ``models`` referencing a ``provider_id``;
    legacy files carry connection details on every model instead and are
    grouped into providers on read.
    """
    providers = data.get("providers")
    models = data.get("models")
    if not isinstance(models, dict):
        models = {}
    is_provider_shape = isinstance(providers, dict) and all(
        not isinstance(item, dict) or item.get("provider_id")
        for item in models.values()
    )
    if not is_provider_shape:
        return _migrate_flat_catalog(data)
    return {
        "selected": data.get("selected", ""),
        "providers": providers,
        "models": models,
    }


def _migrate_flat_catalog(data: dict[str, Any]) -> dict[str, Any]:
    """Group legacy per-model entries under providers keyed by base URL."""
    raw_models = data.get("models")
    if not isinstance(raw_models, dict):
        raw_models = {}

    providers: dict[str, dict[str, Any]] = {}
    by_target: dict[tuple[str, str], str] = {}
    models: dict[str, dict[str, Any]] = {}

    for model_id, raw in raw_models.items():
        if not isinstance(raw, dict):
            continue
        base_url = _normalize_base_url(raw.get("base_url", ""))
        provider_type = str(raw.get("provider_type", "openai-compatible"))
        target = (base_url, provider_type)
        provider_id = by_target.get(target)
        if provider_id is None:
            provider_id = generate_provider_id(base_url, providers)
            by_target[target] = provider_id
            providers[provider_id] = {
                "display_name": provider_display_name_from_url(base_url),
                "base_url": base_url,
                "provider_type": provider_type,
            }
        _merge_provider_key(providers[provider_id], raw.get("api_key"))
        models[model_id] = {
            "provider_id": provider_id,
            "display_name": str(raw.get("display_name", model_id)),
            "model": str(raw.get("model", "")),
            "accepts_audio_input": bool(raw.get("accepts_audio_input", False)),
        }

    return {
        "selected": data.get("selected", ""),
        "providers": providers,
        "models": models,
    }


def _merge_provider_key(provider: dict[str, Any], raw_key: object) -> None:
    """Store the first non-empty legacy API key on the grouped provider."""
    if provider.get("api_key"):
        return
    key = _optional_str(raw_key)
    if key:
        provider["api_key"] = key


def _parse_catalog(data: dict[str, Any]) -> LLMCatalog:
    """Parse normalized catalog data into the domain object."""
    providers = {
        provider_id: _parse_provider(provider_id, item)
        for provider_id, item in data["providers"].items()
        if isinstance(item, dict)
    }
    models: dict[str, LLMModelEntry] = {}
    for model_id, item in data["models"].items():
        if not isinstance(item, dict):
            continue
        provider = providers.get(str(item.get("provider_id", "")))
        if provider is None:
            continue
        models[model_id] = LLMModelEntry(
            id=model_id,
            display_name=str(item.get("display_name", model_id)),
            provider_type=provider.provider_type,
            model=str(item.get("model", "")),
            base_url=provider.base_url,
            api_key=provider.api_key,
            accepts_audio_input=bool(item.get("accepts_audio_input", False)),
            provider_id=provider.id,
        )
    return LLMCatalog(
        selected_id=str(data.get("selected", "")).strip() or None,
        models=models,
        providers=providers,
    )


def _parse_provider(provider_id: str, item: dict[str, Any]) -> LLMProvider:
    """Parse one provider entry."""
    return LLMProvider(
        id=provider_id,
        display_name=str(item.get("display_name", provider_id)),
        base_url=_normalize_base_url(item.get("base_url", "")),
        provider_type=str(item.get("provider_type", "openai-compatible")),
        api_key=_optional_str(item.get("api_key")),
        discovery_error=_optional_str(item.get("discovery_error")),
    )


def _normalize_base_url(value: object) -> str:
    """Normalize a base URL (strip whitespace and a trailing slash)."""
    return str(value or "").strip().rstrip("/")


def _optional_str(value: object) -> str | None:
    """Return a stripped string, or ``None`` when empty."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
