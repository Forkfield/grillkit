# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""WebSocket/API payload helpers for theory sections."""

from typing import Any

from app.theory.domain.entities import TheoryTask


def next_task_payload(task: TheoryTask) -> dict[str, Any]:
    """Build WebSocket/API payload for the next unanswered task.

    Args:
        task: Next unanswered theory task round.

    Returns:
        Dict with question fields for the client.
    """
    return {
        "id": task.id,
        "question_id": task.question_id,
        "order": task.order,
        "question_text": task.question_text,
        "question_code": task.question_code,
        "round": task.round,
    }
