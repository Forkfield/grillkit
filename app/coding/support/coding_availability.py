# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Coding feature availability checks for setup and session creation."""

import os

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _coding_enabled_env() -> bool:
    """Return whether coding is enabled via ``CODING_ENABLED``.

    Returns:
        True when coding is enabled in the environment.
    """
    return os.environ.get("CODING_ENABLED", "true").lower() in _TRUTHY


async def is_judge0_healthy() -> bool:
    """Probe Judge0 via ``GET /about``.

    Returns:
        True when the health endpoint responds with HTTP 200.
    """
    from app.shared.infrastructure.gateways.judge0 import Judge0Gateway

    return await Judge0Gateway.from_env().health_check()


async def is_coding_available() -> bool:
    """Return whether coding can be selected on setup and created.

    Requires ``CODING_ENABLED`` and a healthy Judge0 instance. All callers are
    async (API handlers and use cases); there is no synchronous variant.

    Returns:
        True when coding sessions may be started from setup.
    """
    if not _coding_enabled_env():
        return False
    return await is_judge0_healthy()
