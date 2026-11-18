# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Session phase transitions between interview sections."""

from dataclasses import replace

from app.interview.domain.session_phases import (
    phase_order_for_mode,
    section_services,
)
from app.interview.domain.value_objects import SectionKind
from app.interview.queries.projection import SessionSnapshot, load_session_snapshot
from app.interview.repositories.uow import InterviewUnitOfWork


def section_complete(snapshot: SessionSnapshot, kind: SectionKind) -> bool:
    """Return whether one section has no remaining user work.

    Args:
        snapshot: Loaded session with section aggregates.
        kind: Section to inspect.

    Returns:
        True when the section exists and has no remaining user work.
    """
    if kind == "theory":
        theory = snapshot.theory
        return theory is not None and theory.is_complete()

    coding = snapshot.coding
    if coding is None:
        return False
    return coding.status in {"skipped", "completed"} or coding.is_complete()


def active_section(snapshot: SessionSnapshot) -> SectionKind:
    """Return the section the user should interact with now.

    Args:
        snapshot: Loaded session with section aggregates.

    Returns:
        First incomplete section in phase order, or the last phase when done.
    """
    order = phase_order_for_mode(snapshot.session.session_mode)
    for kind in order:
        if not section_complete(snapshot, kind):
            return kind
    return order[-1]


def activate_current_section(
    uow: InterviewUnitOfWork,
    snapshot: SessionSnapshot,
) -> SessionSnapshot:
    """Promote the active section and start its timer when needed.

    Writes only when the section state actually changes: a pending coding
    section becomes active once earlier phases are complete, and the first
    pending task gets a ``started_at`` timestamp when a timer is configured.

    Args:
        uow: Active unit of work used to persist the change.
        snapshot: Loaded session with section aggregates.

    Returns:
        Snapshot with the updated section aggregate.
    """
    kind = active_section(snapshot)
    if kind == "theory":
        theory = snapshot.theory
        if theory is None:
            return snapshot
        updated_theory = theory.with_activated().start_next_task_timer()
        if updated_theory is theory:
            return snapshot
        uow.theory_sections.save_aggregate(updated_theory)
        return replace(snapshot, theory=updated_theory)

    coding = snapshot.coding
    if coding is None:
        return snapshot
    updated_coding = coding.with_activated().start_next_task_timer()
    if updated_coding is coding:
        return snapshot
    uow.coding_sections.save_aggregate(updated_coding)
    return replace(snapshot, coding=updated_coding)


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

        Runs on the orchestrator's unit of work so phase transitions do not open
        a second SQLite connection while the caller still holds a write lock.

        Args:
            interview_id: Parent interview UUID.
            section_kind: Section that the user just completed.
        """
        services = section_services(self._uow)
        services[section_kind].on_phase_complete(interview_id)
        snapshot = load_session_snapshot(self._uow, interview_id)
        if snapshot is not None:
            _ = activate_current_section(self._uow, snapshot)
