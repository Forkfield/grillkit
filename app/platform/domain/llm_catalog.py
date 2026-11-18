# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""LLM model catalog service and its repository port.

The service reads and updates the user interview model catalog by delegating
all filesystem access to a repository behind :class:`LLMCatalogRepositoryProtocol`,
so the domain never reads or writes ``data/llm_models.json`` directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.ai.llm_models import LLMCatalog, LLMModelEntry

if TYPE_CHECKING:
    from app.platform.schemas import NewLLMModel


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
        catalog = self.load_catalog()
        if catalog.selected_id and catalog.selected_id in catalog.models:
            return catalog.selected_id
        return next(iter(catalog.models), None)

    def get_selected_model(self) -> LLMModelEntry | None:
        """Return the active interview model entry, or ``None`` when unselected.

        Returns:
            The selected catalog entry when set and known, otherwise ``None``.
        """
        selected_id = self.get_selected_model_id()
        if selected_id is None:
            return None
        return self.load_catalog().models.get(selected_id)

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

    def save_model_selection(self, model_id: str, api_key: str | None) -> None:
        """Persist the active model and update the stored API key.

        Args:
            model_id: Catalog model id selected for interviews.
            api_key: API key to store, or ``None`` to clear the stored key.
        """
        self.set_selected_model(model_id)
        self.update_model_api_key(model_id, api_key)
