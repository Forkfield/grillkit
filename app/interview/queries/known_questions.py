# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Known-questions read models for the SPA."""

from app.interview.repositories.uow import InterviewUnitOfWork
from app.interview.schemas.known_questions import (
    KnownItemsRead,
    KnownItemView,
    KnownManagePageRead,
)
from app.interview.support.bank_text import resolve_known_views


class KnownQuestionsQuery:
    """Read-side queries over known bank-item exclusions."""

    def __init__(self, uow: InterviewUnitOfWork) -> None:
        """Initialize with the unit of work for the request scope.

        Args:
            uow: Application unit of work (auto-commit for HTTP handlers).
        """
        self._uow = uow

    def list_items(self) -> KnownItemsRead:
        """Return all known bank item IDs grouped by branch.

        Returns:
            Known item IDs for theory and coding.
        """
        return KnownItemsRead.from_grouped(self._uow.known_questions.list_all_grouped())

    def manage_page(self) -> KnownManagePageRead:
        """Return the manage-page read model with resolved bank text.

        Returns:
            Known item views and the total count for the SPA manage page.
        """
        grouped = self._uow.known_questions.list_all_grouped()
        views = resolve_known_views(grouped)
        return KnownManagePageRead(
            theory_items=[
                KnownItemView(id=item.id, text=item.text)
                for item in views.get("theory", [])
            ],
            coding_items=[
                KnownItemView(id=item.id, text=item.text)
                for item in views.get("coding", [])
            ],
            total_count=len(grouped.get("theory", [])) + len(grouped.get("coding", [])),
        )
