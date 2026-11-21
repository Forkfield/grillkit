# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Mark and unmark known bank items for future session exclusion."""

from app.interview.domain.value_objects import SectionKind
from app.interview.repositories.uow import InterviewUnitOfWork
from app.interview.schemas.known_questions import KnownItemsRead


class MarkKnownItem:
    """Mark a bank item as known for future session exclusion."""

    def __init__(self, uow: InterviewUnitOfWork) -> None:
        """Initialize with the unit of work for the request scope.

        Args:
            uow: Application unit of work (auto-commit for HTTP handlers).
        """
        self._uow = uow

    def execute(self, branch: SectionKind, item_id: str) -> KnownItemsRead:
        """Apply the mark and return the updated grouped list.

        Marking an already-known item is a no-op (idempotent).

        Args:
            branch: ``theory`` or ``coding``.
            item_id: ID from the YAML bank for that branch.

        Returns:
            Known item IDs after the mutation.
        """
        self._uow.known_questions.mark(branch, item_id)
        return KnownItemsRead.from_grouped(self._uow.known_questions.list_all_grouped())


class UnmarkKnownItem:
    """Remove a bank item from the known list."""

    def __init__(self, uow: InterviewUnitOfWork) -> None:
        """Initialize with the unit of work for the request scope.

        Args:
            uow: Application unit of work (auto-commit for HTTP handlers).
        """
        self._uow = uow

    def execute(self, branch: SectionKind, item_id: str) -> KnownItemsRead:
        """Apply the unmark and return the updated grouped list.

        Unmarking an absent item is a no-op (idempotent), matching DELETE
        semantics.

        Args:
            branch: ``theory`` or ``coding``.
            item_id: ID from the YAML bank for that branch.

        Returns:
            Known item IDs after the mutation.
        """
        self._uow.known_questions.unmark(branch, item_id)
        return KnownItemsRead.from_grouped(self._uow.known_questions.list_all_grouped())
