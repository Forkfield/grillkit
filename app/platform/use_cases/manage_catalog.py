# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Use case for managing catalog providers and their models.

Provider and model mutations share one flow: probe the endpoint (so a bad URL,
key, or model name is reported before anything is persisted), then write the
catalog. Deleting never probes. Model discovery imports every reported model
without probing (flags only), and a failed attempt marks the provider card.
"""

from dataclasses import dataclass, field

from app.ai.llm_models import LLMProvider
from app.platform.domain.config import ConfigService
from app.platform.domain.effective_config import EffectiveModelConfig
from app.platform.domain.llm_catalog import LLMCatalogService
from app.platform.schemas import LLMModelForm, LLMProviderForm


@dataclass(frozen=True)
class CatalogActionResult:
    """Outcome of a provider or model mutation.

    Attributes:
        error: Optional validation or connection error message.
        message: Optional success message.
    """

    error: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class DiscoverModelsResult:
    """Outcome of listing the models a provider reports.

    Attributes:
        models: Model ids returned by the endpoint.
        error: Optional error message when discovery failed.
    """

    models: list[str] = field(default_factory=list)
    error: str | None = None


class ManageCatalogUseCase:
    """Create, update, and delete providers and their models."""

    def __init__(
        self,
        config_service: ConfigService,
        llm_catalog_service: LLMCatalogService,
    ) -> None:
        self._config_service: ConfigService = config_service
        self._catalog_service: LLMCatalogService = llm_catalog_service

    async def create_provider(self, form: LLMProviderForm) -> CatalogActionResult:
        """Probe and persist a new provider.

        Args:
            form: Submitted provider fields.

        Returns:
            Success or error result for the config page.
        """
        success, message = await self._config_service.test_connection(
            base_url=form.base_url,
            api_key=form.api_key,
            provider_type=form.provider_type,
            timeout=self._timeout(),
        )
        if not success:
            return CatalogActionResult(error=self._probe_error(message, form.api_key))
        try:
            provider = self._catalog_service.create_provider(
                display_name=form.display_name,
                base_url=form.base_url,
                provider_type=form.provider_type,
                api_key=form.api_key,
            )
        except ValueError as exc:
            return CatalogActionResult(error=str(exc))
        imported, discovery_error = await self._import_discovered_models(provider)
        if discovery_error:
            return CatalogActionResult(
                message=(
                    f"Added provider '{provider.display_name}'. "
                    f"Could not load models: {discovery_error}"
                )
            )
        if imported:
            return CatalogActionResult(
                message=(
                    f"Added provider '{provider.display_name}' — "
                    f"imported {imported} "
                    f"model{'' if imported == 1 else 's'}."
                )
            )
        return CatalogActionResult(message=f"Added provider '{provider.display_name}'.")

    async def update_provider(
        self, provider_id: str, form: LLMProviderForm
    ) -> CatalogActionResult:
        """Probe changed connection details and persist a provider update.

        Args:
            provider_id: Provider to update.
            form: Submitted provider fields.

        Returns:
            Success or error result for the config page.
        """
        existing = self._catalog_service.get_provider(provider_id)
        if existing is None:
            return CatalogActionResult(error=f"Unknown LLM provider: {provider_id}")
        effective_key = self._effective_key(form, existing)
        if self._connection_changed(existing, form, effective_key):
            success, message = await self._config_service.test_connection(
                base_url=form.base_url,
                api_key=effective_key,
                provider_type=form.provider_type,
                timeout=self._timeout(),
            )
            if not success:
                return CatalogActionResult(
                    error=self._probe_error(message, effective_key)
                )
        try:
            provider = self._catalog_service.update_provider(
                provider_id,
                display_name=form.display_name,
                base_url=form.base_url,
                provider_type=form.provider_type,
                api_key=form.api_key,
                clear_api_key=form.clear_api_key,
            )
        except ValueError as exc:
            return CatalogActionResult(error=str(exc))
        return CatalogActionResult(message=f"Saved provider '{provider.display_name}'.")

    def delete_provider(self, provider_id: str) -> CatalogActionResult:
        """Remove a provider and its models.

        Args:
            provider_id: Provider to remove.

        Returns:
            Success or error result for the config page.
        """
        try:
            self._catalog_service.delete_provider(provider_id)
        except ValueError as exc:
            return CatalogActionResult(error=str(exc))
        return CatalogActionResult(message="Provider removed.")

    async def add_model(
        self, provider_id: str, form: LLMModelForm
    ) -> CatalogActionResult:
        """Probe and persist a model under a provider.

        Args:
            provider_id: Provider that owns the model.
            form: Submitted model fields.

        Returns:
            Success or error result for the config page.
        """
        provider = self._catalog_service.get_provider(provider_id)
        if provider is None:
            return CatalogActionResult(error=f"Unknown LLM provider: {provider_id}")
        success, message = await self._probe_model(provider, form)
        if not success:
            return CatalogActionResult(
                error=self._probe_error(message, provider.api_key)
            )
        try:
            entry = self._catalog_service.add_model(
                provider_id,
                display_name=form.display_name,
                model=form.model,
                accepts_audio_input=form.accepts_audio_input,
            )
        except ValueError as exc:
            return CatalogActionResult(error=str(exc))
        # A successful manual add proves the endpoint works; drop any stale
        # discovery-failure mark from the provider card.
        self._catalog_service.set_provider_discovery_error(provider_id, None)
        return CatalogActionResult(message=f"Added model '{entry.display_name}'.")

    async def update_model(
        self, provider_id: str, model_id: str, form: LLMModelForm
    ) -> CatalogActionResult:
        """Probe and persist a model update.

        Args:
            provider_id: Provider that owns the model.
            model_id: Catalog model id.
            form: Submitted model fields.

        Returns:
            Success or error result for the config page.
        """
        provider = self._catalog_service.get_provider(provider_id)
        if provider is None:
            return CatalogActionResult(error=f"Unknown LLM provider: {provider_id}")
        success, message = await self._probe_model(provider, form)
        if not success:
            return CatalogActionResult(
                error=self._probe_error(message, provider.api_key)
            )
        try:
            entry = self._catalog_service.update_model(
                provider_id,
                model_id,
                display_name=form.display_name,
                model=form.model,
                accepts_audio_input=form.accepts_audio_input,
            )
        except ValueError as exc:
            return CatalogActionResult(error=str(exc))
        return CatalogActionResult(message=f"Saved model '{entry.display_name}'.")

    def delete_model(self, provider_id: str, model_id: str) -> CatalogActionResult:
        """Remove a model that belongs to a provider.

        Args:
            provider_id: Provider that should own the model.
            model_id: Catalog model id.

        Returns:
            Success or error result for the config page.
        """
        entry = self._catalog_service.get_model(model_id)
        if entry is None or entry.provider_id != provider_id:
            return CatalogActionResult(error=f"Unknown LLM model: {model_id}")
        try:
            self._catalog_service.delete_model(model_id)
        except ValueError as exc:
            return CatalogActionResult(error=str(exc))
        return CatalogActionResult(message="Model removed.")

    async def discover_models(self, provider_id: str) -> DiscoverModelsResult:
        """List the models stored provider credentials can access.

        Args:
            provider_id: Provider whose endpoint to query.

        Returns:
            Discovered model ids, or an error message.
        """
        provider = self._catalog_service.get_provider(provider_id)
        if provider is None:
            return DiscoverModelsResult(error=f"Unknown LLM provider: {provider_id}")
        models, error = await self._config_service.discover_models(
            base_url=provider.base_url,
            api_key=provider.api_key,
            provider_type=provider.provider_type,
            timeout=self._timeout(),
        )
        if error:
            return DiscoverModelsResult(
                error=self._probe_error(error, provider.api_key)
            )
        return DiscoverModelsResult(models=models)

    async def import_models(self, provider_id: str) -> CatalogActionResult:
        """Discover models from the provider endpoint and add them all.

        Already-known models are skipped; imported ones default to
        ``accepts_audio_input=False`` and keep the provider model name as the
        display name. A failed attempt marks the provider card so the user
        sees why the list stayed empty.

        Args:
            provider_id: Provider to import models for.

        Returns:
            Success or error result for the config page.
        """
        provider = self._catalog_service.get_provider(provider_id)
        if provider is None:
            return CatalogActionResult(error=f"Unknown LLM provider: {provider_id}")
        imported, error = await self._import_discovered_models(provider)
        if error:
            return CatalogActionResult(error=error)
        if imported:
            return CatalogActionResult(
                message=(
                    f"Imported {imported} "
                    f"model{'' if imported == 1 else 's'} from "
                    f"'{provider.display_name}'."
                )
            )
        return CatalogActionResult(
            message=(
                f"All models of '{provider.display_name}' are already in the catalog."
            )
        )

    def set_model_audio_input(
        self, provider_id: str, model_id: str, accepts_audio_input: bool
    ) -> CatalogActionResult:
        """Toggle the audio-input flag of one model without probing.

        The flag only records UI capability, so it is persisted directly
        instead of running a live connection probe.

        Args:
            provider_id: Provider that owns the model.
            model_id: Catalog model id.
            accepts_audio_input: New flag value.

        Returns:
            Success or error result for the config page.
        """
        entry = self._catalog_service.get_model(model_id)
        if entry is None or entry.provider_id != provider_id:
            return CatalogActionResult(error=f"Unknown LLM model: {model_id}")
        try:
            self._catalog_service.update_model(
                provider_id,
                model_id,
                display_name=entry.display_name,
                model=entry.model,
                accepts_audio_input=accepts_audio_input,
            )
        except ValueError as exc:
            return CatalogActionResult(error=str(exc))
        return CatalogActionResult(
            message=(
                f"'{entry.display_name}' now "
                f"{'accepts' if accepts_audio_input else 'no longer accepts'} audio input."
            )
        )

    async def _import_discovered_models(
        self, provider: LLMProvider
    ) -> tuple[int, str | None]:
        """Discover models for ``provider`` and import them into the catalog.

        Returns:
            Tuple of the number of added models and an error message when
            discovery failed (the provider is then marked with it).
        """
        models, error = await self._config_service.discover_models(
            base_url=provider.base_url,
            api_key=provider.api_key,
            provider_type=provider.provider_type,
            timeout=self._timeout(),
        )
        if error:
            message = self._probe_error(error, provider.api_key)
            self._catalog_service.set_provider_discovery_error(provider.id, message)
            return 0, message
        try:
            imported = self._catalog_service.import_provider_models(provider.id, models)
        except ValueError as exc:
            return 0, str(exc)
        self._catalog_service.set_provider_discovery_error(provider.id, None)
        return imported, None

    async def _probe_model(
        self, provider: LLMProvider, form: LLMModelForm
    ) -> tuple[bool, str]:
        """Probe one model using the provider's stored connection details."""
        probe = EffectiveModelConfig(
            provider_type=provider.provider_type,
            base_url=provider.base_url,
            model=form.model,
            api_key=provider.api_key,
            timeout=self._timeout(),
            accepts_audio_input=form.accepts_audio_input,
        )
        return await self._config_service.test_model(probe)

    def _timeout(self) -> float:
        """Return the configured request timeout, defaulting to 60 seconds."""
        config = self._config_service.get_config()
        return config.timeout if config is not None else 60.0

    @staticmethod
    def _effective_key(form: LLMProviderForm, provider: LLMProvider) -> str | None:
        """Return the key an update would store."""
        if form.clear_api_key:
            return None
        return form.api_key or provider.api_key

    @staticmethod
    def _connection_changed(
        provider: LLMProvider, form: LLMProviderForm, effective_key: str | None
    ) -> bool:
        """Whether an update changes the connection details."""
        return (
            provider.base_url != form.base_url
            or provider.provider_type != form.provider_type
            or provider.api_key != effective_key
        )

    @staticmethod
    def _probe_error(message: str, api_key: str | None) -> str:
        """Add a key hint to a probe failure when no key was supplied."""
        if api_key:
            return message
        return f"{message}. This provider may require an API key — add one and retry."
