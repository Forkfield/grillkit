# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Completed session results and section review pages."""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.interview.api.deps import (
    CodingReviewPageDep,
    CompletedSessionResultsDep,
    TheoryReviewPageDep,
)

api_router = APIRouter(prefix="/api/interview", tags=["interview-results"])


def _redirect_payload(url: str, *, not_found: bool = False) -> JSONResponse:
    """Build a JSON redirect response for the SPA.

    Args:
        url: Target route the SPA should navigate to.
        not_found: True when the target session does not exist.

    Returns:
        JSON response with a ``redirect`` field, using 404 for missing sessions
        so the SPA can distinguish genuine 404s from ordinary redirects.
    """
    status = 404 if not_found else 200
    body: dict[str, Any] = {"redirect": url}
    if not_found:
        body["not_found"] = True
    return JSONResponse(body, status_code=status)


@api_router.get("/{interview_id}/results", response_model=None)
async def session_results_json(
    interview_id: str,
    service: CompletedSessionResultsDep,
) -> dict[str, Any] | JSONResponse:
    """Return the completed session results hub JSON payload for the SPA.

    Args:
        interview_id: Session UUID.
        service: Session results page service for the request scope.

    Returns:
        JSON with the full results context, or a ``redirect`` payload when the
        session is missing or not completed.
    """
    page = service.prepare_page(interview_id)
    if page.redirect_url is not None:
        # A redirect to "/" means the session does not exist at all.
        return _redirect_payload(
            page.redirect_url,
            not_found=page.redirect_url == "/",
        )
    return page.template_context or {}


@api_router.get("/{interview_id}/theory", response_model=None)
async def theory_review_json(
    interview_id: str,
    service: TheoryReviewPageDep,
) -> dict[str, Any] | JSONResponse:
    """Return the completed theory section review JSON payload for the SPA.

    Args:
        interview_id: Session UUID.
        service: Theory review service for the request scope.

    Returns:
        JSON with the theory review context, or a ``redirect`` to results when
        the session or theory section is unavailable.
    """
    context = service.build_context_for(interview_id)
    if context is None:
        return _redirect_payload(
            f"/interview/{interview_id}/results",
            not_found=True,
        )
    return context.model_dump()


@api_router.get("/{interview_id}/coding", response_model=None)
async def coding_review_json(
    interview_id: str,
    service: CodingReviewPageDep,
) -> dict[str, Any] | JSONResponse:
    """Return the completed coding section review JSON payload for the SPA.

    Args:
        interview_id: Session UUID.
        service: Coding review service for the request scope.

    Returns:
        JSON with the coding review context, or a ``redirect`` to results when
        the session or coding section is unavailable.
    """
    context = service.build_context_for(interview_id)
    if context is None:
        return _redirect_payload(
            f"/interview/{interview_id}/results",
            not_found=True,
        )
    return context.model_dump()
