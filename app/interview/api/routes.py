# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Interview session endpoints.

This module provides the interview page (HTTP GET). Business logic is
delegated to the service layer; theory transport lives under ``/theory/``.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.interview.api.deps import ActiveSessionPageDep
from app.interview.api.errors import http_exception_from_domain_error
from app.interview.domain.exceptions import InterviewDomainError
from app.platform.api.deps import ConfigServiceDep, SpeechRuntimeDep
from app.question_voice.use_cases.generate_question_audio import GenerateQuestionAudio
from app.shared.infrastructure.gateways.tts_exceptions import (
    QuestionVoiceDisabledError,
    QuestionVoiceSynthesisError,
)
from app.speech.api.deps import WhisperModelServiceDep

router = APIRouter(prefix="/interview", tags=["interview"])

api_router = APIRouter(prefix="/api/interview", tags=["interview"])


@api_router.get("/{interview_id}", response_model=None)
async def interview_page_json(
    interview_id: str,
    config_service: ConfigServiceDep,
    whisper_model_service: WhisperModelServiceDep,
    page_service: ActiveSessionPageDep,
    coordinator: SpeechRuntimeDep,
) -> dict[str, object] | JSONResponse:
    """Return the interview page JSON payload for the SPA.

    Args:
        interview_id: The session UUID.
        config_service: Provider configuration service.
        whisper_model_service: Whisper model download service.
        page_service: Active session page service.
        coordinator: App-lifetime speech runtime coordinator.

    Returns:
        JSON with the full page context, or ``{"redirect": ...}`` for
        sessions that are missing or already completed.
    """
    config, model = config_service.load_active()
    render = await page_service.prepare_page(
        interview_id,
        config=config,
        accepts_audio_input=model is not None and model.accepts_audio_input,
        whisper_model_service=whisper_model_service,
    )
    if render.not_found:
        return JSONResponse(
            {"redirect": "/", "not_found": True},
            status_code=404,
        )
    if render.redirect_url is not None:
        return {"redirect": render.redirect_url}

    await coordinator.preload_whisper_for_active_interview(
        config,
        interview_active=True,
    )
    return render.context or {}


@router.get("/{interview_id}/question-audio")
async def question_audio(
    interview_id: str,
    coordinator: SpeechRuntimeDep,
    answer_id: int | None = None,
) -> FileResponse:
    """Stream WAV audio for the current or specified unanswered question.

    Args:
        interview_id: Interview session UUID.
        coordinator: App-lifetime speech runtime coordinator.
        answer_id: Optional answer row id; defaults to the first unanswered question.

    Returns:
        ``audio/wav`` file from cache or TTS synthesis.

    Raises:
        HTTPException: When voice is disabled, the session is invalid, or TTS fails.
    """
    try:
        path = await GenerateQuestionAudio.execute(
            coordinator.tts, interview_id, answer_id
        )
    except QuestionVoiceDisabledError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QuestionVoiceSynthesisError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except InterviewDomainError as exc:
        raise http_exception_from_domain_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(path, media_type="audio/wav", filename="question.wav")
