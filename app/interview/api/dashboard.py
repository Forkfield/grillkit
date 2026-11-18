# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Dashboard API endpoint.

Returns interview history as JSON for the frontend SPA.
"""

from fastapi import APIRouter

from app.interview.api.deps import InterviewDashboardDep
from app.interview.schemas.dashboard import DashboardRowRead

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard", response_model=list[DashboardRowRead])
async def dashboard_rows(dashboard: InterviewDashboardDep) -> list[DashboardRowRead]:
    """Return recent interview history as JSON.

    Args:
        dashboard: Dashboard builder service for the request scope.

    Returns:
        JSON list of dashboard rows, newest-first.
    """
    return dashboard.list_rows(limit=20)
