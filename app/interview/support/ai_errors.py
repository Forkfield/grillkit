# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""User-facing AI provider error messages for interview clients."""

import re

_SERVER_ERROR_MARKERS = ("upstream", "server_error")
_HTTP_SERVER_ERROR = re.compile(r"(?:error|status) code:\s*5\d{2}\b")


def ai_error_message_for_client(exc: Exception) -> str:
    """Turn provider failures into a short client error message.

    Args:
        exc: Exception raised during AI evaluation.

    Returns:
        User-facing error message.
    """
    text = str(exc)
    lowered = text.lower()
    if "not found" in lowered and "model" in lowered:
        return (
            "AI model is not available on the configured endpoint. "
            "Open the Configuration page and verify the model name and "
            "provider settings."
        )
    if "timed out" in lowered or "timeout" in lowered:
        return (
            "AI evaluation timed out. The model may still be loading — "
            "wait and try again, or increase the timeout on the Configuration "
            "page."
        )
    if any(marker in lowered for marker in _SERVER_ERROR_MARKERS) or (
        _HTTP_SERVER_ERROR.search(lowered)
    ):
        return (
            "AI provider returned a server error. The model endpoint may be "
            "temporarily unavailable — try again in a moment."
        )
    return f"AI evaluation failed: {text}"
