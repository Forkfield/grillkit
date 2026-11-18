# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Composition root for the config service and its repository.

This module wires :class:`ConfigService` with its :class:`ConfigRepository`
in a single place (a lazy singleton) so the domain never constructs its own
filesystem repository, while deep application-layer call sites that have no
FastAPI dependency injection can still reach the shared runtime instance.

``ConfigService`` and ``ConfigRepository`` are stateless (they read from disk
on every call), so a shared runtime instance never goes stale and needs no
refresh mechanism.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.platform.domain.config import ConfigService
from app.platform.domain.llm_catalog import LLMCatalogService
from app.platform.repo.config_repository import ConfigRepository
from app.platform.repo.llm_catalog_repository import LLMCatalogRepository

_default_config_service: ConfigService | None = None
_default_catalog_service: LLMCatalogService | None = None


def get_config_repository() -> ConfigRepository:
    """Return a config repository instance (FastAPI dependency)."""
    return ConfigRepository()


ConfigRepositoryDep = Annotated[
    ConfigRepository,
    Depends(get_config_repository),
]


def get_config_service() -> ConfigService:
    """Return the shared config service instance (FastAPI dependency)."""
    return get_default_config_service()


ConfigServiceDep = Annotated[
    ConfigService,
    Depends(get_config_service),
]


def get_default_config_service() -> ConfigService:
    """Return the application-wide ``ConfigService`` singleton.

    Returns:
        The shared instance, creating it lazily on first access.
    """
    global _default_config_service
    if _default_config_service is None:
        _default_config_service = ConfigService(
            get_config_repository(), get_default_catalog_service()
        )
    return _default_config_service


def set_default_config_service(service: ConfigService | None) -> None:
    """Override the shared config service (used by tests).

    Args:
        service: Replacement instance, or ``None`` to reset to a fresh default.
    """
    global _default_config_service
    _default_config_service = service


def get_llm_catalog_repository() -> LLMCatalogRepository:
    """Return an LLM catalog repository instance (FastAPI dependency)."""
    return LLMCatalogRepository()


LLMCatalogRepositoryDep = Annotated[
    LLMCatalogRepository,
    Depends(get_llm_catalog_repository),
]


def get_catalog_service() -> LLMCatalogService:
    """Return the shared LLM catalog service instance (FastAPI dependency)."""
    return get_default_catalog_service()


LLMCatalogServiceDep = Annotated[
    LLMCatalogService,
    Depends(get_catalog_service),
]


def get_default_catalog_service() -> LLMCatalogService:
    """Return the application-wide ``LLMCatalogService`` singleton.

    Returns:
        The shared instance, creating it lazily on first access.
    """
    global _default_catalog_service
    if _default_catalog_service is None:
        _default_catalog_service = LLMCatalogService(get_llm_catalog_repository())
    return _default_catalog_service


def set_default_catalog_service(service: LLMCatalogService | None) -> None:
    """Override the shared LLM catalog service (used by tests).

    Args:
        service: Replacement instance, or ``None`` to reset to a fresh default.
    """
    global _default_catalog_service
    _default_catalog_service = service
