# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for coding availability checks."""

from unittest.mock import AsyncMock, patch

import pytest

from app.coding.support.coding_availability import (
    is_coding_available,
    is_judge0_healthy,
)


@pytest.mark.asyncio
async def test_is_coding_available_false_when_disabled(monkeypatch) -> None:
    """CODING_ENABLED=false disables coding without probing Judge0."""
    monkeypatch.setenv("CODING_ENABLED", "false")
    with patch(
        "app.coding.support.coding_availability.is_judge0_healthy",
        new=AsyncMock(return_value=True),
    ) as probe:
        assert await is_coding_available() is False
    probe.assert_not_called()


@pytest.mark.asyncio
async def test_is_coding_available_requires_judge0(monkeypatch) -> None:
    """Coding is unavailable when the Judge0 health check fails."""
    monkeypatch.setenv("CODING_ENABLED", "true")
    with patch(
        "app.coding.support.coding_availability.is_judge0_healthy",
        new=AsyncMock(return_value=False),
    ):
        assert await is_coding_available() is False
    with patch(
        "app.coding.support.coding_availability.is_judge0_healthy",
        new=AsyncMock(return_value=True),
    ):
        assert await is_coding_available() is True


@pytest.mark.asyncio
async def test_is_judge0_healthy_uses_gateway() -> None:
    """Health probe delegates to Judge0Gateway.health_check."""
    with patch(
        "app.shared.infrastructure.gateways.judge0.Judge0Gateway.from_env"
    ) as from_env:
        gateway = from_env.return_value
        gateway.health_check = AsyncMock(return_value=True)
        assert await is_judge0_healthy() is True
    from_env.assert_called_once_with()
