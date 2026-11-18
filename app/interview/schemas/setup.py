# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Setup page + create-interview wire models (JSON)."""

from pydantic import BaseModel, Field


class SetupCreateBody(BaseModel):
    """JSON body for creating an interview session from the setup form.

    Attributes:
        selection_json: Selection payload built by the setup form (v2 spec).
        question_count: Number of theory questions.
        coding_question_count: Number of coding tasks.
        enable_question_timer: Whether the per-question timer is enabled.
        question_time_minutes: Per-round theory limit in minutes when enabled.
        enable_coding_timer: Whether the per-task timer is enabled.
        coding_time_minutes: Per-task coding limit in minutes when enabled.
    """

    selection_json: str = Field(min_length=1)
    question_count: int = 5
    coding_question_count: int = 2
    enable_question_timer: bool = False
    question_time_minutes: int = Field(default=3, ge=1)
    enable_coding_timer: bool = False
    coding_time_minutes: int = Field(default=10, ge=1)
