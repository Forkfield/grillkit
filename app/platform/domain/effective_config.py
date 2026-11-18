# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Effective LLM provider configuration aggregate.

The domain :class:`AppConfig` stores only shared application settings plus a
reference to the active catalog model. The concrete provider fields
(``provider_type``/``base_url``/``model``/``api_key``) live on the catalog
``LLMModelEntry`` and are resolved at the point of use into an
:class:`EffectiveModelConfig` aggregate that also carries the request timeout.

This aggregate is the single shape consumed by the AI provider factory and by
the config-page read model, so provider construction never re-unpacks a set of
loose primitives.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.llm_models import LLMModelEntry


@dataclass(frozen=True)
class EffectiveModelConfig:
    """Resolved provider settings ready for connection tests and the UI.

    Attributes:
        provider_type: AI provider adapter id (``openai-compatible`` today).
        base_url: API endpoint URL.
        model: Model name passed to the provider.
        api_key: API key for authentication (optional for local providers).
        timeout: Request timeout in seconds.
    """

    provider_type: str
    base_url: str
    model: str
    api_key: str | None = None
    timeout: float = 60.0
    accepts_audio_input: bool = False

    @classmethod
    def from_entry(cls, entry: LLMModelEntry, *, timeout: float) -> EffectiveModelConfig:
        """Build an effective config from a catalog entry and a timeout.

        Args:
            entry: Selected catalog model entry.
            timeout: Request timeout in seconds from ``AppConfig``.

        Returns:
            Aggregate combining provider fields, the request timeout, and the
            model's audio-input capability.
        """
        return cls(
            provider_type=entry.provider_type,
            base_url=entry.base_url,
            model=entry.model,
            api_key=entry.api_key,
            timeout=timeout,
            accepts_audio_input=entry.accepts_audio_input,
        )
