# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""LLM model catalog types."""

from collections.abc import Collection
from dataclasses import dataclass, field
import re
from typing import Final
from urllib.parse import urlparse

CUSTOM_PRESET_ID: Final[str] = "custom"
_FALLBACK_MODEL_ID: Final[str] = "model"


@dataclass(frozen=True)
class LLMProvider:
    """One OpenAI-compatible provider in the catalog.

    Providers own the connection details (base URL and API key); models only
    reference the provider and carry the model name and UI flags.

    Attributes:
        id: Stable provider identifier stored in ``data/llm_models.json``.
        display_name: Human-readable label for the configuration UI.
        base_url: OpenAI-compatible API base URL.
        provider_type: Provider adapter id (always ``openai-compatible`` today).
        api_key: Stored API key for the provider (optional).
    """

    id: str
    display_name: str
    base_url: str
    provider_type: str = "openai-compatible"
    api_key: str | None = None


@dataclass(frozen=True)
class LLMModelEntry:
    """One OpenAI-compatible interview model from the catalog.

    Attributes:
        id: Stable model identifier stored in ``data/llm_models.json``.
        display_name: Human-readable label for the configuration UI.
        provider_type: Provider adapter id (always ``openai-compatible`` today).
        model: Model name passed to the provider API.
        base_url: OpenAI-compatible API base URL.
        api_key: Stored API key for catalog entries (optional).
        accepts_audio_input: Whether the model supports multimodal audio answers.
        provider_id: Catalog provider that owns this model, if any.
    """

    id: str
    display_name: str
    provider_type: str
    model: str
    base_url: str
    api_key: str | None = None
    accepts_audio_input: bool = False
    provider_id: str = ""


@dataclass(frozen=True)
class LLMCatalog:
    """User-defined model catalog loaded from ``data/llm_models.json``.

    Attributes:
        selected_id: Active interview model id, if any.
        models: All models keyed by id, with provider fields resolved.
        providers: All providers keyed by id.
    """

    selected_id: str | None
    models: dict[str, LLMModelEntry]
    providers: dict[str, LLMProvider] = field(default_factory=dict)


def normalize_model_id(model_id: str, catalog: LLMCatalog) -> str:
    """Return a supported catalog model id.

    Args:
        model_id: Raw model id from storage or form input.
        catalog: Loaded model catalog.

    Returns:
        Normalized model id.

    Raises:
        ValueError: If ``model_id`` is empty/invalid or unknown.
    """
    value = model_id.strip()
    if not value or value == CUSTOM_PRESET_ID:
        raise ValueError("Interview model is required")
    if value not in catalog.models:
        raise ValueError(f"Unsupported LLM model: {value}")
    return value


def slugify_model_id(text: str) -> str:
    """Convert arbitrary text into a catalog-safe id slug.

    Lowercases the text and replaces every run of non-alphanumeric characters
    with a single hyphen, trimming hyphens from both ends.

    Args:
        text: Source text, typically a model display name.

    Returns:
        A slug using lowercase letters, digits, and hyphens, or an empty
        string when no usable characters remain.
    """
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def generate_model_id(display_name: str, existing_ids: Collection[str]) -> str:
    """Derive a unique catalog id from a model display name.

    Args:
        display_name: Human-readable model name from the add-model form.
        existing_ids: Catalog ids already in use.

    Returns:
        A unique slug; falls back to ``model`` when the name has no usable
        characters and appends a numeric suffix to avoid collisions.
    """
    base = slugify_model_id(display_name) or _FALLBACK_MODEL_ID
    if base == CUSTOM_PRESET_ID:
        base = f"{CUSTOM_PRESET_ID}-{_FALLBACK_MODEL_ID}"
    candidate = base
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def provider_display_name_from_url(base_url: str) -> str:
    """Derive a human-readable provider label from its base URL.

    Args:
        base_url: OpenAI-compatible base URL.

    Returns:
        The URL host (e.g. ``api.openai.com``), or the raw URL when it has no
        host component.
    """
    return urlparse(base_url).netloc or base_url.strip() or "Provider"


def generate_provider_id(base_url: str, existing_ids: Collection[str]) -> str:
    """Derive a unique catalog provider id from a base URL host.

    Args:
        base_url: OpenAI-compatible base URL.
        existing_ids: Provider ids already in use.

    Returns:
        A unique slug (e.g. ``api-openai-com``), with a numeric suffix on
        collisions.
    """
    host = urlparse(base_url).netloc or base_url
    base = slugify_model_id(host) or "provider"
    candidate = base
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate
