# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Open the interview session page: start the active phase and build context."""

from dataclasses import dataclass
from typing import Any

from app.interview.queries.session_page import ActiveSessionPage
from app.interview.repositories.uow import InterviewUnitOfWork
from app.interview.use_cases.advance_phase import open_session
from app.platform.domain.config import AppConfig
from app.shared.infrastructure.gateways.whisper_model import WhisperModelService


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


class OpenSessionPage:
    """Open a session page, starting the clock of the phase on screen."""

    def __init__(self, uow: InterviewUnitOfWork) -> None:
        """Initialize with the active unit of work.

        Args:
            uow: Unit of work used to persist the started section timer.
        """
        self._uow: InterviewUnitOfWork = uow

    async def prepare_page(
        self,
        interview_id: str,
        *,
        config: AppConfig | None,
        accepts_audio_input: bool = False,
        whisper_model_service: WhisperModelService | None = None,
    ) -> SessionPageRender:
        """Open a session page and build its context.

        Args:
            interview_id: The session UUID.
            config: Saved provider configuration, if any.
            accepts_audio_input: Whether the configured LLM accepts audio answers.
            whisper_model_service: Whisper model service instance (injectable).

        Returns:
            Page context, a redirect for completed sessions, or ``not_found``.
        """
        snapshot = open_session(self._uow, interview_id)
        if snapshot is None:
            return SessionPageRender(not_found=True)

        interview = snapshot.interview
        if interview.status == "completed":
            return SessionPageRender(redirect_url=f"/interview/{interview_id}/results")

        context = await ActiveSessionPage.build_context(
            snapshot,
            config=config,
            accepts_audio_input=accepts_audio_input,
            whisper_model_service=whisper_model_service,
        )
        return SessionPageRender(context=context)
