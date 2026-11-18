# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Setup endpoints module (JSON).

This module provides the setup API for configuring interview parameters
and creating new interview sessions. The setup page is rendered by the SPA
frontend; the backend only serves JSON page data and the create endpoint.
"""

from dataclasses import replace

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.coding.support.coding_availability import (
    is_coding_available_async,
)
from app.interview.api.deps import CreateSessionDep
from app.interview.api.setup_form import setup_form_context
from app.interview.domain.rules.selection import (
    parse_session_json,
    validate_session_selection,
)
from app.interview.schemas.setup import SetupCreateBody
from app.platform.api.deps import ConfigServiceDep
from app.platform.domain.config import AppConfig
from app.shared import coding as coding_bank
from app.shared.questions import list_categories, list_levels, list_tracks
from app.speech.api.deps import WhisperModelServiceDep
from app.speech.queries.speech_page import SttModelPageService

_MIN_QUESTIONS = 1
_MAX_QUESTIONS = 20


def _clamp_question_count(value: int) -> int:
    """Clamp question count to the allowed setup range.

    Args:
        value: Raw question count from the form.

    Returns:
        Value between ``_MIN_QUESTIONS`` and ``_MAX_QUESTIONS``.
    """
    return max(_MIN_QUESTIONS, min(_MAX_QUESTIONS, value))


def _page_payload(
    *,
    config: AppConfig | None,
    whisper_model_service: WhisperModelServiceDep,
    error: str | None = None,
    min_question_count: int = _MIN_QUESTIONS,
    min_coding_task_count: int = _MIN_QUESTIONS,
    initial_wizard_step: str = "mode",
) -> dict[str, object]:
    """Build the setup page JSON payload for the SPA."""
    payload: dict[str, object] = {
        "configured": config is not None,
        **setup_form_context(
            locale=config.locale if config is not None else "en",
            error=error,
            min_question_count=min_question_count,
            min_coding_task_count=min_coding_task_count,
            initial_wizard_step=initial_wizard_step,
        ),
    }
    if config is not None:
        stt = SttModelPageService.build_page_context(
            config,
            whisper_model_service=whisper_model_service,
        )
        payload["speech_model_banner"] = stt.speech_model_banner
        payload["speech_model_status"] = (
            stt.speech_model_status.model_dump()
            if stt.speech_model_status is not None
            else None
        )
    return payload


router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/options")
async def setup_options(
    track: str | None = None,
    level: str | None = None,
) -> JSONResponse:
    """Return cascaded setup options for dynamic form updates.

    Args:
        track: When set, returns levels for that question bank track.
        level: When set with track, returns categories for that pair.

    Returns:
        JSON with ``tracks``, ``levels``, or ``categories`` keys.
    """
    if track is None:
        return JSONResponse({"tracks": list_tracks()})

    tracks = list_tracks()
    if track not in tracks:
        raise HTTPException(status_code=404, detail=f"Unknown track: {track}")

    if level is None:
        return JSONResponse({"levels": list_levels(track)})

    levels = list_levels(track)
    if level not in levels:
        raise HTTPException(status_code=404, detail=f"Unknown level: {level}")

    return JSONResponse({"categories": sorted(list_categories(track, level))})


@router.get("/coding-options")
async def setup_coding_options(
    track: str | None = None,
    level: str | None = None,
) -> JSONResponse:
    """Return cascaded setup options for the coding task bank.

    Args:
        track: When set, returns levels for that coding track.
        level: When set with track, returns categories for that pair.

    Returns:
        JSON with ``tracks``, ``levels``, or ``categories`` keys.
    """
    if track is None:
        return JSONResponse({"tracks": coding_bank.list_tracks()})

    tracks = coding_bank.list_tracks()
    if track not in tracks:
        raise HTTPException(status_code=404, detail=f"Unknown coding track: {track}")

    if level is None:
        return JSONResponse({"levels": coding_bank.list_levels(track)})

    levels = coding_bank.list_levels(track)
    if level not in levels:
        raise HTTPException(status_code=404, detail=f"Unknown coding level: {level}")

    return JSONResponse(
        {"categories": sorted(coding_bank.list_categories(track, level))}
    )


@router.get("/coding-available")
async def setup_coding_available() -> JSONResponse:
    """Return whether coding sessions can be started from setup.

    Returns:
        JSON with ``available`` boolean.
    """
    return JSONResponse({"available": await is_coding_available_async()})


api_router = APIRouter(prefix="/api/setup", tags=["setup"])


@api_router.get("")
async def setup_page(
    config_service: ConfigServiceDep,
    whisper_model_service: WhisperModelServiceDep,
) -> dict[str, object]:
    """Return the setup page JSON payload for the SPA.

    Args:
        config_service: Provider configuration service.
        whisper_model_service: Whisper model download service.

    Returns:
        JSON with the setup form context, or ``{"configured": False}``
        when the provider is not configured yet (the SPA redirects to config).
    """
    config = config_service.get_config()
    if config is None:
        return {"configured": False}
    return _page_payload(config=config, whisper_model_service=whisper_model_service)


@api_router.post("")
async def create_interview(
    body: SetupCreateBody,
    config_service: ConfigServiceDep,
    session_creation: CreateSessionDep,
) -> dict[str, object]:
    """Create interview session from multi-track setup selection.

    Args:
        body: Parsed setup form submission.
        config_service: Provider configuration service.
        session_creation: Session creation service.

    Returns:
        JSON with ``redirect`` on success, or ``success=False`` plus an error
        message and refreshed min counts when validation fails.
    """
    config = config_service.get_config()
    if config is None:
        return {"success": False, "configured": False, "redirect": "/#/config"}

    theory_timer_seconds: int | None = None
    if body.enable_question_timer:
        theory_timer_seconds = max(1, body.question_time_minutes) * 60

    coding_timer_seconds: int | None = None
    if body.enable_coding_timer:
        coding_timer_seconds = max(1, body.coding_time_minutes) * 60

    clamped_theory_count = _clamp_question_count(body.question_count)
    clamped_coding_count = _clamp_question_count(body.coding_question_count)

    try:
        session = parse_session_json(body.selection_json)
        session = replace(
            session,
            theory=replace(
                session.theory,
                question_count=clamped_theory_count,
                task_time_limit_seconds=theory_timer_seconds,
            ),
            coding=replace(
                session.coding,
                question_count=clamped_coding_count,
                task_time_limit_seconds=coding_timer_seconds,
            ),
        )
        validate_session_selection(session)
        interview = session_creation.create_session(
            session,
            locale=config.locale,
        )
        return {"success": True, "redirect": f"/interview/{interview.id}"}
    except ValueError as e:
        min_theory = _MIN_QUESTIONS
        min_coding = _MIN_QUESTIONS
        try:
            parsed = parse_session_json(body.selection_json)
            if parsed.theory.enabled:
                min_theory = max(_MIN_QUESTIONS, parsed.theory_selection.topic_count)
            if parsed.coding.enabled:
                min_coding = max(_MIN_QUESTIONS, parsed.coding_selection.topic_count)
        except ValueError:
            pass
        return {
            "success": False,
            "error": str(e),
            "min_question_count": min_theory,
            "min_coding_task_count": min_coding,
        }
