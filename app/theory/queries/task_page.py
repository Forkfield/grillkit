# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Theory section page context builder."""

from app.interview.domain.serialization import parse_session_spec
from app.interview.domain.value_objects import SessionSelection
from app.interview.queries.loader import InterviewQuery
from app.interview.schemas.interview import InterviewRead
from app.shared.task_timer import remaining_seconds
from app.theory.schemas.page import TheoryPageContext


def build_theory_context(
    interview: InterviewRead,
    *,
    session: SessionSelection | None = None,
) -> TheoryPageContext | None:
    """Assemble theory panel context from a loaded interview read model.

    Args:
        interview: Interview read model with theory tasks mirrored as answers.
        session: Parsed selection; parsed from the read model when omitted.

    Returns:
        Theory page context, or None when the session has no theory tasks.
    """
    if session is None:
        session = parse_session_spec(
            interview.selection_spec,
            question_count=interview.question_count,
            task_time_limit_seconds=interview.question_time_limit_seconds,
        )
    if not session.theory.enabled:
        return None

    current = InterviewQuery.get_current_unanswered(interview)
    timer_enabled = interview.question_time_limit_seconds is not None
    remaining = (
        remaining_seconds(current.started_at, interview.question_time_limit_seconds)
        if current is not None
        else None
    )
    return TheoryPageContext(
        answers=interview.answers,
        current_question=current,
        current_answer_id=current.id if current is not None else None,
        question_timer_enabled=timer_enabled,
        question_time_limit_seconds=interview.question_time_limit_seconds,
        timer_remaining_seconds=remaining,
        current_round=current.round if current is not None else 0,
        complete=current is None and bool(interview.answers),
    )
