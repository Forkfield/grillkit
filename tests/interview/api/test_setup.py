# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for setup API cascaded options."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.interview.domain.value_objects import SessionSelection
from app.platform.domain.config import AppConfig


class TestSetupOptions:
    """Tests for GET /api/setup/options."""

    def test_lists_tracks(self, client):
        """Options without params returns available question-bank tracks."""
        with patch(
            "app.interview.queries.setup_options.list_tracks",
            return_value=["database", "python"],
        ):
            response = client.get("/api/setup/options")
        assert response.status_code == 200
        assert response.json() == {"tracks": ["database", "python"]}

    def test_lists_levels_for_track(self, client):
        """Options with track returns levels for that track."""
        with (
            patch(
                "app.interview.queries.setup_options.list_tracks",
                return_value=["python"],
            ),
            patch(
                "app.interview.queries.setup_options.list_levels",
                return_value=["junior", "middle"],
            ),
        ):
            response = client.get("/api/setup/options", params={"track": "python"})
        assert response.status_code == 200
        assert response.json() == {"levels": ["junior", "middle"]}

    def test_lists_categories_for_track_and_level(self, client):
        """Options with track and level returns topic categories."""
        with (
            patch(
                "app.interview.queries.setup_options.list_tracks",
                return_value=["python"],
            ),
            patch(
                "app.interview.queries.setup_options.list_levels",
                return_value=["junior"],
            ),
            patch(
                "app.interview.queries.setup_options.list_categories",
                return_value=["basics", "oop"],
            ),
        ):
            response = client.get(
                "/api/setup/options",
                params={"track": "python", "level": "junior"},
            )
        assert response.status_code == 200
        assert response.json() == {"categories": ["basics", "oop"]}

    def test_unknown_track_returns_404(self, client):
        """Unknown track slug returns 404."""
        with patch(
            "app.interview.queries.setup_options.list_tracks",
            return_value=["python"],
        ):
            response = client.get("/api/setup/options", params={"track": "java"})
        assert response.status_code == 404


class TestSetupCodingOptions:
    """Tests for GET /api/setup/coding-options and /api/setup/coding-available."""

    def test_lists_coding_tracks(self, client):
        """Coding options without params returns available coding tracks."""
        with patch(
            "app.interview.queries.setup_options.coding_bank.list_tracks",
            return_value=["python"],
        ):
            response = client.get("/api/setup/coding-options")
        assert response.status_code == 200
        assert response.json() == {"tracks": ["python"]}

    def test_coding_available_endpoint(self, client):
        """Coding availability endpoint reflects service flag."""
        with patch(
            "app.interview.api.setup.is_coding_available_async",
            new=AsyncMock(return_value=True),
        ):
            response = client.get("/api/setup/coding-available")
        assert response.status_code == 200
        assert response.json() == {"available": True}


class TestSetupConfigRedirect:
    """Setup requires provider configuration before starting an interview."""

    def test_setup_get_unconfigured(self, client):
        """GET /api/setup signals the provider is not configured."""
        with patch(
            "app.platform.domain.config.ConfigService.get_config", return_value=None
        ):
            response = client.get("/api/setup")
        assert response.status_code == 200
        assert response.json() == {"configured": False}

    def test_setup_post_redirects_without_config(self, client):
        """POST /api/setup redirects to /#/config when provider is not configured."""
        with patch(
            "app.platform.domain.config.ConfigService.get_config", return_value=None
        ):
            response = client.post(
                "/api/setup",
                json={
                    "selection_json": (
                        '{"sources":[{"track":"python",'
                        '"level":"junior","categories":["basics"]}]}'
                    ),
                    "question_count": 5,
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is False
        assert body["redirect"] == "/#/config"

    def test_setup_get_shows_configured_locale(self, client):
        """GET /api/setup returns interview language from saved config."""
        mock_config = AppConfig(
            locale="ru",
        )
        with (
            patch(
                "app.platform.domain.config.ConfigService.get_config",
                return_value=mock_config,
            ),
            patch(
                "app.interview.queries.setup_page.list_tracks",
                return_value=["python"],
            ),
            patch(
                "app.interview.queries.setup_page.list_levels",
                return_value=["junior"],
            ),
            patch(
                "app.interview.queries.setup_page.list_categories",
                return_value=["basics"],
            ),
        ):
            response = client.get("/api/setup")
        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is True
        assert body["locale_label"] == "Russian"
        assert body["locale"] == "ru"

    def test_setup_post_passes_timer_limit_when_enabled(self, client):
        """POST /api/setup forwards per-round timer seconds when the checkbox is set."""
        mock_config = AppConfig(
            locale="en",
        )
        captured: dict[str, object] = {}

        def fake_create(session, locale: str = "en") -> MagicMock:
            captured["session"] = session
            captured["locale"] = locale
            interview = MagicMock()
            interview.id = "timer-setup-id"
            return interview

        with (
            patch(
                "app.platform.domain.config.ConfigService.get_config",
                return_value=mock_config,
            ),
            patch(
                "app.interview.use_cases.create_session.CreateInterviewSession.create_session",
                side_effect=fake_create,
            ),
        ):
            response = client.post(
                "/api/setup",
                json={
                    "selection_json": (
                        '{"sources":[{"track":"python",'
                        '"level":"junior","categories":["basics"]}]}'
                    ),
                    "question_count": 5,
                    "enable_question_timer": True,
                    "question_time_minutes": 4,
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["redirect"] == "/interview/timer-setup-id"
        session = captured.get("session")
        assert isinstance(session, SessionSelection)
        assert session.theory.task_time_limit_seconds == 240

    def test_setup_post_rejects_question_count_below_topics(self, client):
        """POST /api/setup rejects when question count is below selected topic count."""
        mock_config = AppConfig(
            locale="en",
        )
        selection = (
            '{"sources":[{"track":"python","level":"junior",'
            '"categories":["basics","oop"]}]}'
        )
        with patch(
            "app.platform.domain.config.ConfigService.get_config",
            return_value=mock_config,
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
        assert "at least 2" in body["error"]


class TestSetupExcludeKnown:
    """Tests for exclude_known in setup selection JSON."""

    def test_parse_session_json_reads_exclude_known(self):
        """selection_json may disable known-question exclusion."""
        from app.interview.domain.rules.selection import parse_session_json

        raw = (
            '{"version":2,"session_mode":"theory_only","exclude_known":false,'
            '"theory":{"enabled":true,"question_count":1,'
            '"task_time_limit_seconds":null,'
            '"sources":[{"track":"python","level":"junior","categories":["basics"]}]},'
            '"coding":{"enabled":false,"question_count":0,'
            '"task_time_limit_seconds":null,"sources":[]}}'
        )
        session = parse_session_json(raw)
        assert session.exclude_known is False
