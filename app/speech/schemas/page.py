# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Page context for speech model status."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.speech.schemas.status import WhisperModelStatusRead


class SttModelPageContext(BaseModel):
    """Keys shared by config, setup, and interview pages for Whisper status.

    Attributes:
        speech_model_status: Status snapshot for the UI.
        speech_model_banner: Whether to show the install/download banner.
        status: Alias for ``speech_model_status``.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    speech_model_status: WhisperModelStatusRead | None
    speech_model_banner: bool
    status: WhisperModelStatusRead | None = None  # TODO удалить легаси имя
