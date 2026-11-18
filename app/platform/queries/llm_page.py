# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""LLM catalog read models for the configuration page."""

from app.platform.repo.config_composition import get_default_catalog_service
from app.platform.schemas import LLMPresetOptionRead


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
            api_key_required=entry.api_key_required,
            accepts_audio_input=entry.accepts_audio_input,
        )
        for entry in get_default_catalog_service().list_models()
    ]

