# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Skip-question tests for theory sessions."""

from app.interview.queries.loader import InterviewLoader
from app.shared.infrastructure.models import Answer, Interview
from app.shared.locales import SKIP_FEEDBACK_MESSAGES
from app.theory.domain.entities import TheoryTask
from tests.helpers.interview_seed import persist_interview_with_answers
from tests.helpers.selection import minimal_selection_spec


def _seed(interview_id: str, answers: list[Answer], *, locale: str = "en") -> str:
    """Persist an active theory interview with the given task rows."""
    return persist_interview_with_answers(
        Interview(
            id=interview_id,
            locale=locale,
            selection_spec=minimal_selection_spec(categories=["basics"]),
            status="active",
        ),
        answers,
        question_count=len({answer.question_id for answer in answers}),
        task_time_limit_seconds=None,
    )


class TestTheorySkip:
    """Skipping the open theory round."""

    def test_skip_scores_zero_and_advances_without_ai(
        self, client, isolated_db, override_ws_ai_provider
    ):
        """Skip → score 0, skip marker, next question; the AI is never called."""
        interview_id = _seed(
            "skip-theory-1",
            [
                Answer(question_id="q1", order=1, round=0, question_text="Q1?"),
                Answer(question_id="q2", order=2, round=0, question_text="Q2?"),
            ],
            locale="ru",
        )
        override_ws_ai_provider(client, [])

        with client.websocket_connect(f"/interview/{interview_id}/theory/ws") as ws:
            ws.send_json({"type": "skip", "question_id": "q1"})
            feedback = ws.receive_json()

        assert feedback["type"] == "feedback"
        assert feedback["skipped"] is True
        assert feedback["timed_out"] is False
        assert feedback["feedback"] == SKIP_FEEDBACK_MESSAGES["ru"]
        assert feedback["follow_up_question"] is None
        assert feedback["next_question"]["question_id"] == "q2"

        reloaded = InterviewLoader.load(interview_id)
        assert reloaded is not None
        q1 = next(a for a in reloaded.answers if a.question_id == "q1")
        assert q1.answer_text == TheoryTask.SKIPPED_ANSWER_TEXT
        assert q1.score == 0
        assert q1.feedback == SKIP_FEEDBACK_MESSAGES["ru"]

    def test_skip_last_question_finishes_theory(
        self, client, isolated_db, override_ws_ai_provider
    ):
        """Skipping the only question leaves no next question."""
        interview_id = _seed(
            "skip-theory-2",
            [Answer(question_id="q1", order=1, round=0, question_text="Q1?")],
        )
        override_ws_ai_provider(client, [])

        with client.websocket_connect(f"/interview/{interview_id}/theory/ws") as ws:
            ws.send_json({"type": "skip", "question_id": "q1"})
            feedback = ws.receive_json()

        assert feedback["skipped"] is True
        assert feedback["next_question"] is None

    def test_skip_follow_up_moves_to_next_question(
        self, client, isolated_db, override_ws_ai_provider
    ):
        """Skipping an open follow-up round closes it and opens the next question."""
        interview_id = _seed(
            "skip-theory-3",
            [
                Answer(
                    question_id="q1",
                    order=1,
                    round=0,
                    question_text="Q1?",
                    answer_text="First answer",
                    score=5,
                ),
                Answer(question_id="q1", order=1, round=1, question_text="Why?"),
                Answer(question_id="q2", order=2, round=0, question_text="Q2?"),
            ],
        )
        override_ws_ai_provider(client, [])

        with client.websocket_connect(f"/interview/{interview_id}/theory/ws") as ws:
            ws.send_json({"type": "skip", "question_id": "q1"})
            feedback = ws.receive_json()

        assert feedback["round"] == 1
        assert feedback["next_question"]["question_id"] == "q2"

        reloaded = InterviewLoader.load(interview_id)
        assert reloaded is not None
        initial = next(
            a for a in reloaded.answers if a.question_id == "q1" and a.round == 0
        )
        follow_up = next(
            a for a in reloaded.answers if a.question_id == "q1" and a.round == 1
        )
        assert initial.answer_text == "First answer"
        assert initial.score == 5
        assert follow_up.answer_text == TheoryTask.SKIPPED_ANSWER_TEXT
        assert follow_up.score == 0

    def test_skip_requires_question_id(
        self, client, isolated_db, override_ws_ai_provider
    ):
        """A skip message without question_id is rejected."""
        interview_id = _seed(
            "skip-theory-4",
            [Answer(question_id="q1", order=1, round=0, question_text="Q1?")],
        )
        override_ws_ai_provider(client, [])

        with client.websocket_connect(f"/interview/{interview_id}/theory/ws") as ws:
            ws.send_json({"type": "skip"})
            err = ws.receive_json()

        assert err["type"] == "error"

    def test_skip_answered_question_is_rejected(
        self, client, isolated_db, override_ws_ai_provider
    ):
        """A question without an open round cannot be skipped."""
        interview_id = _seed(
            "skip-theory-5",
            [
                Answer(
                    question_id="q1",
                    order=1,
                    round=0,
                    question_text="Q1?",
                    answer_text="Done",
                    score=7,
                ),
                Answer(question_id="q2", order=2, round=0, question_text="Q2?"),
            ],
        )
        override_ws_ai_provider(client, [])

        with client.websocket_connect(f"/interview/{interview_id}/theory/ws") as ws:
            ws.send_json({"type": "skip", "question_id": "q1"})
            err = ws.receive_json()

        assert err["type"] == "error"
        reloaded = InterviewLoader.load(interview_id)
        assert reloaded is not None
        q1 = next(a for a in reloaded.answers if a.question_id == "q1")
        assert q1.answer_text == "Done"
        assert q1.score == 7
