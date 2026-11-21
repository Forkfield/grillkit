# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for dashboard interview history queries."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.interview.domain.serialization import session_to_spec
from app.interview.domain.value_objects import (
    SectionBranchSpec,
    SessionSelection,
    TrackSelection,
)
from app.interview.queries.dashboard import InterviewDashboard
from app.interview.queries.projection import load_recent_session_snapshots
from app.interview.repositories.mappers import interview_read_from_orm
from app.interview.repositories.uow import InterviewUnitOfWork
from app.interview.schemas.interview import InterviewRead
from app.shared.infrastructure.database import Base
from app.shared.infrastructure.models import Interview
from tests.helpers.coding_seed import seed_active_coding_interview
from tests.helpers.completed_session_seed import seed_completed_theory_interview
from tests.helpers.interview_seed import (
    persist_interview_with_answers,
    seed_two_question_interview,
)
from tests.helpers.selection import minimal_selection_spec
from tests.helpers.sql_trace import count_selects
from tests.helpers.theory_seed import create_theory_section_for_interview


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine for testing."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture
def db_session(engine):
    """Create a test database session."""
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def test_format_local_datetime_utc():
    """UTC datetimes are converted to local formatted strings."""
    dt = datetime(2026, 5, 18, 12, 30, tzinfo=UTC)
    result = InterviewDashboard.format_local_datetime(dt)
    assert "2026" in result
    assert ":" in result


def test_interview_display_title():
    """Title is built from selection_spec."""
    interview = Interview(
        id="x",
        selection_spec=minimal_selection_spec(categories=["data-structures"]),
    )
    read_model = interview_read_from_orm(interview)
    assert InterviewDashboard.interview_display_title(read_model) == "Python Interview"


def test_interview_display_title_coding_only():
    """Coding-only sessions use coding sources for the dashboard title."""
    spec = session_to_spec(
        SessionSelection(
            session_mode="coding_only",
            theory=SectionBranchSpec(
                enabled=False,
                question_count=0,
                task_time_limit_seconds=None,
                sources=(),
            ),
            coding=SectionBranchSpec(
                enabled=True,
                question_count=1,
                task_time_limit_seconds=None,
                sources=(
                    TrackSelection(
                        track="python",
                        level="junior",
                        categories=("basics",),
                    ),
                ),
            ),
        )
    )
    interview = Interview(id="coding-1", selection_spec=spec)
    read_model = interview_read_from_orm(interview)
    assert InterviewDashboard.interview_display_title(read_model) == "Python Interview"


def test_list_recent_ordering(db_session):
    """load_recent_session_snapshots returns completed before older active when newer."""
    now = datetime.now(UTC)
    active = Interview(
        id="active-1",
        selection_spec=minimal_selection_spec(categories=["basics"]),
        status="active",
        started_at=now - timedelta(hours=2),
    )
    completed = Interview(
        id="done-1",
        selection_spec=minimal_selection_spec(categories=["algorithms"]),
        status="completed",
        started_at=now - timedelta(hours=3),
        completed_at=now,
    )
    db_session.add(active)
    db_session.add(completed)
    db_session.flush()
    create_theory_section_for_interview(
        db_session,
        active,
        question_count=5,
    )
    create_theory_section_for_interview(
        db_session,
        completed,
        question_count=3,
    )
    db_session.commit()

    class TestUow(InterviewUnitOfWork):
        def __init__(self) -> None:
            super().__init__()
            self._session = db_session

    with TestUow() as uow:
        recent = load_recent_session_snapshots(uow, limit=20)
    assert [snapshot.shell.id for snapshot in recent] == ["done-1", "active-1"]


def test_compute_max_score_uses_nested_breakdown_for_coding_only():
    """Coding-only completed sessions read max score from nested breakdown."""
    interview = InterviewRead(
        id="coding-done",
        status="completed",
        locale="en",
        selection_spec=minimal_selection_spec(categories=["basics"]),
        question_ids="[]",
        question_count=0,
        question_time_limit_seconds=None,
        answers=[],
        score=4,
        overall_feedback={
            "score_breakdown": {
                "coding": {
                    "score": 4,
                    "max": 5,
                    "skipped": False,
                    "questions": {"cod-001": {"score": 4, "max": 5}},
                }
            }
        },
    )
    assert (
        InterviewDashboard.compute_max_score(
            interview,
            interview.overall_feedback["score_breakdown"],
        )
        == 5
    )


def test_list_dashboard_rows(isolated_db):
    """Dashboard rows map session fields for the history table."""
    completed_id = seed_completed_theory_interview("dash-done-1")
    persist_interview_with_answers(
        Interview(
            id="dash-active-1",
            locale="en",
            selection_spec=minimal_selection_spec(categories=["basics"]),
            status="active",
            started_at=datetime.now(UTC),
        ),
        [],
        question_count=5,
    )

    with InterviewUnitOfWork() as uow:
        rows = InterviewDashboard(uow).list_rows(limit=20)

    completed = next(row for row in rows if row.id == completed_id)
    assert completed.title == "Python Interview"
    assert completed.session_mode_label == "Theory"
    assert completed.score_display == "4 / 5"
    assert completed.status_label == "Completed"
    assert completed.url == f"/interview/{completed_id}/results"

    active = next(row for row in rows if row.id == "dash-active-1")
    assert active.score_display == "—"
    assert active.status_label == "Active"
    assert active.url == "/interview/dash-active-1"


def test_list_rows_loads_each_collection_once(isolated_db):
    """Dashboard rows read shells, theory, and coding sections exactly once."""
    seed_two_question_interview("dash-selects-theory")
    seed_active_coding_interview("dash-selects-coding")

    with (
        count_selects(isolated_db) as trace,
        InterviewUnitOfWork() as uow,
    ):
        rows = InterviewDashboard(uow).list_rows(limit=20)

    assert len(rows) == 2
    assert len(trace.statements) == 5
