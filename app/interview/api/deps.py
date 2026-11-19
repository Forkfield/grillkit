# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""FastAPI dependencies for interview feature API handlers."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException

from app.ai.base import AIProvider
from app.ai.stt import Stt
from app.coding.queries.loader import CodingTaskLoader
from app.coding.queries.review_page import CodingReviewPage
from app.coding.use_cases.create_section import CreateCodingSection
from app.coding.use_cases.submit_solution import SubmitCodingSolution
from app.interview.queries.dashboard import InterviewDashboard
from app.interview.queries.loader import InterviewLoader
from app.interview.queries.results_page import CompletedSessionResults
from app.interview.use_cases.complete_session import CompleteInterviewSession
from app.interview.use_cases.create_session import CreateInterviewSession
from app.interview.use_cases.session_page import OpenSessionPage
from app.platform.api.deps import SpeechRuntimeDep
from app.shared.application.uow_deps import UoWAutoCommitDep, UoWDep
from app.shared.infrastructure.gateways.ai_context import ai_provider_from_config
from app.speech.domain.stt_resolver import (
    resolve_stt,
    stt_unavailable_message,
)
from app.theory.queries.review_page import TheoryReviewPage
from app.theory.use_cases.create_section import CreateTheorySection
from app.theory.use_cases.submit_answer import SubmitTheoryAnswer


async def get_ai_provider() -> AsyncIterator[AIProvider]:
    """Yield a configured AI provider for the lifetime of a request or WebSocket.

    Yields:
        Configured AIProvider instance.

    Raises:
        ValueError: If provider configuration is missing.
    """
    async with ai_provider_from_config() as provider:
        yield provider


def get_interview_query(uow: UoWDep) -> InterviewLoader:
    """Build an interview query service bound to the request unit of work."""
    return InterviewLoader(uow)


def get_dashboard_builder(uow: UoWDep) -> InterviewDashboard:
    """Build a dashboard builder bound to the request UoW."""
    return InterviewDashboard(uow)


def get_open_session_page(uow: UoWAutoCommitDep) -> OpenSessionPage:
    """Build the open-session-page use case bound to an auto-commit UoW."""
    return OpenSessionPage(uow)


def get_create_theory_section(
    uow: UoWAutoCommitDep,
) -> CreateTheorySection:
    """Build a theory section creation use case."""
    return CreateTheorySection(uow)


def get_create_coding_section(
    uow: UoWAutoCommitDep,
) -> CreateCodingSection:
    """Build a coding section creation use case."""
    return CreateCodingSection(uow)


def get_session_creation_service(
    uow: UoWAutoCommitDep,
    create_theory: Annotated[CreateTheorySection, Depends(get_create_theory_section)],
    create_coding: Annotated[CreateCodingSection, Depends(get_create_coding_section)],
) -> CreateInterviewSession:
    """Build a session creation use case composed from section creators.

    Args:
        uow: Application unit of work for the request scope.
        create_theory: Theory section creation use case.
        create_coding: Coding section creation use case.

    Returns:
        Composed ``CreateInterviewSession`` use case instance.
    """
    return CreateInterviewSession(
        uow,
        create_theory_section=create_theory,
        create_coding_section=create_coding,
    )


def get_session_completion_service(
    uow: UoWDep,
) -> CompleteInterviewSession:
    """Build a session completion use case bound to the request UoW."""
    return CompleteInterviewSession(uow)


def get_theory_submission_service(uow: UoWDep) -> SubmitTheoryAnswer:
    """Build a theory submission service bound to the request UoW.

    Args:
        uow: Application unit of work for the request scope.

    Returns:
        Theory submission service instance.
    """
    return SubmitTheoryAnswer(uow)


def get_coding_submission_service(uow: UoWDep) -> SubmitCodingSolution:
    """Build a coding submission service bound to the request UoW.

    Args:
        uow: Application unit of work for the request scope.

    Returns:
        Coding submission service instance.
    """
    return SubmitCodingSolution(uow)


def get_coding_state_service(uow: UoWDep) -> CodingTaskLoader:
    """Build a coding state service bound to the request UoW."""
    return CodingTaskLoader(uow)


def get_session_results_page_service(
    uow: UoWDep,
) -> CompletedSessionResults:
    """Build a session results page query bound to the request UoW."""
    return CompletedSessionResults(uow)


def get_theory_review_service(uow: UoWDep) -> TheoryReviewPage:
    """Build a theory review service bound to the request UoW.

    Args:
        uow: Application unit of work for the request scope.

    Returns:
        Theory review service instance.
    """
    return TheoryReviewPage(uow)


def get_coding_review_service(uow: UoWDep) -> CodingReviewPage:
    """Build a coding review service bound to the request UoW.

    Args:
        uow: Application unit of work for the request scope.

    Returns:
        Coding review service instance.
    """
    return CodingReviewPage(uow)


InterviewLoaderDep = Annotated[InterviewLoader, Depends(get_interview_query)]
InterviewDashboardDep = Annotated[InterviewDashboard, Depends(get_dashboard_builder)]
OpenSessionPageDep = Annotated[
    OpenSessionPage,
    Depends(get_open_session_page),
]
CreateSessionDep = Annotated[
    CreateInterviewSession,
    Depends(get_session_creation_service),
]
CompleteSessionDep = Annotated[
    CompleteInterviewSession,
    Depends(get_session_completion_service),
]
SubmitTheoryAnswerDep = Annotated[
    SubmitTheoryAnswer,
    Depends(get_theory_submission_service),
]
SubmitCodingSolutionDep = Annotated[
    SubmitCodingSolution,
    Depends(get_coding_submission_service),
]
CodingTaskLoaderDep = Annotated[
    CodingTaskLoader,
    Depends(get_coding_state_service),
]
CreateTheorySectionDep = Annotated[
    CreateTheorySection,
    Depends(get_create_theory_section),
]
CreateCodingSectionDep = Annotated[
    CreateCodingSection,
    Depends(get_create_coding_section),
]
CompletedSessionResultsDep = Annotated[
    CompletedSessionResults,
    Depends(get_session_results_page_service),
]
TheoryReviewPageDep = Annotated[
    TheoryReviewPage,
    Depends(get_theory_review_service),
]
CodingReviewPageDep = Annotated[
    CodingReviewPage,
    Depends(get_coding_review_service),
]
AIProviderDep = Annotated[AIProvider, Depends(get_ai_provider)]


async def get_stt(
    coordinator: SpeechRuntimeDep,
) -> Stt:
    """Resolve a loaded STT engine through the speech runtime.

    Args:
        coordinator: App-lifetime speech runtime coordinator.

    Returns:
        Loaded STT engine.

    Raises:
        HTTPException: When a speech model is not installed or loaded.
    """
    stt = await resolve_stt(coordinator)
    if stt is None:
        raise HTTPException(
            status_code=503,
            detail=stt_unavailable_message(coordinator),
        )
    return stt


SttDep = Annotated[Stt, Depends(get_stt)]
