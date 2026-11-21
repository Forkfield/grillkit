# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Setup endpoints module (JSON).

The setup page is rendered by the SPA frontend; the backend serves the page
read model, cascaded bank options, coding availability, and the create
endpoint.
"""

from fastapi import APIRouter, HTTPException

from app.coding.support.coding_availability import is_coding_available
from app.interview.api.deps import StartSetupSessionDep
from app.interview.queries.setup_options import (
    UnknownSetupOptionError,
    coding_options,
    theory_options,
)
from app.interview.queries.setup_page import build_setup_page
from app.interview.schemas.setup import (
    SetupCodingAvailableRead,
    SetupCreateBody,
    SetupCreateResponse,
    SetupOptionsRead,
    SetupPageRead,
)
from app.interview.use_cases.setup_session import SetupSessionCommand
from app.platform.api.deps import ConfigServiceDep
from app.speech.api.deps import WhisperModelServiceDep

router = APIRouter(prefix="/api/setup", tags=["setup"])


@router.get(
    "/options",
    response_model=SetupOptionsRead,
    response_model_exclude_none=True,
)
async def setup_options(
    track: str | None = None,
    level: str | None = None,
) -> SetupOptionsRead:
    """Return cascaded theory options for dynamic form updates.

    Args:
        track: When set, returns levels for that question bank track.
        level: When set with track, returns categories for that pair.

    Returns:
        JSON with ``tracks``, ``levels``, or ``categories`` keys.

    Raises:
        HTTPException: 404 when the track or level slug is unknown.
    """
    try:
        return theory_options(track, level)
    except UnknownSetupOptionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/coding-options",
    response_model=SetupOptionsRead,
    response_model_exclude_none=True,
)
async def setup_coding_options(
    track: str | None = None,
    level: str | None = None,
) -> SetupOptionsRead:
    """Return cascaded coding options for dynamic form updates.

    Args:
        track: When set, returns levels for that coding track.
        level: When set with track, returns categories for that pair.

    Returns:
        JSON with ``tracks``, ``levels``, or ``categories`` keys.

    Raises:
        HTTPException: 404 when the track or level slug is unknown.
    """
    try:
        return coding_options(track, level)
    except UnknownSetupOptionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/coding-available", response_model=SetupCodingAvailableRead)
async def setup_coding_available() -> SetupCodingAvailableRead:
    """Return whether coding sessions can be started from setup.

    Returns:
        JSON with ``available`` boolean.
    """
    return SetupCodingAvailableRead(available=await is_coding_available())


@router.get("", response_model=SetupPageRead, response_model_exclude_unset=True)
async def setup_page(
    config_service: ConfigServiceDep,
    whisper_model_service: WhisperModelServiceDep,
) -> SetupPageRead:
    """Return the setup page read model for the SPA.

    Args:
        config_service: Provider configuration service.
        whisper_model_service: Whisper model download service.

    Returns:
        Setup page read model, or ``{"configured": False}`` when the provider
        is not configured yet (the SPA redirects to config).
    """
    config = config_service.get_config()
    if config is None:
        return SetupPageRead(configured=False)
    return await build_setup_page(
        config=config,
        whisper_model_service=whisper_model_service,
    )


@router.post("", response_model=SetupCreateResponse, response_model_exclude_unset=True)
async def create_interview(
    body: SetupCreateBody,
    config_service: ConfigServiceDep,
    start_session: StartSetupSessionDep,
) -> SetupCreateResponse:
    """Create an interview session from the setup selection.

    Args:
        body: Parsed setup form submission.
        config_service: Provider configuration service.
        start_session: Setup submission use case.

    Returns:
        JSON with ``redirect`` on success, ``configured: False`` when the
        provider is missing, or ``success=False`` plus an error message.
    """
    config = config_service.get_config()
    if config is None:
        return SetupCreateResponse(
            success=False,
            configured=False,
            redirect="/#/config",
        )

    result = await start_session.execute(
        SetupSessionCommand(
            selection_json=body.selection_json,
            question_count=body.question_count,
            coding_question_count=body.coding_question_count,
            theory_timer_seconds=(
                body.question_time_minutes * 60 if body.enable_question_timer else None
            ),
            coding_timer_seconds=(
                body.coding_time_minutes * 60 if body.enable_coding_timer else None
            ),
            locale=config.locale,
        )
    )
    if result.interview_id is None:
        return SetupCreateResponse(
            success=False,
            error=result.error or "Could not create the interview.",
            min_question_count=result.min_question_count,
            min_coding_task_count=result.min_coding_task_count,
        )
    return SetupCreateResponse(
        success=True,
        redirect=f"/interview/{result.interview_id}",
    )
