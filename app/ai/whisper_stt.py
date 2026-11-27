# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""faster-whisper implementation of :class:`~app.ai.stt.Stt`."""

import asyncio
import logging

from faster_whisper import WhisperModel
import numpy as np
import numpy.typing as npt

from app.shared.locales import normalize_locale

logger = logging.getLogger(__name__)


class WhisperStt:
    """Transcribe audio using an in-memory ``WhisperModel``."""

    def __init__(self, model: WhisperModel) -> None:
        """Wrap a loaded faster-whisper model.

        Args:
            model: Loaded ``WhisperModel`` instance.
        """
        self._model = model

    async def transcribe(
        self,
        audio: npt.NDArray[np.float32],
        locale: str,
    ) -> str:
        """Transcribe mono float32 audio with VAD filtering.

        Args:
            audio: Mono PCM as float32 samples normalized to [-1, 1].
            locale: Interview locale code for the ``language`` parameter.

        Returns:
            Final recognized text (may be empty).
        """
        language = normalize_locale(locale)

        def _transcribe() -> str:
            segments, info = self._model.transcribe(
                audio,
                language=language,
                task="transcribe",
                # Drop silence/noise before decoding: Whisper hallucinates
                # text (random phrases, CJK glyphs) on non-speech audio.
                vad_filter=True,
                # Treat pauses shorter than 0.7 s as part of speech so
                # natural hesitations do not split or clip the answer.
                vad_parameters={"min_silence_duration_ms": 700},
                # Decode each window independently so one hallucinated
                # segment is not fed forward and amplified in the next.
                condition_on_previous_text=False,
            )
            segment_list = list(segments)
            result = "".join((segment.text or "") for segment in segment_list).strip()
            logger.info(
                "Whisper transcript: language=%s segments=%d result=%r",
                getattr(info, "language", language) if info is not None else language,
                len(segment_list),
                result,
            )
            return result

        return await asyncio.to_thread(_transcribe)
