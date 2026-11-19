# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for coding section page context."""

import asyncio
import json

from app.coding.queries.task_page import build_coding_context
from app.interview.queries.projection import load_session_snapshot
from app.interview.repositories.uow import InterviewUnitOfWork
from app.interview.use_cases.session_page import OpenSessionPage
from tests.helpers.coding_seed import seed_active_coding_interview


def test_build_context_returns_none_without_section():
    """Coding page context is absent when the session has no coding section."""
    assert build_coding_context(None) is None


def test_build_context_exposes_current_task(isolated_db):
    """Coding page context includes the active task and progress fields."""
    del isolated_db
    interview_id, task_id = seed_active_coding_interview("coding-page-1")
    with InterviewUnitOfWork() as uow:
        snapshot = load_session_snapshot(uow, interview_id)
        assert snapshot is not None
        context = build_coding_context(snapshot.coding)

    assert context is not None
    assert context.task_count == 1
    assert context.completed_tasks == 0
    assert context.current_task is not None
    assert context.current_task["task_id"] == task_id
    assert context.current_task_row_id is not None
    assert "hidden_tests" not in json.dumps(context.current_task["task_spec"])


def test_full_template_context_includes_coding_key(isolated_db):
    """Session page merges coding context for the interview SPA."""
    del isolated_db
    interview_id, _task_id = seed_active_coding_interview("coding-page-2")

    with InterviewUnitOfWork() as uow:
        render = asyncio.run(
            OpenSessionPage(uow).prepare_page(interview_id, config=None)
        )

    context = render.context
    assert context is not None
    assert context["coding"] is not None
    assert context["coding"]["task_count"] == 1
    assert context["session_mode_label"]


def test_interview_route_uses_coding_template(client, isolated_db):
    """Active coding phase returns a coding JSON context."""
    interview_id, _task_id = seed_active_coding_interview("coding-template-1")
    response = client.get(f"/api/interview/{interview_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["active_phase"] == "coding"
    assert payload["coding"] is not None
    assert payload["coding"]["task_count"] == 1
