# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Negative tests for interview setup POST (validation, clamping, errors)."""

from unittest.mock import AsyncMock, patch

from app.interview.domain.serialization import session_to_spec
from app.interview.domain.value_objects import (
    SectionBranchSpec,
    SessionSelection,
    TrackSelection,
)
from app.platform.domain.config import AppConfig
from app.shared.questions import list_categories


class TestSetupNegative:
    """Tests for invalid setup submissions."""

    def _config(self) -> AppConfig:
        return AppConfig(
            locale="en",
        )

    def _valid_theory_selection(self, **kwargs):
        session = SessionSelection(
            session_mode="theory_only",
            exclude_known=False,
            theory=SectionBranchSpec(
                enabled=True,
                question_count=5,
                task_time_limit_seconds=None,
                sources=(
                    TrackSelection(
                        track="python",
                        level="junior",
                        categories=("basics",),
                    ),
                ),
            ),
            coding=SectionBranchSpec(
                enabled=False,
                question_count=0,
                task_time_limit_seconds=None,
                sources=(),
            ),
        )
        return session_to_spec(session)

    def test_question_count_clamped_to_min(self, client, isolated_db):
        """question_count=0 is clamped to _MIN_QUESTIONS (1)."""
        selection = self._valid_theory_selection()
        with (
            patch(
                "app.platform.domain.config.ConfigService.get_config",
                return_value=self._config(),
            ),
        ):
            response = client.post(
                "/api/setup",
                json={
                    "selection_json": selection,
                    "question_count": 0,
                },
            )
        # Should still create session (clamped to 1)
        assert response.status_code == 200
        assert "/interview/" in response.json()["redirect"]

    def test_question_count_clamped_to_max(self, client, isolated_db):
        """question_count=50 is clamped to _MAX_QUESTIONS (20)."""
        from app.interview.domain.serialization import session_to_spec
        from app.interview.domain.value_objects import TrackSelection

        extensive = SessionSelection.theory_only(
            sources=(
                TrackSelection(
                    track="python",
                    level="junior",
                    categories=tuple(
                        list_categories("python", "junior"),
                    ),
                ),
            ),
            question_count=50,
        )
        with patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=self._config(),
        ):
            response = client.post(
                "/api/setup",
                json={
                    "selection_json": session_to_spec(extensive),
                    "question_count": 50,
                },
            )
        # Should still create session (clamped to 20)
        assert response.status_code == 200
        assert "/interview/" in response.json()["redirect"]

    def test_malformed_json_shows_error(self, client, isolated_db):
        """Malformed selection_json returns setup form with error."""
        with patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=self._config(),
        ):
            response = client.post(
                "/api/setup",
                json={
                    "selection_json": "not valid json {{{ ",
                    "question_count": 5,
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert "error" in body

    def test_unknown_category_rejected(self, client, isolated_db):
        """Invalid category in selection returns error."""

        selection = (
            '{"version":2,"session_mode":"theory_only",'
            '"theory":{"enabled":true,"question_count":5,"sources":['
            '{"track":"python","level":"junior","categories":["unknown-category"]}'
            ']},"coding":{"enabled":false}}'
        )
        # The error happens during plan validation, not JSON parse
        with patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=self._config(),
        ):
            response = client.post(
                "/api/setup",
                json={
                    "selection_json": selection,
                    "question_count": 5,
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False

    def test_coding_question_count_clamped(self, client, isolated_db):
        """coding_question_count is also clamped to 1–20 range."""
        session = SessionSelection(
            session_mode="coding_only",
            theory=SectionBranchSpec(
                enabled=False,
                question_count=0,
                task_time_limit_seconds=None,
                sources=(),
            ),
            coding=SectionBranchSpec(
                enabled=True,
                question_count=5,
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
        # Coding available should be True for this test path
        with (
            patch(
                "app.platform.domain.config.ConfigService.get_config",
                return_value=self._config(),
            ),
            patch(
                "app.interview.use_cases.setup_session.is_coding_available",
                new=AsyncMock(return_value=True),
            ),
        ):
            response = client.post(
                "/api/setup",
                json={
                    "selection_json": session_to_spec(session),
                    "question_count": 5,
                    "coding_question_count": 0,  # Should clamp to 1
                },
            )
        assert response.status_code == 200
        assert "/interview/" in response.json()["redirect"]

    def test_too_few_questions_for_topics_shows_error(self, client, isolated_db):
        """When question_count < topic_count and all are single-cat topics, error shown."""
        selection = (
            '{"version":2,"session_mode":"theory_only",'
            '"theory":{"enabled":true,"question_count":1,"sources":['
            '{"track":"python","level":"junior","categories":["basics","oop"]}'
            ']},"coding":{"enabled":false}}'
        )
        with patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=self._config(),
        ):
            response = client.post(
                "/api/setup",
                json={
                    "selection_json": selection,
                    "question_count": 1,
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert "at least" in body["error"].lower() or "error" in body["error"].lower()

    def test_setup_get_unconfigured(self, client):
        """GET /api/setup signals the provider is not configured."""
        with patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=None,
        ):
            response = client.get("/api/setup")
        assert response.status_code == 200
        assert response.json() == {"configured": False}

    def test_setup_post_redirects_without_config(self, client):
        """POST /api/setup redirects to /#/config when provider is not configured."""
        with patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=None,
        ):
            response = client.post(
                "/api/setup",
                json={"selection_json": "{}", "question_count": 5},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is False
        assert body["redirect"] == "/#/config"
