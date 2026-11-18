# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""HTTP API for known bank-item exclusions."""

from dataclasses import asdict

from fastapi import APIRouter

from app.interview.schemas.known_questions import KnownItemMutation, KnownItemsResponse
from app.interview.support.bank_text import KnownQuestionView, resolve_known_views
from app.shared.application.uow_deps import UoWAutoCommitDep

router = APIRouter(prefix="/known-questions", tags=["known-questions"])


@router.get("")
def list_known_questions(
    uow: UoWAutoCommitDep,
) -> KnownItemsResponse:
    """Return all known bank item IDs grouped by branch."""
    grouped = uow.known_questions.list_all_grouped()
    return KnownItemsResponse(
        theory=grouped.get("theory", []),
        coding=grouped.get("coding", []),
    )


@router.post("")
def mark_known_item(
    body: KnownItemMutation,
    uow: UoWAutoCommitDep,
) -> KnownItemsResponse:
    """Mark a bank item as known for future session exclusion."""
    uow.known_questions.mark(body.branch, body.item_id)
    grouped = uow.known_questions.list_all_grouped()
    return KnownItemsResponse(
        theory=grouped.get("theory", []),
        coding=grouped.get("coding", []),
    )


@router.delete("")
def unmark_known_item(
    body: KnownItemMutation,
    uow: UoWAutoCommitDep,
) -> KnownItemsResponse:
    """Remove a bank item from the known list."""
    uow.known_questions.unmark(body.branch, body.item_id)
    grouped = uow.known_questions.list_all_grouped()
    return KnownItemsResponse(
        theory=grouped.get("theory", []),
        coding=grouped.get("coding", []),
    )


def _known_view_dict(item: KnownQuestionView) -> dict[str, str]:
    """Convert a display row into a JSON-serializable dict."""
    return asdict(item)


api_router = APIRouter(prefix="/api/known-questions", tags=["known-questions"])


@api_router.get("/manage")
def manage_known_questions(uow: UoWAutoCommitDep) -> dict[str, object]:
    """Return known bank-item views (with bank text) for the SPA manage page.

    Args:
        uow: Auto-commit unit of work for the request scope.

    Returns:
        JSON payload with ``theory_items``, ``coding_items`` and ``total_count``.
    """
    known = resolve_known_views(uow.known_questions.list_all_grouped())
    theory = [_known_view_dict(item) for item in known.get("theory", [])]
    coding = [_known_view_dict(item) for item in known.get("coding", [])]
    return {
        "theory_items": theory,
        "coding_items": coding,
        "total_count": uow.known_questions.count(),
    }
