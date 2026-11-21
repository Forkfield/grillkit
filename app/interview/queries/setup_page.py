# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Setup page read-model builder for the SPA."""

from collections.abc import Callable

from app.coding.support.coding_availability import is_coding_available
from app.interview.domain.rules.bank_selection import track_label
from app.interview.schemas.setup import (
    SetupPageRead,
    SetupSessionMode,
    SetupTrackSection,
)
from app.platform.domain.config import AppConfig
from app.shared import coding as coding_bank
from app.shared.infrastructure.gateways.whisper_model import WhisperModelService
from app.shared.locales import SUPPORTED_LOCALES, normalize_locale
from app.shared.questions import list_categories, list_levels, list_tracks
from app.speech.queries.speech_page import SttModelPageService

_DEFAULT_MIN_COUNT = 1
_DEFAULT_WIZARD_STEP = "mode"


def _build_track_sections(
    tracks: list[str],
    *,
    list_levels_fn: Callable[[str], list[str]],
    list_categories_fn: Callable[[str, str], list[str]],
) -> list[SetupTrackSection]:
    """Build setup track blocks for one question bank.

    Args:
        tracks: Track slugs from the bank.
        list_levels_fn: Callable ``(track) -> levels``.
        list_categories_fn: Callable ``(track, level) -> categories``.

    Returns:
        Track blocks for the setup SPA.
    """
    sections: list[SetupTrackSection] = []
    for slug in tracks:
        levels = list_levels_fn(slug)
        default_level = levels[0] if levels else ""
        categories = (
            sorted(list_categories_fn(slug, default_level)) if default_level else []
        )
        sections.append(
            SetupTrackSection(
                slug=slug,
                label=track_label(slug),
                levels=levels,
                default_level=default_level,
                categories=categories,
            )
        )
    return sections


def _session_modes(coding_available: bool) -> list[SetupSessionMode]:
    """Build the selectable session modes.

    Args:
        coding_available: Whether Judge0-backed modes can be selected.

    Returns:
        Mode entries for the wizard.
    """
    unavailable = None if coding_available else "Unavailable"
    return [
        SetupSessionMode(
            value="theory_only",
            label="Theory only",
            description="Question-and-answer theory section",
            enabled=True,
        ),
        SetupSessionMode(
            value="theory_then_coding",
            label="Theory, then coding",
            description="Theory section followed by coding challenges",
            enabled=coding_available,
            badge=unavailable,
        ),
        SetupSessionMode(
            value="coding_then_theory",
            label="Coding, then theory",
            description="Coding challenges followed by theory questions",
            enabled=coding_available,
            badge=unavailable,
        ),
        SetupSessionMode(
            value="coding_only",
            label="Coding only",
            description="Coding challenges without theory questions",
            enabled=coding_available,
            badge=unavailable,
        ),
    ]


async def build_setup_page(
    *,
    config: AppConfig,
    whisper_model_service: WhisperModelService | None = None,
    error: str | None = None,
    min_question_count: int = _DEFAULT_MIN_COUNT,
    min_coding_task_count: int = _DEFAULT_MIN_COUNT,
    initial_wizard_step: str = _DEFAULT_WIZARD_STEP,
) -> SetupPageRead:
    """Assemble the setup page read model for the SPA.

    Args:
        config: Saved provider configuration.
        whisper_model_service: Whisper model service instance (injectable).
        error: Optional form-level error message.
        min_question_count: Minimum allowed theory question count.
        min_coding_task_count: Minimum allowed coding task count.
        initial_wizard_step: Wizard step id to open on load.

    Returns:
        Frozen page read model.
    """
    coding_available = await is_coding_available()
    locale_code = normalize_locale(config.locale)
    speech = SttModelPageService.build_page_context(
        config,
        whisper_model_service=whisper_model_service,
    )
    tracks = list_tracks()
    track_sections = (
        _build_track_sections(
            tracks,
            list_levels_fn=list_levels,
            list_categories_fn=list_categories,
        )
        if tracks
        else []
    )
    return SetupPageRead(
        configured=True,
        tracks=[(slug, track_label(slug)) for slug in tracks],
        track_sections=track_sections,
        coding_track_sections=_build_track_sections(
            coding_bank.list_tracks(),
            list_levels_fn=coding_bank.list_levels,
            list_categories_fn=coding_bank.list_categories,
        ),
        session_modes=_session_modes(coding_available) if tracks else [],
        coding_available=coding_available,
        locale=locale_code,
        locale_label=SUPPORTED_LOCALES[locale_code],
        error=error if tracks else (error or "No question banks found."),
        min_question_count=min_question_count,
        min_coding_task_count=min_coding_task_count,
        initial_wizard_step=initial_wizard_step,
        speech_model_banner=speech.speech_model_banner,
        speech_model_status=speech.speech_model_status,
    )
