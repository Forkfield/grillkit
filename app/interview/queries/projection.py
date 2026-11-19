# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Assemble interview read models from domain aggregates."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from app.coding.domain.entities import CodingSection as DomainCodingSection
from app.coding.repositories.mappers import coding_section_from_orm
from app.interview.domain.entities import Interview as DomainInterview
from app.interview.domain.scoring import resolve_completed_read_score
from app.interview.domain.serialization import parse_session_spec
from app.interview.domain.session_phases import phase_order_for_mode
from app.interview.domain.value_objects import SectionKind, SessionSelection
from app.interview.repositories.mappers import (
    compose_interview_read,
    interview_from_orm,
)
from app.interview.repositories.uow import InterviewUnitOfWork
from app.interview.schemas.interview import InterviewRead
from app.theory.domain.entities import TheorySection as DomainTheorySection
from app.theory.repositories.mappers import theory_section_from_orm


@dataclass(frozen=True)
class SessionSnapshot:
    """One consistent read of a session shell and its section aggregates.

    The API read model is derived from the aggregates rather than stored
    alongside them, so replacing a section (for example after activating it)
    can never leave a stale read model behind.

    Attributes:
        shell: Interview shell aggregate as loaded from storage.
        session: Parsed selection (session mode, enabled sections, timers).
        theory: Theory section aggregate with tasks, if present.
        coding: Coding section aggregate with tasks, if present.
    """

    shell: DomainInterview
    session: SessionSelection
    theory: DomainTheorySection | None
    coding: DomainCodingSection | None

    @cached_property
    def interview(self) -> InterviewRead:
        """Compose the API read model from the current section aggregates."""
        return assemble_interview_read(self.shell, self.theory, self.coding)


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


def assemble_interview_read(
    shell: DomainInterview,
    theory: DomainTheorySection | None,
    coding: DomainCodingSection | None = None,
) -> InterviewRead:
    """Compose an interview read model with a resolved display score.

    Args:
        shell: Interview shell aggregate.
        theory: Theory section aggregate with tasks, if present.
        coding: Coding section aggregate, if present.

    Returns:
        Immutable interview read model for services and API.
    """
    read_model = compose_interview_read(shell, theory, coding)
    score = resolve_completed_read_score(shell, theory, coding)
    if score is None:
        return read_model
    return read_model.model_copy(update={"score": score})


def load_session_snapshot(
    uow: InterviewUnitOfWork,
    interview_id: str,
) -> SessionSnapshot | None:
    """Load a session shell and both section aggregates with one query.

    Args:
        uow: Active application unit of work.
        interview_id: Parent session UUID.

    Returns:
        Snapshot with parsed selection, or None when the session does not exist.
    """
    orm_interview = uow.interviews.get_with_sections(interview_id)
    if orm_interview is None:
        return None

    shell = interview_from_orm(orm_interview)
    theory = (
        theory_section_from_orm(orm_interview.theory_section)
        if orm_interview.theory_section is not None
        else None
    )
    coding = (
        coding_section_from_orm(orm_interview.coding_section)
        if orm_interview.coding_section is not None
        else None
    )
    if orm_interview.theory_section is not None:
        uow.theory_sections.remember(orm_interview.theory_section)
    if orm_interview.coding_section is not None:
        uow.coding_sections.remember(orm_interview.coding_section)
    # Compose once for the legacy-spec fallbacks used when parsing the session.
    interview = assemble_interview_read(shell, theory, coding)
    return SessionSnapshot(
        shell=shell,
        session=parse_session_spec(
            interview.selection_spec,
            question_count=interview.question_count,
            task_time_limit_seconds=interview.question_time_limit_seconds,
        ),
        theory=theory,
        coding=coding,
    )


def load_interview_read(
    uow: InterviewUnitOfWork,
    interview_id: str,
) -> InterviewRead | None:
    """Load a composed interview read model for one session.

    Args:
        uow: Active application unit of work.
        interview_id: Parent session UUID.

    Returns:
        Interview read model, or None when the session does not exist.
    """
    snapshot = load_session_snapshot(uow, interview_id)
    return snapshot.interview if snapshot is not None else None


def load_recent_interview_reads(
    uow: InterviewUnitOfWork,
    *,
    limit: int = 20,
) -> list[InterviewRead]:
    """Load recent interview read models, newest first.

    Args:
        uow: Active application unit of work.
        limit: Maximum number of sessions to return.

    Returns:
        Composed interview read models with theory tasks when present.
    """
    shells = uow.interviews.list_recent_aggregates(limit=limit)
    if not shells:
        return []
    interview_ids = [shell.id for shell in shells]
    theory_by_id = uow.theory_sections.get_aggregates_by_interview_ids(interview_ids)
    coding_by_id = uow.coding_sections.get_aggregates_by_interview_ids(interview_ids)
    return [
        assemble_interview_read(
            shell,
            theory_by_id.get(shell.id),
            coding_by_id.get(shell.id),
        )
        for shell in shells
    ]
