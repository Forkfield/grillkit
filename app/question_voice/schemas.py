from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

TtsVoiceState = Literal["missing", "ready", "downloading", "error"]


class VoiceStatusRead(BaseModel):
    """Runtime status of a TTS voice for one locale.

    Attributes:
        voice_id: Silero voice identifier from provider configuration.
        locale: Interview locale used for status messaging.
        locale_label: Display name for the locale.
        state: Installation or download state.
        percent: Download progress 0–100 when ``state`` is ``downloading``.
        message: User-facing status or error text.
        voice_display_name: Silero voice label for UI.
        loaded_in_memory: True when the voice is loaded in this process.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    voice_id: str
    locale: str
    locale_label: str
    state: TtsVoiceState
    percent: int
    message: str
    voice_display_name: str
    loaded_in_memory: bool = False


class QuestionVoicePageContext(BaseModel):
    """Keys for config and interview pages for Silero question voice.

    Attributes:
        tts_voice_status: Status snapshot for banners and partials.
        tts_voice_banner: Whether to show the install/load banner.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    tts_voice_status: VoiceStatusRead | None
    tts_voice_banner: bool
