# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for completed session results and section review JSON API.

Covers the SPA-facing endpoints in ``app/interview/api/results.py``:
``/api/interview/{id}/results``, ``/api/interview/{id}/theory`` and
``/api/interview/{id}/coding``.
"""

from unittest.mock import patch

from app.shared.infrastructure.models import Interview
from tests.helpers.completed_session_seed import (
    seed_completed_coding_interview,
    seed_completed_theory_interview,
)
from tests.helpers.interview_seed import persist_interview_with_answers
from tests.helpers.selection import minimal_selection_spec


def _config():
    from app.platform.domain.config import AppConfig

    return AppConfig(
        locale="en",
    )


class TestResultsApi:
    """Tests for GET /api/interview/{id}/results."""

    def test_completed_theory_returns_context(self, client, isolated_db):
        """A completed theory session returns the full results hub JSON."""
        interview_id = seed_completed_theory_interview("results-api-1")
        with patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=_config(),
        ):
            response = client.get(f"/api/interview/{interview_id}/results")
        assert response.status_code == 200
        body = response.json()
        assert body["interview"]["id"] == interview_id
        assert body["interview"]["status"] == "completed"
        assert (
            body["overall_feedback"]["overall_feedback"] == "Good theory performance."
        )
        assert body["max_score"] > 0
        assert body["section_cards"]
        assert body["section_cards"][0]["section"] == "theory"
        assert body["section_cards"][0]["detail_url"] == (
            f"/interview/{interview_id}/theory"
        )

    def test_active_session_redirects(self, client, isolated_db):
        """An active (not completed) session redirects to the interview page."""
        persist_interview_with_answers(
            Interview(
                id="results-active-1",
                locale="en",
                selection_spec=minimal_selection_spec(categories=["basics"]),
                status="active",
            ),
            [],
        )
        with patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=_config(),
        ):
            response = client.get("/api/interview/results-active-1/results")
        assert response.status_code == 200
        assert response.json() == {"redirect": "/interview/results-active-1"}

    def test_missing_session_returns_404(self, client, isolated_db):
        """An unknown session returns a 404 JSON redirect to the dashboard."""
        with patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=_config(),
        ):
            response = client.get("/api/interview/nope-1/results")
        assert response.status_code == 404
        body = response.json()
        assert body["redirect"] == "/"
        assert body["not_found"] is True


class TestTheoryReviewApi:
    """Tests for GET /api/interview/{id}/theory."""

    def test_completed_theory_returns_context(self, client, isolated_db):
        """A completed theory session returns chat history and section score."""
        interview_id = seed_completed_theory_interview("theory-api-1")
        with patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=_config(),
        ):
            response = client.get(f"/api/interview/{interview_id}/theory")
        assert response.status_code == 200
        body = response.json()
        assert body["interview_id"] == interview_id
        assert body["section_score"] == 4
        assert body["answers"]
        answer = body["answers"][0]
        assert answer["question_id"] == "q1"
        assert answer["answer_text"] == "A programming language"
        assert answer["score"] == 4
        assert body["section_feedback"]["section_feedback"] == "Clear and concise."

    def test_missing_session_redirects_to_results(self, client, isolated_db):
        """An unknown or incomplete session redirects to the results hub."""
        with patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=_config(),
        ):
            response = client.get("/api/interview/nope-1/theory")
        assert response.status_code == 404
        assert response.json() == {
            "redirect": "/interview/nope-1/results",
            "not_found": True,
        }


class TestCodingReviewApi:
    """Tests for GET /api/interview/{id}/coding."""

    def test_completed_coding_returns_context(self, client, isolated_db):
        """A completed coding session returns grouped tasks and rounds."""
        interview_id = seed_completed_coding_interview("coding-api-1")
        with patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=_config(),
        ):
            response = client.get(f"/api/interview/{interview_id}/coding")
        assert response.status_code == 200
        body = response.json()
        assert body["interview_id"] == interview_id
        assert body["section_score"] == 4
        assert body["tasks"]
        task = body["tasks"][0]
        assert task["task_id"] == "cod-001"
        assert task["rounds"]
        assert task["rounds"][0]["submitted_code"] == "def solve():\n    return 1"

    def test_missing_session_redirects_to_results(self, client, isolated_db):
        """An unknown session redirects to the results hub."""
        with patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=_config(),
        ):
            response = client.get("/api/interview/nope-1/coding")
        assert response.status_code == 404
        assert response.json() == {
            "redirect": "/interview/nope-1/results",
            "not_found": True,
        }
