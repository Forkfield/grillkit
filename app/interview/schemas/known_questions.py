# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Read models for known bank-item exclusion API."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.interview.domain.value_objects import SectionKind


class KnownItemMutation(BaseModel):
    """Request body for marking a known bank item.

    Attributes:
        branch: Section branch (``theory`` or ``coding``).
        item_id: ID from the YAML bank for that branch.
    """

    branch: SectionKind
    item_id: str = Field(min_length=1)


class KnownItemsRead(BaseModel):
    """Known bank item IDs grouped by section branch.

    Attributes:
        theory: Theory question IDs marked as known.
        coding: Coding task IDs marked as known.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    theory: list[str]
    coding: list[str]

    @classmethod
    def from_grouped(cls, grouped: dict[str, list[str]]) -> "KnownItemsRead":
        """Build the read model from the repository grouped dict.

        Args:
            grouped: Known item IDs grouped by branch (repo shape).

        Returns:
            Known item IDs for theory and coding.
        """
        return cls(
            theory=grouped.get("theory", []),
            coding=grouped.get("coding", []),
        )


class KnownItemView(BaseModel):
    """Display row for a known bank item on the manage page.

    Attributes:
        id: Bank item ID from the YAML bank.
        text: Resolved question or task text, or the ID when unresolved.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    id: str
    text: str


class KnownManagePageRead(BaseModel):
    """Read model for ``GET /api/known-questions/manage``.

    Attributes:
        theory_items: Known theory questions with resolved text.
        coding_items: Known coding tasks with resolved text.
        total_count: Total number of known bank items.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    theory_items: list[KnownItemView]
    coding_items: list[KnownItemView]
    total_count: int
