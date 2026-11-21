# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Session phase transitions between interview sections."""

from dataclasses import replace

from app.interview.domain.session_phases import section_services
from app.interview.domain.value_objects import SectionKind
from app.interview.queries.projection import (
    SessionSnapshot,
    active_section,
    load_session_snapshot,
)
from app.interview.repositories.uow import InterviewUnitOfWork


def activate_current_section(
    uow: InterviewUnitOfWork,
    snapshot: SessionSnapshot,
    *,
    start_timer: bool = True,
) -> SessionSnapshot:
    """Promote the active section and start its timer when needed.

    Writes only when the section state actually changes: a pending coding
    section becomes active once earlier phases are complete, and the first
    pending task gets a ``started_at`` timestamp when a timer is configured.

    Args:
        uow: Active unit of work used to persist the change.
        snapshot: Loaded session with section aggregates.
        start_timer: Whether to start the first pending task timer. Page loads
            pass True; phase-completion hooks pass False so the clock starts
            only once the user is shown the question.

    Returns:
        Snapshot with the updated section aggregate.
    """
    kind = active_section(snapshot)
    if kind == "theory":
        theory = snapshot.theory
        if theory is None:
            return snapshot
        updated_theory = theory.with_activated()
        if start_timer:
            updated_theory = updated_theory.start_next_task_timer()
        if updated_theory is theory:
            return snapshot
        uow.theory_sections.save_aggregate(updated_theory)
        return replace(snapshot, theory=updated_theory)

    coding = snapshot.coding
    if coding is None:
        return snapshot
    updated_coding = coding.with_activated()
    if start_timer:
        updated_coding = updated_coding.start_next_task_timer()
    if updated_coding is coding:
        return snapshot
    uow.coding_sections.save_aggregate(updated_coding)
    return replace(snapshot, coding=updated_coding)


def open_session(
    uow: InterviewUnitOfWork,
    interview_id: str,
) -> SessionSnapshot | None:
    """Load a session and start the clock of the phase the user should see.

    Opening the page is the only place that starts a section timer. Phase
    completion hooks call :func:`activate_current_section` without a timer so
    the clock does not run while the finished phase is still on screen.

    Args:
        uow: Active unit of work used to persist the started timer.
        interview_id: Parent session UUID.

    Returns:
        Snapshot with the activated section, or None when the session is missing.
    """
    snapshot = load_session_snapshot(uow, interview_id)
    if snapshot is None or snapshot.interview.status != "active":
        return snapshot
    return activate_current_section(uow, snapshot)


class AdvanceSessionPhase:
    """Coordinate phase completion hooks across interview sections."""

    def __init__(self, uow: InterviewUnitOfWork) -> None:
        """Initialize with the active unit of work.

        Args:
            uow: Shared application unit of work for this phase scope.
        """
        self._uow: InterviewUnitOfWork = uow

    def notify_section_complete(
        self,
        interview_id: str,
        section_kind: SectionKind,
    ) -> None:
        """Run section hooks and promote the next phase when a phase finishes.

        Runs on the caller's unit of work so phase transitions do not open
        a second SQLite connection while the caller still holds a write lock.
        The next phase timer is left untouched: the session page starts it when
        the user opens the section, so the clock does not run while the finished
        phase is still on screen.

        Args:
            interview_id: Parent interview UUID.
            section_kind: Section that the user just completed.
        """
        services = section_services(self._uow)
        services[section_kind].on_phase_complete(interview_id)
        snapshot = load_session_snapshot(self._uow, interview_id)
        if snapshot is not None:
            _ = activate_current_section(self._uow, snapshot, start_timer=False)
