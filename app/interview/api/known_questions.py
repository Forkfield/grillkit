# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""HTTP API for known bank-item exclusions.

The SPA manage page reads enriched views from ``GET /manage``; the interview
and setup pages list, mark and unmark items through the collection endpoints.
"""

from fastapi import APIRouter

from app.interview.api.deps import (
    KnownQuestionsQueryDep,
    MarkKnownItemDep,
    UnmarkKnownItemDep,
)
from app.interview.domain.value_objects import SectionKind
from app.interview.schemas.known_questions import (
    KnownItemMutation,
    KnownItemsRead,
    KnownManagePageRead,
)

router = APIRouter(prefix="/api/known-questions", tags=["known-questions"])


@router.get("", response_model=KnownItemsRead)
def list_known_items(query: KnownQuestionsQueryDep) -> KnownItemsRead:
    """Return all known bank item IDs grouped by branch.

    Args:
        query: Known-questions read query.

    Returns:
        Known item IDs for theory and coding.
    """
    return query.list_items()


@router.post("", response_model=KnownItemsRead)
def mark_known_item(
    body: KnownItemMutation,
    mark: MarkKnownItemDep,
) -> KnownItemsRead:
    """Mark a bank item as known for future session exclusion.

    Args:
        body: Branch and bank item ID.
        mark: Mark-known-item use case.

    Returns:
        Known item IDs after the mutation.
    """
    return mark.execute(body.branch, body.item_id)


@router.delete("", response_model=KnownItemsRead)
def unmark_known_item(
    branch: SectionKind,
    item_id: str,
    unmark: UnmarkKnownItemDep,
) -> KnownItemsRead:
    """Remove a bank item from the known list.

    Args:
        branch: ``theory`` or ``coding``.
        item_id: ID from the YAML bank for that branch.
        unmark: Unmark-known-item use case.

    Returns:
        Known item IDs after the mutation (absent items are ignored).
    """
    return unmark.execute(branch, item_id)


@router.get("/manage", response_model=KnownManagePageRead)
def manage_known_questions(query: KnownQuestionsQueryDep) -> KnownManagePageRead:
    """Return known bank-item views (with bank text) for the manage page.

    Args:
        query: Known-questions read query.

    Returns:
        Manage-page read model with ``theory_items``, ``coding_items`` and
        ``total_count``.
    """
    return query.manage_page()
