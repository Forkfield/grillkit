# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Shared in-process download state for disk-cached ML artifacts."""

import asyncio
from collections.abc import Awaitable, Callable
import logging

logger = logging.getLogger(__name__)


class ArtifactDownloadService:
    """Download lock, progress, and background task orchestration for artifacts.

    Each instance carries its own download lock, progress, and error state, so
    Whisper, Piper, and other artifacts never share one download lock or
    progress stream.
    """

    def __init__(self) -> None:
        """Initialize per-instance download tracking state."""
        self._download_lock = asyncio.Lock()
        self._active_key: str | None = None
        self._percent = 0
        self._error_key: str | None = None
        self._error_message: str | None = None

    def reset_download_state(self) -> None:
        """Clear in-memory download progress (for tests)."""
        self._active_key = None
        self._percent = 0
        self._error_key = None
        self._error_message = None

    def active_download_error(self, key: str) -> str | None:
        """Return a stored error message for ``key`` when no download is active."""
        if (
            self._error_key == key
            and self._error_message is not None
            and self._active_key is None
        ):
            return self._error_message
        return None

    def is_downloading(self, key: str) -> bool:
        """Return whether ``key`` is the artifact currently being downloaded."""
        return self._active_key == key

    def download_percent(self) -> int:
        """Return the current download percent for the active artifact."""
        return self._percent

    def set_download_percent(self, percent: int) -> None:
        """Update in-memory download percent from progress callbacks."""
        self._percent = percent

    async def schedule_download(
        self,
        key: str,
        runner: Callable[[str], Awaitable[None]],
    ) -> bool:
        """Start a background download when none is already active.

        Args:
            key: Artifact identifier (size, voice id, etc.).
            runner: Async callable that performs install and load.

        Returns:
            True when a new download task was scheduled.
        """
        async with self._download_lock:
            if self._active_key is not None:
                return False
            self._active_key = key
            self._percent = 0
            self._error_key = None
            self._error_message = None

        asyncio.create_task(self._run_download_task(key, runner))
        return True

    async def _run_download_task(
        self,
        key: str,
        runner: Callable[[str], Awaitable[None]],
    ) -> None:
        """Execute ``runner`` and update shared error/active state."""
        try:
            await runner(key)
            self.clear_download_error()
        except Exception as exc:
            logger.exception("Artifact download failed for %s", key)
            self.record_download_error(key, str(exc))
        finally:
            async with self._download_lock:
                self._active_key = None
                self._percent = 0

    def record_download_error(self, key: str, message: str) -> None:
        """Store the last download failure for status reporting."""
        self._error_key = key
        self._error_message = message

    def clear_download_error(self) -> None:
        """Clear the last download error after a successful install."""
        self._error_key = None
        self._error_message = None
