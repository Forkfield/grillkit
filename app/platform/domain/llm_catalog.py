# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""LLM model catalog service and its repository port.

The service reads and updates the user interview model catalog by delegating
all filesystem access to a repository behind :class:`LLMCatalogRepositoryProtocol`,
so the domain never reads or writes ``data/llm_models.json`` directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.ai.llm_models import LLMCatalog, LLMModelEntry, LLMProvider

if TYPE_CHECKING:
    from app.platform.schemas import NewLLMModel


def selected_id_of(catalog: LLMCatalog) -> str | None:
    """Return the active model id from a loaded catalog.

    Falls back to the first catalog entry when ``selected`` is unset or points
    to a model that no longer exists.

    Args:
        catalog: Loaded model catalog.

    Returns:
        Active model id, or ``None`` when the catalog is empty.
    """
    if catalog.selected_id and catalog.selected_id in catalog.models:
        return catalog.selected_id
    return next(iter(catalog.models), None)


class LLMCatalogRepositoryProtocol(Protocol):
    """Port for reading and persisting the interview model catalog.

    The concrete implementation lives in the infrastructure layer and is
    injected into :class:`LLMCatalogService`, so the domain never depends on a
    specific filesystem repository.
    """

    def load(self) -> LLMCatalog: ...

    def set_selected(self, model_id: str) -> None: ...

    def add_user_model(self, payload: NewLLMModel) -> LLMModelEntry: ...

    def update_model_api_key(self, model_id: str, api_key: str | None) -> None: ...

    def create_provider(
        self,
        *,
        display_name: str,
        base_url: str,
        provider_type: str,
        api_key: str | None,
    ) -> LLMProvider: ...

    def update_provider(
        self,
        provider_id: str,
        *,
        display_name: str,
        base_url: str,
        provider_type: str,
        api_key: str | None,
        clear_api_key: bool,
    ) -> LLMProvider: ...

    def delete_provider(self, provider_id: str) -> str | None: ...

    def add_model(
        self,
        provider_id: str,
        *,
        display_name: str,
        model: str,
        accepts_audio_input: bool,
    ) -> LLMModelEntry: ...

    def update_model(
        self,
        provider_id: str,
        model_id: str,
        *,
        display_name: str,
        model: str,
        accepts_audio_input: bool,
    ) -> LLMModelEntry: ...

    def delete_model(self, model_id: str) -> str | None: ...


class LLMCatalogService:
    """Read and update the user LLM model catalog.

    The service depends only on :class:`LLMCatalogRepositoryProtocol` (a domain
    port); the concrete repository is injected by the composition root.
    """

    def __init__(self, repo: LLMCatalogRepositoryProtocol) -> None:
        """Initialize the service with its catalog repository.

        Args:
            repo: Catalog repository (port) used for ``llm_models.json`` I/O.
        """
        self._repo = repo

    def load_catalog(self) -> LLMCatalog:
        """Load models from ``data/llm_models.json``.

        Returns:
            Catalog with selected id and all saved models.
        """
        return self._repo.load()

    def get_selected_model_id(self) -> str | None:
        """Return the active interview model id from ``data/llm_models.json``.

        Returns:
            Selected model id or ``None`` when unset or unknown.
        """
        return selected_id_of(self.load_catalog())

    def get_selected_model(self) -> LLMModelEntry | None:
        """Return the active interview model entry, or ``None`` when unselected.

        Returns:
            The selected catalog entry when set and known, otherwise ``None``.
        """
        catalog = self.load_catalog()
        selected_id = selected_id_of(catalog)
        if selected_id is None:
            return None
        return catalog.models.get(selected_id)

    def set_selected_model(self, model_id: str) -> None:
        """Persist the active interview model id.

        Args:
            model_id: Catalog model id to mark as selected.

        Raises:
            ValueError: If the model id is unknown.
        """
        self._repo.set_selected(model_id)

    def get_model(self, model_id: str | None) -> LLMModelEntry | None:
        """Look up one catalog entry by id.

        Args:
            model_id: Catalog model id or ``None``.

        Returns:
            Matching entry, or ``None`` when unset or unknown.
        """
        if not model_id:
            return None
        return self.load_catalog().models.get(model_id)

    def list_models(self) -> list[LLMModelEntry]:
        """Return catalog models sorted by display name.

        Returns:
            Ordered list of model entries for UI selection.
        """
        catalog = self.load_catalog()
        return sorted(
            catalog.models.values(),
            key=lambda entry: (entry.display_name.lower(), entry.id),
        )

    def add_user_model(self, payload: NewLLMModel) -> LLMModelEntry:
        """Append a model to ``data/llm_models.json``.

        Args:
            payload: Validated add-model form values.

        Returns:
            Persisted catalog entry.
        """
        return self._repo.add_user_model(payload)

    def update_model_api_key(self, model_id: str, api_key: str | None) -> None:
        """Persist an API key for a catalog model.

        Args:
            model_id: Catalog model id.
            api_key: API key to store, or ``None`` to remove it.
        """
        self._repo.update_model_api_key(model_id, api_key)

    def get_provider(self, provider_id: str | None) -> LLMProvider | None:
        """Return one provider by id, or ``None`` when unknown.

        Args:
            provider_id: Catalog provider id.

        Returns:
            Matching provider, or ``None``.
        """
        if not provider_id:
            return None
        return self.load_catalog().providers.get(provider_id)

    def create_provider(
        self,
        *,
        display_name: str,
        base_url: str,
        provider_type: str = "openai-compatible",
        api_key: str | None = None,
    ) -> LLMProvider:
        """Persist a new provider.

        Args:
            display_name: Human-readable provider label.
            base_url: OpenAI-compatible base URL.
            provider_type: Provider adapter id.
            api_key: Optional API key stored on the provider.

        Returns:
            Persisted provider.
        """
        return self._repo.create_provider(
            display_name=display_name,
            base_url=base_url,
            provider_type=provider_type,
            api_key=api_key,
        )

    def update_provider(
        self,
        provider_id: str,
        *,
        display_name: str,
        base_url: str,
        provider_type: str = "openai-compatible",
        api_key: str | None = None,
        clear_api_key: bool = False,
    ) -> LLMProvider:
        """Update a provider's connection details.

        Args:
            provider_id: Provider to update.
            display_name: New human-readable label.
            base_url: New base URL.
            provider_type: New provider adapter id.
            api_key: Replacement key, or empty to keep the stored one.
            clear_api_key: Whether to remove the stored key.

        Returns:
            Updated provider.
        """
        return self._repo.update_provider(
            provider_id,
            display_name=display_name,
            base_url=base_url,
            provider_type=provider_type,
            api_key=api_key,
            clear_api_key=clear_api_key,
        )

    def delete_provider(self, provider_id: str) -> str | None:
        """Remove a provider and all of its models.

        Args:
            provider_id: Provider to remove.

        Returns:
            The new selected model id (``None`` when it was removed).
        """
        return self._repo.delete_provider(provider_id)

    def add_model(
        self,
        provider_id: str,
        *,
        display_name: str,
        model: str,
        accepts_audio_input: bool = False,
    ) -> LLMModelEntry:
        """Append a model under an existing provider.

        Args:
            provider_id: Provider that owns the model.
            display_name: Human-readable model label.
            model: Provider model name.
            accepts_audio_input: Whether the model supports audio answers.

        Returns:
            Persisted catalog entry.
        """
        return self._repo.add_model(
            provider_id,
            display_name=display_name,
            model=model,
            accepts_audio_input=accepts_audio_input,
        )

    def update_model(
        self,
        provider_id: str,
        model_id: str,
        *,
        display_name: str,
        model: str,
        accepts_audio_input: bool = False,
    ) -> LLMModelEntry:
        """Update a model owned by a provider.

        Args:
            provider_id: Provider that owns the model.
            model_id: Catalog model id to update.
            display_name: New human-readable label.
            model: New provider model name.
            accepts_audio_input: New audio-input capability flag.

        Returns:
            Updated catalog entry.
        """
        return self._repo.update_model(
            provider_id,
            model_id,
            display_name=display_name,
            model=model,
            accepts_audio_input=accepts_audio_input,
        )

    def delete_model(self, model_id: str) -> str | None:
        """Remove a model from the catalog.

        Args:
            model_id: Catalog model id to remove.

        Returns:
            The new selected model id (``None`` when it was removed).
        """
        return self._repo.delete_model(model_id)

    def save_model_selection(self, model_id: str, api_key: str | None) -> None:
        """Persist the active model and update the stored API key.

        Args:
            model_id: Catalog model id selected for interviews.
            api_key: API key to store, or ``None`` to clear the stored key.
        """
        self.set_selected_model(model_id)
        self.update_model_api_key(model_id, api_key)
