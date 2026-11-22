# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Use case for adding a user-defined LLM model to the catalog."""

from dataclasses import dataclass

from app.platform.domain.config import ConfigService
from app.platform.domain.effective_config import EffectiveModelConfig
from app.platform.domain.llm_catalog import LLMCatalogService
from app.platform.schemas import NewLLMModel


@dataclass(frozen=True)
class AddLLMModelResult:
    """Outcome of adding a model to the catalog.

    Attributes:
        error: Optional validation or connection error message.
        message: Optional success message.
        selected_preset_id: Catalog id to preselect on the config page.
    """

    error: str | None = None
    message: str | None = None
    selected_preset_id: str | None = None


class AddLLMModelUseCase:
    """Probe a user-defined model and append it to the catalog.

    The full add flow lives here instead of the HTTP handler: build the
    probe config from the submitted form, verify the provider connection,
    and only persist the entry when the probe succeeds.
    """

    def __init__(
        self,
        config_service: ConfigService,
        llm_catalog_service: LLMCatalogService,
    ) -> None:
        self._config_service: ConfigService = config_service
        self._catalog_service: LLMCatalogService = llm_catalog_service

    async def execute(
        self,
        payload: NewLLMModel,
    ) -> AddLLMModelResult:
        """Run the add-model flow.

        Args:
            payload: Validated add-model form values from the catalog form.

        Returns:
            Result with an error or success message for the config page.
        """
        config = self._config_service.get_config()
        try:
            probe = EffectiveModelConfig(
                provider_type="openai-compatible",
                base_url=payload.base_url,
                model=payload.model,
                api_key=payload.api_key,
                timeout=config.timeout if config is not None else 60.0,
                accepts_audio_input=payload.accepts_audio_input,
            )
            success, test_message = await self._config_service.test_model(probe)
            if not success:
                if not payload.api_key:
                    test_message = (
                        f"{test_message}. This provider may require an API key — "
                        "add one and retry."
                    )
                raise ValueError(test_message)
            entry = self._catalog_service.add_user_model(payload)
            return AddLLMModelResult(
                message=f"Added model '{entry.display_name}' to the catalog.",
                selected_preset_id=entry.id,
            )
        except ValueError as exc:
            return AddLLMModelResult(error=str(exc))
