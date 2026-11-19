# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for FastAPI application factory."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
import pytest

from app.main import create_app, lifespan


class TestCreateApp:
    """Tests for create_app factory function."""

    def test_app_creation(self):
        """Test that create_app returns a FastAPI instance."""
        app = create_app()
        assert app is not None
        assert app.title == "GrillKit"
        assert app.description == "AI Interview Trainer"
        assert app.version == "2026.8.9"

    def test_health_endpoint_registered(self):
        """Test that the liveness probe route is registered."""
        app = create_app()
        routes = [getattr(route, "path", "") for route in app.routes]
        assert "/health" in routes

    def test_routers_included(self):
        """Test that routers are included."""
        app = create_app()
        routes = [getattr(route, "path", "") for route in app.routes]

        # Check dashboard API path exists
        assert "/api/dashboard" in routes or "/api/dashboard" in [
            getattr(r, "path", "") for r in app.routes
        ]
        # Check config router paths exist (they have /config prefix)
        config_routes = [r for r in app.routes if "/config" in getattr(r, "path", "")]
        assert len(config_routes) > 0


class TestLifespan:
    """Tests for lifespan context manager."""

    @pytest.mark.asyncio
    async def test_lifespan_yields_control(self):
        """Test that lifespan yields control to the app."""
        with (
            patch(
                "app.platform.domain.speech_runtime.SpeechRuntimeCoordinator.startup",
                new=AsyncMock(),
            ),
            patch(
                "app.platform.domain.speech_runtime.SpeechRuntimeCoordinator.unload_all",
            ),
        ):
            mock_app = MagicMock()
            entered = False
            exited = False

            async with lifespan(mock_app):
                entered = True

            exited = True
            assert entered
            assert exited


class TestAppIntegration:
    """Integration tests for the application."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        with (
            patch(
                "app.platform.domain.speech_runtime.SpeechRuntimeCoordinator.startup",
                new=AsyncMock(),
            ),
            patch(
                "app.platform.domain.speech_runtime.SpeechRuntimeCoordinator.unload_all",
            ),
        ):
            app = create_app()
            with TestClient(app) as test_client:
                yield test_client

    def test_dashboard_endpoint(self, client):
        """Test that the home page returns the dashboard HTML."""
        with patch(
            "app.interview.queries.dashboard.InterviewDashboard.list_rows",
            return_value=[],
        ):
            response = client.get("/api/dashboard")
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")

    def test_config_api_exists(self, client):
        """Test that config API endpoint exists and returns JSON."""
        response = client.get("/api/config")
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")
