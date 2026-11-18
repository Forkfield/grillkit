# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Interview session page context builder."""

from dataclasses import dataclass
from typing import Any

from app.coding.domain.entities import CodingSection
from app.coding.queries.task_page import build_coding_context
from app.interview.domain.rules.selection import (
    session_display_title,
    session_selection_summary_lines,
)
from app.interview.domain.serialization import parse_session_spec
from app.interview.domain.session_phases import phase_order_for_mode
from app.interview.domain.value_objects import SESSION_MODE_LABELS, SessionSelection
from app.interview.queries.dashboard import InterviewDashboard
from app.interview.queries.projection import (
    SessionSnapshot,
    load_session_snapshot,
)
from app.interview.repositories.uow import InterviewUnitOfWork
from app.interview.schemas.interview import (
    AnswerRead,
    InterviewPageContext,
    InterviewRead,
)
from app.interview.use_cases.advance_phase import (
    activate_current_section,
    active_section,
)
from app.platform.domain.config import AppConfig
from app.question_voice.queries.voice_page import VoicePage
from app.shared.infrastructure.gateways.whisper_model import WhisperModelService
from app.shared.locales import (
    SUPPORTED_LOCALES,
    TIMEOUT_CHAT_LABELS,
    localized_string,
)
from app.speech.queries.speech_page import SttModelPageService
from app.theory.queries.task_page import build_theory_context
from app.theory.schemas.page import TheoryPageContext


@dataclass(frozen=True)
class SessionPageRender:
    """Result of preparing the interview page.

    Exactly one of ``context``, ``redirect_url`` and ``not_found`` is set.

    Attributes:
        context: Page context when the session is active.
        redirect_url: Redirect target for completed sessions.
        not_found: True when the session does not exist.
    """

    context: dict[str, Any] | None = None
    redirect_url: str | None = None
    not_found: bool = False


class ActiveSessionPage:
    """Compose session shell and section contexts for the interview page."""

    def __init__(self, uow: InterviewUnitOfWork) -> None:
        """Initialize with the active unit of work."""
        self._uow: InterviewUnitOfWork = uow

    def load(self, interview_id: str) -> SessionSnapshot | None:
        """Load a session and start the active section timer when applicable.

        Args:
            interview_id: The session UUID.

        Returns:
            Session snapshot, or None when the session does not exist.
        """
        snapshot = load_session_snapshot(self._uow, interview_id)
        if snapshot is None or snapshot.interview.status != "active":
            return snapshot
        return activate_current_section(self._uow, snapshot)

    async def prepare_page(
        self,
        interview_id: str,
        *,
        config: AppConfig | None,
        accepts_audio_input: bool = False,
        whisper_model_service: WhisperModelService | None = None,
    ) -> SessionPageRender:
        """Load a session and build context for the interview page.

        Args:
            interview_id: The session UUID.
            config: Saved provider configuration, if any.
            accepts_audio_input: Whether the configured LLM accepts audio answers.
            whisper_model_service: Whisper model service instance (injectable).

        Returns:
            Page context, a redirect for completed sessions, or ``not_found``.
        """
        snapshot = self.load(interview_id)
        if snapshot is None:
            return SessionPageRender(not_found=True)

        interview = snapshot.interview
        if interview.status == "completed":
            return SessionPageRender(redirect_url=f"/interview/{interview_id}/results")

        return SessionPageRender(
            context=await self.build_context(
                snapshot,
                config=config,
                accepts_audio_input=accepts_audio_input,
                whisper_model_service=whisper_model_service,
            )
        )

    @staticmethod
    def build_page_context(
        interview: InterviewRead,
        *,
        config: AppConfig | None,
        question_voice_enabled: bool,
        theory: TheoryPageContext | None = None,
        coding: CodingSection | None = None,
        session: SessionSelection | None = None,
        interview_model_accepts_audio: bool = False,
    ) -> InterviewPageContext:
        """Assemble the session shell context for the interview SPA.

        Theory-specific fields are mirrored on the shell for the theory panel
        while ``theory`` exposes the structured section context.

        Args:
            interview: Loaded interview read model.
            config: Application config, if configured.
            question_voice_enabled: Whether Piper TTS is enabled in config.
            theory: Optional pre-built theory page context.
            coding: Coding section aggregate for the score fallback.
            session: Parsed selection; parsed from the read model when omitted.
            interview_model_accepts_audio: Whether the configured model accepts audio.

        Returns:
            Frozen page context for the interview SPA.
        """
        if session is None:
            session = parse_session_spec(
                interview.selection_spec,
                question_count=interview.question_count,
                task_time_limit_seconds=interview.question_time_limit_seconds,
            )
        if theory is None:
            theory = build_theory_context(interview, session=session)
        current_question: AnswerRead | None = (
            theory.current_question if theory is not None else None
        )
        overall_feedback_data = interview.overall_feedback
        score_breakdown = (
            overall_feedback_data.get("score_breakdown")
            if overall_feedback_data
            else None
        )
        max_score = InterviewDashboard.compute_max_score(
            interview,
            score_breakdown if isinstance(score_breakdown, dict) else None,
            coding_section=coding,
            session=session,
        )

        return InterviewPageContext(
            interview=interview,
            interview_title=session_display_title(session),
            selection_lines=session_selection_summary_lines(session),
            answers=theory.answers if theory is not None else interview.answers,
            current_question=current_question,
            current_answer_id=current_question.id if current_question else None,
            question_voice_enabled=question_voice_enabled,
            overall_feedback=overall_feedback_data,
            max_score=max_score,
            locale_label=SUPPORTED_LOCALES.get(interview.locale, interview.locale),
            question_timer_enabled=(
                theory.question_timer_enabled if theory is not None else False
            ),
            question_time_limit_seconds=interview.question_time_limit_seconds,
            timer_remaining_seconds=(
                theory.timer_remaining_seconds if theory is not None else None
            ),
            current_round=theory.current_round if theory is not None else 0,
            timeout_chat_label=localized_string(interview.locale, TIMEOUT_CHAT_LABELS),
            llm_request_timeout_seconds=int(config.timeout) if config else 60,
            interview_model_accepts_audio=interview_model_accepts_audio,
        )

    async def build_context(
        self,
        snapshot: SessionSnapshot,
        *,
        config: AppConfig | None,
        accepts_audio_input: bool = False,
        whisper_model_service: WhisperModelService | None = None,
    ) -> dict[str, Any]:
        """Merge session shell, section panels, and audio keys for the SPA.

        Args:
            snapshot: Loaded session with parsed selection and section aggregates.
            config: Application config, if configured.
            accepts_audio_input: Whether the configured LLM accepts audio answers.
            whisper_model_service: Whisper model service instance (injectable).

        Returns:
            Flat dict for SPA rendering.
        """
        theory = build_theory_context(snapshot.interview, session=snapshot.session)
        coding = build_coding_context(snapshot.coding)
        base = ActiveSessionPage.build_page_context(
            snapshot.interview,
            config=config,
            question_voice_enabled=bool(config and config.question_voice_enabled),
            theory=theory,
            coding=snapshot.coding,
            session=snapshot.session,
            interview_model_accepts_audio=accepts_audio_input,
        ).model_dump()
        speech = SttModelPageService.build_page_context(
            config,
            whisper_model_service=whisper_model_service,
        ).model_dump()
        voice = (await VoicePage.build_page_context(config)).model_dump()
        session = snapshot.session
        return {
            **base,
            **speech,
            **voice,
            "theory": theory.model_dump() if theory is not None else None,
            "coding": coding.model_dump() if coding is not None else None,
            "session_mode": session.session_mode,
            "session_mode_label": SESSION_MODE_LABELS.get(
                session.session_mode, session.session_mode
            ),
            "phase_order": list(phase_order_for_mode(session.session_mode)),
            "active_phase": active_section(snapshot),
        }
