# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""LLM catalog read models for the configuration page."""

from app.platform.repo.config_composition import get_default_catalog_service
from app.platform.schemas import LLMModelRead, LLMPresetOptionRead, LLMProviderRead


def list_preset_options() -> list[LLMPresetOptionRead]:
    """Load catalog entries for the interview model selector.

    Returns:
        Preset read models for the config form.
    """
    return [
        LLMPresetOptionRead(
            id=entry.id,
            display_name=entry.display_name,
            description=entry.model,
            model=entry.model,
            base_url=entry.base_url,
            accepts_audio_input=entry.accepts_audio_input,
        )
        for entry in get_default_catalog_service().list_models()
    ]


def list_provider_options() -> list[LLMProviderRead]:
    """Load providers and their models for the providers settings tab.

    Returns:
        Provider read models sorted by label, each with its models sorted by
        label.
    """
    catalog = get_default_catalog_service().load_catalog()
    providers = getattr(catalog, "providers", {}) or {}
    models = getattr(catalog, "models", {}) or {}
    reads: list[LLMProviderRead] = []
    for provider_id, provider in providers.items():
        provider_models = sorted(
            (
                LLMModelRead(
                    id=entry.id,
                    provider_id=provider_id,
                    display_name=entry.display_name,
                    model=entry.model,
                    accepts_audio_input=entry.accepts_audio_input,
                )
                for entry in models.values()
                if entry.provider_id == provider_id
            ),
            key=lambda item: (item.display_name.lower(), item.id),
        )
        reads.append(
            LLMProviderRead(
                id=provider.id,
                display_name=provider.display_name,
                base_url=provider.base_url,
                provider_type=provider.provider_type,
                has_api_key=bool(provider.api_key),
                models=provider_models,
            )
        )
    return sorted(reads, key=lambda item: (item.display_name.lower(), item.id))
