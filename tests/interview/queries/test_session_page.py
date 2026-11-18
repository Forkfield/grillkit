# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for interview page context building."""

import asyncio

import pytest

from app.interview.domain.serialization import session_to_spec
from app.interview.domain.value_objects import (
    SectionBranchSpec,
    SessionSelection,
    TrackSelection,
)
from app.interview.queries.session_page import ActiveSessionPage as SessionPageService
from app.interview.repositories.uow import InterviewUnitOfWork
from app.interview.schemas.interview import AnswerRead, InterviewRead
from app.platform.domain.config import AppConfig
from app.shared.infrastructure.models import Answer, Interview
from tests.helpers.interview_seed import (
    persist_interview_with_answers,
    seed_two_question_interview,
)
from tests.helpers.selection import minimal_selection_spec
from tests.helpers.sql_trace import count_selects

_SPEC = minimal_selection_spec()


def _session() -> InterviewRead:
    """Build a minimal active interview read model."""
    return InterviewRead(
        id="s1",
        status="active",
        locale="en",
        selection_spec=_SPEC,
        question_ids='["q1"]',
        question_count=1,
        question_time_limit_seconds=None,
        answers=[
            AnswerRead(
                id=1,
                question_id="q1",
                order=1,
                round=0,
                question_text="Question?",
                question_code=None,
                answer_text=None,
                score=None,
                started_at=None,
            )
        ],
    )


def test_build_page_context_sets_audio_flag_from_catalog(monkeypatch, isolated_db):
    """Page context reflects whether the configured LLM accepts audio input."""
    del isolated_db

    enabled = SessionPageService.build_page_context(
        _session(),
        config=AppConfig(
            llm_preset_id="audio-model",
            timeout=60,
        ),
        question_voice_enabled=False,
        interview_model_accepts_audio=True,
    )
    disabled = SessionPageService.build_page_context(
        _session(),
        config=AppConfig(
            llm_preset_id="text-model",
            timeout=60,
        ),
        question_voice_enabled=False,
        interview_model_accepts_audio=False,
    )

    assert enabled.interview_model_accepts_audio is True
    assert disabled.interview_model_accepts_audio is False


def test_build_page_context_coding_only_session(isolated_db):
    """Coding-only sessions build page context without theory sources."""
    del isolated_db
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
    interview = InterviewRead(
        id="coding-1",
        status="active",
        locale="en",
        selection_spec=spec,
        question_ids="[]",
        question_count=0,
        question_time_limit_seconds=None,
        answers=[],
    )

    context = SessionPageService.build_page_context(
        interview,
        config=None,
        question_voice_enabled=False,
    )

    assert context.interview_title == "Python Interview"
    assert context.selection_lines == ["Python / junior: Basics"]


def test_prepare_page_issues_one_query_per_loaded_collection(isolated_db):
    """Page load reads the session, sections, and tasks without extra queries."""
    interview_id = seed_two_question_interview("page-selects-1")

    with (
        count_selects(isolated_db) as trace,
        InterviewUnitOfWork(auto_commit=True) as uow,
    ):
        render = asyncio.run(
            SessionPageService(uow).prepare_page(interview_id, config=None)
        )

    assert render.context is not None
    assert len(trace.statements) == 4


@pytest.mark.parametrize("task_time_limit_seconds", [None, 120])
def test_prepare_page_activation_does_not_reread_sections(
    isolated_db, task_time_limit_seconds
):
    """Starting the section timer writes without re-selecting the section."""
    interview_id = persist_interview_with_answers(
        Interview(
            id="page-selects-2",
            locale="en",
            selection_spec=minimal_selection_spec(categories=["basics"]),
            status="active",
        ),
        [
            Answer(question_id="q1", order=1, round=0, question_text="Question one?"),
            Answer(question_id="q2", order=2, round=0, question_text="Question two?"),
        ],
        question_count=2,
        task_time_limit_seconds=task_time_limit_seconds,
    )

    with (
        count_selects(isolated_db) as trace,
        InterviewUnitOfWork(auto_commit=True) as uow,
    ):
        render = asyncio.run(
            SessionPageService(uow).prepare_page(interview_id, config=None)
        )

    assert render.context is not None
    assert len(trace.statements) == 4
