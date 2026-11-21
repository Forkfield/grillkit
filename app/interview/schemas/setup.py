# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Setup page + create-interview wire models (JSON)."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.speech.schemas.status import WhisperModelStatusRead


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


class SetupTrackSection(BaseModel):
    """One track block in the setup form.

    Attributes:
        slug: Track slug from the question bank.
        label: Human-readable track label.
        levels: Available levels for the track.
        default_level: Level pre-selected by the SPA.
        categories: Categories of the default level.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    slug: str
    label: str
    levels: list[str]
    default_level: str
    categories: list[str]


class SetupSessionMode(BaseModel):
    """One selectable session mode in the setup form.

    Attributes:
        value: Session mode identifier stored in the selection spec.
        label: Short mode label.
        description: One-line explanation for the UI.
        enabled: Whether the mode can be selected.
        badge: Optional badge text (for example ``Unavailable``).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    value: str
    label: str
    description: str
    enabled: bool
    badge: str | None = None


class SetupPageRead(BaseModel):
    """Read model for ``GET /api/setup``.

    Every page field has a default so the unconfigured response can be a bare
    ``configured: False``; the route serializes with ``exclude_unset``.

    Attributes:
        configured: Whether a provider config exists.
        tracks: ``(slug, label)`` pairs for the theory bank.
        track_sections: Theory track blocks with levels and categories.
        coding_track_sections: Coding track blocks with levels and categories.
        session_modes: Modes offered by the wizard.
        coding_available: Whether Judge0-backed coding modes are offered.
        locale: Normalized interview locale.
        locale_label: Human-readable locale label.
        error: Form-level error message, if any.
        min_question_count: Minimum theory question count for the form.
        min_coding_task_count: Minimum coding task count for the form.
        initial_wizard_step: Wizard step to open on load.
        speech_model_banner: Whether to show the missing-model banner.
        speech_model_status: Whisper model status snapshot.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    configured: bool = False
    tracks: list[tuple[str, str]] = Field(default_factory=list)
    track_sections: list[SetupTrackSection] = Field(default_factory=list)
    coding_track_sections: list[SetupTrackSection] = Field(default_factory=list)
    session_modes: list[SetupSessionMode] = Field(default_factory=list)
    coding_available: bool = False
    locale: str = "en"
    locale_label: str = "English"
    error: str | None = None
    min_question_count: int = 1
    min_coding_task_count: int = 1
    initial_wizard_step: str = "mode"
    speech_model_banner: bool = False
    speech_model_status: WhisperModelStatusRead | None = None


class SetupOptionsRead(BaseModel):
    """Cascaded options response; exactly one key is set.

    Attributes:
        tracks: Available track slugs.
        levels: Available levels for a track.
        categories: Available categories for a track/level pair.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    tracks: list[str] | None = None
    levels: list[str] | None = None
    categories: list[str] | None = None


class SetupCodingAvailableRead(BaseModel):
    """Coding availability flag for setup.

    Attributes:
        available: Whether coding sessions can be started.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    available: bool


class SetupCreateResponse(BaseModel):
    """Result of ``POST /api/setup``.

    Attributes:
        success: Whether the session was created.
        redirect: SPA route to open on success (or ``/#/config`` when unset).
        configured: Present only when the provider config is missing.
        error: Validation or creation error message.
        min_question_count: Minimum theory count to show with the error.
        min_coding_task_count: Minimum coding count to show with the error.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    success: bool
    redirect: str | None = None
    configured: bool | None = None
    error: str | None = None
    min_question_count: int | None = None
    min_coding_task_count: int | None = None
