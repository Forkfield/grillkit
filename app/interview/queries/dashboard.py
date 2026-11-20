# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Dashboard view-model builder for interview history."""

from datetime import UTC, datetime
from typing import Any

from app.coding.domain.entities import CodingSection
from app.interview.domain.rules.selection import session_display_title
from app.interview.domain.serialization import parse_session_spec
from app.interview.domain.value_objects import (
    SessionSelection,
    session_mode_label,
)
from app.interview.queries.projection import (
    load_recent_session_snapshots,
)
from app.interview.repositories.uow import InterviewUnitOfWork
from app.interview.schemas.dashboard import DashboardRowRead
from app.interview.schemas.interview import InterviewRead
from app.theory.domain.entities import TheorySection

DASHBOARD_ROW_LIMIT = 20


class InterviewDashboard:
    """Build dashboard rows and display helpers for interview history."""

    def __init__(self, uow: InterviewUnitOfWork) -> None:
        """Initialize with the active unit of work."""
        self._uow = uow

    @staticmethod
    def format_local_datetime(dt: datetime | None) -> str:
        """Format a timezone-aware datetime in the local timezone.

        Args:
            dt: UTC or aware datetime, or None.

        Returns:
            Formatted string such as ``18 May 2026, 14:30``, or empty string.
        """
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone().strftime("%d %b %Y, %H:%M")

    @staticmethod
    def interview_display_title(
        interview: InterviewRead,
        *,
        session: SessionSelection | None = None,
    ) -> str:
        """Build dashboard/interview page title from selection.

        Args:
            interview: Interview read model.
            session: Parsed selection; parsed from the read model when omitted.

        Returns:
            Title such as ``Python Interview`` or ``Multi-topic Interview``.
        """
        if session is None:
            session = parse_session_spec(interview.selection_spec)
        return session_display_title(session)

    @staticmethod
    def _max_score_from_breakdown(score_breakdown: dict[str, Any]) -> int:
        """Sum maximum points from nested or flat score breakdown payloads.

        Args:
            score_breakdown: Session evaluation breakdown dict.

        Returns:
            Maximum achievable score encoded in the breakdown.
        """
        total = 0
        for key, entry in score_breakdown.items():
            if key == "total" or not isinstance(entry, dict):
                continue
            max_score = entry.get("max")
            if isinstance(max_score, int):
                total += max_score
        return total

    @staticmethod
    def compute_max_score(
        interview: InterviewRead,
        score_breakdown: dict[str, Any] | None = None,
        *,
        uow: InterviewUnitOfWork | None = None,
        coding_section: CodingSection | None = None,
        session: SessionSelection | None = None,
    ) -> int:
        """Compute maximum achievable score for a session.

        Uses AI ``score_breakdown`` when provided; otherwise estimates
        five points per answered theory round or submitted coding round.

        Args:
            interview: Interview read model with answers loaded.
            score_breakdown: Optional per-question breakdown from session evaluation.
            uow: Unit of work used to load the coding section on demand.
            coding_section: Pre-loaded coding section that takes precedence over
                ``uow`` (used to avoid per-row queries in batched contexts).
            session: Parsed selection; parsed from the read model when omitted.

        Returns:
            Maximum possible score for the session.
        """
        if score_breakdown:
            breakdown_total = InterviewDashboard._max_score_from_breakdown(
                score_breakdown
            )
            if breakdown_total > 0:
                return breakdown_total

        if session is None:
            session = parse_session_spec(
                interview.selection_spec,
                question_count=interview.question_count,
                task_time_limit_seconds=interview.question_time_limit_seconds,
            )

        if session.theory.enabled:
            theory_max = (
                len(interview.answers)
                if interview.answers
                else interview.question_count
            ) * TheorySection.MAX_SCORE_PER_ROUND
            if theory_max > 0:
                return theory_max

        if session.coding.enabled:
            section = coding_section
            if section is None and uow is not None:
                section = uow.coding_sections.get_aggregate(interview.id)
            if section is not None:
                return section.max_score()
            if interview.question_count > 0:
                return interview.question_count * CodingSection.MAX_SCORE_PER_ROUND

        return 0

    def list_rows(self, limit: int = DASHBOARD_ROW_LIMIT) -> list[DashboardRowRead]:
        """Load recent interviews for the dashboard history table.

        Args:
            limit: Maximum rows to return.

        Returns:
            Rows sorted newest-first (completed or started time).
        """
        snapshots = load_recent_session_snapshots(self._uow, limit=limit)

        rows: list[DashboardRowRead] = []
        for snapshot in snapshots:
            interview = snapshot.interview
            session = snapshot.session
            if interview.status == "completed":
                feedback = interview.overall_feedback
                breakdown = feedback.get("score_breakdown") if feedback else None
                max_score = InterviewDashboard.compute_max_score(
                    interview,
                    breakdown,
                    coding_section=snapshot.coding,
                    session=session,
                )
                score = interview.score if interview.score is not None else 0
                score_display = f"{score} / {max_score}"
                status_label = "Completed"
                when = interview.completed_at
            else:
                score_display = "—"
                status_label = "Active"
                when = interview.started_at

            rows.append(
                DashboardRowRead(
                    id=interview.id,
                    title=session_display_title(session),
                    question_count=interview.question_count,
                    session_mode_label=session_mode_label(session.session_mode),
                    score_display=score_display,
                    status=interview.status,
                    status_label=status_label,
                    datetime_display=InterviewDashboard.format_local_datetime(when),
                    url=(
                        f"/interview/{interview.id}/results"
                        if interview.status == "completed"
                        else f"/interview/{interview.id}"
                    ),
                )
            )
        return rows
