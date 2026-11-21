# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""WebSocket endpoint for interview answer dictation."""

import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ai.stt import Stt
from app.interview.queries.loader import InterviewLoader
from app.interview.schemas.interview import InterviewRead
from app.platform.domain.speech_runtime import SpeechRuntimeCoordinator
from app.speech.api.dictation_protocol import (
    DICTATION_CLIENT_START,
    DICTATION_CLIENT_STOP,
    DICTATION_SERVER_ERROR,
    DICTATION_SERVER_FINAL,
    DICTATION_SERVER_READY,
    dictation_message,
)
from app.speech.domain.stt_resolver import (
    resolve_stt,
    stt_unavailable_message,
)
from app.speech.use_cases.dictation import DictationSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interview", tags=["interview"])


async def _reject_dictation(websocket: WebSocket, message: str) -> None:
    """Accept, send an error JSON message, and close the dictation WebSocket.

    Args:
        websocket: Connection to close.
        message: User-facing error text.
    """
    await websocket.accept()
    await websocket.send_json(
        dictation_message(DICTATION_SERVER_ERROR, message=message)
    )
    await websocket.close(code=1008, reason=message[:120])


async def _handle_stop(
    websocket: WebSocket,
    stt: Stt,
    interview: InterviewRead,
    session: DictationSession | None,
) -> tuple[DictationSession | None, bool]:
    """Finalize the dictation session and send the transcript.

    Args:
        websocket: Dictation WebSocket connection.
        stt: Speech-to-text backend.
        interview: Interview the dictation belongs to.
        session: Active session, or ``None`` if ``start`` was not sent.

    Returns:
        Tuple of (session, done) where ``done`` closes the connection.
    """
    if session is None:
        await websocket.send_json(
            dictation_message(
                DICTATION_SERVER_ERROR,
                message="Send start before stop",
            )
        )
        return None, False
    final_text = await session.finalize(stt, interview.locale)
    await websocket.send_json(
        dictation_message(
            DICTATION_SERVER_FINAL,
            text=final_text,
        )
    )
    return session, True


async def _handle_text_message(
    websocket: WebSocket,
    stt: Stt,
    interview: InterviewRead,
    incoming_text: str,
    session: DictationSession | None,
) -> tuple[DictationSession | None, bool]:
    """Process one text JSON message from the client.

    Args:
        websocket: Dictation WebSocket connection.
        stt: Speech-to-text backend.
        interview: Interview the dictation belongs to.
        incoming_text: Raw JSON text frame.
        session: Active session, or ``None`` before ``start``.

    Returns:
        Tuple of (updated session, done) where ``done`` closes the connection.
    """
    try:
        payload = json.loads(incoming_text)
    except json.JSONDecodeError:
        await websocket.send_json(
            dictation_message(
                DICTATION_SERVER_ERROR,
                message="Invalid JSON message",
            )
        )
        return session, False

    msg_type = payload.get("type")
    if msg_type == DICTATION_CLIENT_START:
        await websocket.send_json(dictation_message(DICTATION_SERVER_READY))
        return DictationSession(), False
    if msg_type == DICTATION_CLIENT_STOP:
        return await _handle_stop(websocket, stt, interview, session)
    await websocket.send_json(
        dictation_message(
            DICTATION_SERVER_ERROR,
            message=f"Unknown message type: {msg_type}",
        )
    )
    return session, False


async def _handle_audio_chunk(
    websocket: WebSocket,
    session: DictationSession | None,
    chunk: bytes,
) -> DictationSession | None:
    """Append one PCM chunk to the active session.

    Args:
        websocket: Dictation WebSocket connection.
        session: Active session, or ``None`` before ``start``.
        chunk: Raw 16-bit LE mono PCM bytes.

    Returns:
        The (unchanged) session after appending, or ``None`` on protocol error.
    """
    if session is None:
        await websocket.send_json(
            dictation_message(
                DICTATION_SERVER_ERROR,
                message="Send start before audio chunks",
            )
        )
        return None
    session.append_pcm(chunk)
    return session


@router.websocket("/{interview_id}/dictation")
async def interview_dictation_ws(
    websocket: WebSocket,
    interview_id: str,
) -> None:
    """Stream PCM audio and return a final transcript for the answer field.

    Separate from ``/{interview_id}/ws`` (answers and AI evaluation).

    **Client → server (text JSON):**
    - ``{"type":"start"}`` — begin a new dictation session
    - ``{"type":"stop"}`` — finalize and close

    **Client → server (binary):** 16-bit LE mono PCM, 16 kHz

    **Server → client:**
    - ``{"type":"ready"}`` — session initialized
    - ``{"type":"final","text":"..."}`` — final transcript (after ``stop``)
    - ``{"type":"error","message":"..."}`` — failure; connection closes

    Args:
        websocket: Dictation WebSocket connection.
        interview_id: Interview session UUID.
    """
    coordinator: SpeechRuntimeCoordinator = websocket.app.state.speech_runtime
    interview = InterviewLoader.load(interview_id)
    if interview is None:
        await _reject_dictation(websocket, "Interview not found")
        return

    if interview.status != "active":
        await _reject_dictation(websocket, "Interview is not active")
        return

    stt = await resolve_stt(coordinator)
    if stt is None:
        await _reject_dictation(
            websocket,
            stt_unavailable_message(coordinator),
        )
        return

    await websocket.accept()
    session: DictationSession | None = None

    try:
        while True:
            incoming = await websocket.receive()
            if incoming.get("type") == "websocket.disconnect":
                break

            if "text" in incoming:
                session, done = await _handle_text_message(
                    websocket, stt, interview, incoming["text"], session
                )
                if done:
                    break
                continue

            if "bytes" in incoming:
                session = await _handle_audio_chunk(
                    websocket, session, incoming["bytes"]
                )
    except WebSocketDisconnect:
        logger.debug("Dictation WebSocket disconnected for session %s", interview_id)
    except Exception as exc:
        logger.exception("Dictation failed for session %s", interview_id)
        with contextlib.suppress(Exception):
            await websocket.send_json(
                dictation_message(
                    DICTATION_SERVER_ERROR,
                    message=f"Dictation failed: {exc}",
                )
            )
