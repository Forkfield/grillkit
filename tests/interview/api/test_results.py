# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for completed session results HTTP routes."""

from tests.helpers.completed_session_seed import seed_completed_theory_interview


def test_completed_interview_page_redirects_to_results(client, isolated_db) -> None:
    """Completed sessions no longer render the active interview page."""
    interview_id = seed_completed_theory_interview("results-redirect-1")
    response = client.get(f"/api/interview/{interview_id}")
    assert response.status_code == 200
    assert response.json()["redirect"] == f"/interview/{interview_id}/results"


def test_results_page_renders_for_completed_session(client, isolated_db) -> None:
    """Results hub exposes overall feedback and section cards as JSON."""
    interview_id = seed_completed_theory_interview("results-page-1")
    response = client.get(f"/api/interview/{interview_id}/results")
    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_feedback"]["overall_feedback"] == "Good theory performance."
    assert payload["section_cards"][0]["label"]
    assert payload["section_cards"][0]["detail_url"]
