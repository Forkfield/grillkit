# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Start an interview session from the setup form."""

from dataclasses import dataclass, replace

from app.coding.support.coding_availability import is_coding_available
from app.interview.domain.rules.selection import (
    parse_session_payload,
    validate_session_selection,
)
from app.interview.domain.value_objects import SessionSelection
from app.interview.use_cases.create_session import CreateInterviewSession

_MIN_COUNT = 1
_MAX_COUNT = 20


def _clamp_count(value: int) -> int:
    """Clamp a setup count to the allowed 1–20 range.

    Args:
        value: Raw count from the setup body.

    Returns:
        Count between ``_MIN_COUNT`` and ``_MAX_COUNT``.
    """
    return max(_MIN_COUNT, min(_MAX_COUNT, value))


def _minimum_counts(session: SessionSelection) -> tuple[int, int]:
    """Return per-section minimum counts for the setup form.

    Args:
        session: Merged session selection.

    Returns:
        ``(min_question_count, min_coding_task_count)``.
    """
    theory = (
        max(_MIN_COUNT, session.theory_selection.topic_count)
        if session.theory.enabled
        else _MIN_COUNT
    )
    coding = (
        max(_MIN_COUNT, session.coding_selection.topic_count)
        if session.coding.enabled
        else _MIN_COUNT
    )
    return theory, coding


@dataclass(frozen=True)
class SetupSessionCommand:
    """Normalized setup form submission.

    Attributes:
        selection_json: Raw v2 selection payload from the SPA.
        question_count: Requested theory question count.
        coding_question_count: Requested coding task count.
        theory_timer_seconds: Per-round theory limit, or None when disabled.
        coding_timer_seconds: Per-task coding limit, or None when disabled.
        locale: Interview locale from provider config.
    """

    selection_json: str
    question_count: int
    coding_question_count: int
    theory_timer_seconds: int | None
    coding_timer_seconds: int | None
    locale: str


@dataclass(frozen=True)
class SetupSessionResult:
    """Outcome of a setup submission.

    Attributes:
        interview_id: Created session UUID, or None on validation failure.
        error: Validation or creation error message.
        min_question_count: Minimum theory count to echo back to the form.
        min_coding_task_count: Minimum coding count to echo back to the form.
    """

    interview_id: str | None = None
    error: str | None = None
    min_question_count: int = _MIN_COUNT
    min_coding_task_count: int = _MIN_COUNT


class StartSessionFromSetup:
    """Validate a setup submission and create the interview session."""

    def __init__(self, create_session: CreateInterviewSession) -> None:
        """Initialize with the session creation use case.

        Args:
            create_session: Orchestrator that persists the shell and sections.
        """
        self._create_session = create_session

    async def execute(self, command: SetupSessionCommand) -> SetupSessionResult:
        """Apply the submitted counts and timers, validate, then create.

        Args:
            command: Normalized setup form submission.

        Returns:
            Created session id, or a validation error with form minimums.
        """
        try:
            session = parse_session_payload(command.selection_json)
        except ValueError as exc:
            return SetupSessionResult(error=str(exc))

        session = replace(
            session,
            theory=replace(
                session.theory,
                question_count=_clamp_count(command.question_count),
                task_time_limit_seconds=command.theory_timer_seconds,
            ),
            coding=replace(
                session.coding,
                question_count=_clamp_count(command.coding_question_count),
                task_time_limit_seconds=command.coding_timer_seconds,
            ),
        )
        min_theory, min_coding = _minimum_counts(session)
        try:
            coding_available = (
                await is_coding_available() if session.coding.enabled else False
            )
            validate_session_selection(session, coding_available=coding_available)
            interview = self._create_session.create_session(
                session,
                locale=command.locale,
            )
        except ValueError as exc:
            return SetupSessionResult(
                error=str(exc),
                min_question_count=min_theory,
                min_coding_task_count=min_coding,
            )
        return SetupSessionResult(interview_id=interview.id)
