# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for interview HTTP routes (dashboard and legacy endpoints)."""

from unittest.mock import patch

from app.interview.schemas.dashboard import DashboardRowRead


class TestDashboardRouter:
    """Tests for the dashboard JSON API."""

    def test_dashboard_includes_interview_history(self, client):
        """Dashboard API returns interview history rows."""
        mock_rows = [
            DashboardRowRead(
                id="id-1",
                title="Python Interview",
                question_count=5,
                session_mode_label="Theory",
                score_display="10 / 15",
                status="completed",
                status_label="Completed",
                datetime_display="18 May 2026, 14:30",
                url="/interview/id-1/results",
            )
        ]
        with patch(
            "app.interview.queries.dashboard.InterviewDashboard.list_rows",
            return_value=mock_rows,
        ):
            response = client.get("/api/dashboard")
        assert response.status_code == 200
        body = response.json()
        assert body[0]["title"] == "Python Interview"
        assert body[0]["score_display"] == "10 / 15"

    def test_dashboard_returns_json(self, client):
        """Dashboard returns JSON without any provider config."""
        with patch(
            "app.interview.queries.dashboard.InterviewDashboard.list_rows",
            return_value=[],
        ):
            response = client.get("/api/dashboard")
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")
        assert response.json() == []


class TestInterviewHttpRoutes:
    """Tests for interview HTTP surface (page only; interaction is WebSocket)."""

    def test_legacy_post_answer_removed(self, client):
        """Legacy form POST answer endpoint is no longer registered."""
        response = client.post(
            "/interview/test-id/answer",
            data={"question_id": "q1", "answer_text": "text"},
        )
        assert response.status_code == 404

    def test_legacy_post_complete_removed(self, client):
        """Legacy form POST complete endpoint is no longer registered."""
        response = client.post("/interview/test-id/complete")
        assert response.status_code == 404


class TestInterviewPageJson:
    """Tests for the JSON interview page API consumed by the SPA."""

    @staticmethod
    def _mock_page(monkeypatch, render):
        async def fake_prepare_page(
            self,
            interview_id,
            *,
            config,
            accepts_audio_input=False,
            whisper_model_service,
        ):
            return render

        from app.interview.use_cases.session_page import OpenSessionPage

        monkeypatch.setattr(OpenSessionPage, "prepare_page", fake_prepare_page)

    def _get(
        self,
        client,
        monkeypatch,
        *,
        context=None,
        redirect_url=None,
        not_found=False,
    ):
        from app.interview.use_cases.session_page import SessionPageRender

        self._mock_page(
            monkeypatch,
            SessionPageRender(
                context=context,
                redirect_url=redirect_url,
                not_found=not_found,
            ),
        )
        return client.get("/api/interview/test-id")

    def test_active_session_returns_context(
        self, client, monkeypatch, minimal_app_config
    ):
        """GET /api/interview/{id} returns the active page context as JSON."""
        with patch(
            "app.platform.domain.config.ConfigService.load_active",
            return_value=(minimal_app_config, None),
        ):
            response = self._get(
                client,
                monkeypatch,
                context={"interview": {"status": "active"}, "active_phase": "theory"},
            )
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")
        body = response.json()
        assert body["interview"]["status"] == "active"
        assert body["active_phase"] == "theory"

    def test_completed_session_redirects_to_results(
        self, client, monkeypatch, minimal_app_config
    ):
        """GET /api/interview/{id} signals a redirect to results when completed."""
        with patch(
            "app.platform.domain.config.ConfigService.load_active",
            return_value=(minimal_app_config, None),
        ):
            response = self._get(
                client,
                monkeypatch,
                redirect_url="/interview/test-id/results",
            )
        assert response.status_code == 200
        assert response.json() == {"redirect": "/interview/test-id/results"}

    def test_missing_session_returns_404(self, client, monkeypatch):
        """GET /api/interview/{id} returns 404 JSON for an unknown session."""
        response = self._get(client, monkeypatch, not_found=True)
        assert response.status_code == 404
        body = response.json()
        assert body["redirect"] == "/"
        assert body["not_found"] is True
