# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Pydantic models and mappers for the platform feature."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.question_voice.schemas import VoiceStatusRead
from app.shared.locales import DEFAULT_LOCALE
from app.shared.stt_models import (
    DEFAULT_STT_MODEL_SIZE,
    STT_MODEL_BY_SIZE,
    SttModelSpec,
)
from app.speech.schemas.status import WhisperModelStatusRead


class AppConfigRead(BaseModel):
    """Saved provider settings for the configuration UI.

    Attributes:
        provider_type: AI provider adapter id.
        base_url: API endpoint URL.
        model: Model name passed to the provider.
        api_key: API key or mask placeholder when ``mask_secret`` was used.
        timeout: Request timeout in seconds.
        locale: Interview language for AI feedback and voice.
        speech_model_size: Whisper model size for dictation.
        question_voice_enabled: Whether Silero TTS reads questions aloud.
        tts_voice_id: Silero voice id for question audio.
        llm_preset_id: Active catalog model id, if set.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    provider_type: str
    base_url: str
    model: str
    api_key: str | None = None
    timeout: float = 60.0
    locale: str
    speech_model_size: str
    question_voice_enabled: bool = False
    tts_voice_id: str
    llm_preset_id: str | None = None


class LLMPresetOptionRead(BaseModel):
    """One interview model option in the configuration selector.

    Attributes:
        id: Catalog model id.
        display_name: Human-readable label.
        description: Short description shown in the UI.
        model: Provider model name.
        base_url: OpenAI-compatible base URL.
        accepts_audio_input: Whether the model supports audio answer submission.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    id: str
    display_name: str
    description: str
    model: str
    base_url: str
    accepts_audio_input: bool = False


class LLMProviderRead(BaseModel):
    """One provider card on the providers settings tab.

    Attributes:
        id: Catalog provider id.
        display_name: Human-readable label.
        base_url: OpenAI-compatible base URL.
        provider_type: Provider adapter id.
        has_api_key: Whether a key is stored (the key itself is never sent).
        discovery_error: Message from the last failed model discovery, if any.
        models: Models configured under this provider.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    id: str
    display_name: str
    base_url: str
    provider_type: str
    has_api_key: bool = False
    discovery_error: str | None = None
    models: list["LLMModelRead"] = Field(default_factory=list)


class LLMModelRead(BaseModel):
    """One model inside a provider card.

    Attributes:
        id: Catalog model id.
        provider_id: Provider that owns the model.
        display_name: Human-readable label.
        model: Provider model name.
        accepts_audio_input: Whether the model supports audio answers.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    id: str
    provider_id: str
    display_name: str
    model: str
    accepts_audio_input: bool = False


class SpeechModelSpecRead(BaseModel):
    """Whisper model metadata for one size tier on the config page.

    Attributes:
        size: Model size identifier.
        display_name: Human-readable label.
        hf_repo_id: Hugging Face repository id.
        approx_download_mb: Approximate download size in megabytes.
        ram_hint: Suggested RAM for running the model.
        speed_hint: Relative speed expectation.
        quality_hint: Relative transcription quality.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    size: str
    display_name: str
    hf_repo_id: str
    approx_download_mb: int
    ram_hint: str
    speed_hint: str
    quality_hint: str


class ConfigPageContext(BaseModel):
    """Full JSON context for the config page.

    Attributes:
        config: Masked provider settings for the form, if configured.
        locales: Supported interview locale codes and labels.
        speech_model_specs: Whisper size options keyed by size slug.
        speech_model_status: Whisper install/load status snapshot.
        speech_model_banner: Whether to show the speech model banner.
        tts_voice_status: Silero question-voice status snapshot.
        tts_voice_banner: Whether to show the question-voice banner.
        llm_presets: Interview model catalog options.
        llm_providers: Providers with their models for the providers tab.
        selected_llm_preset_id: Active catalog model id.
        error: Optional validation or connection error message.
        message: Optional success or informational message.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    config: AppConfigRead | None
    locales: dict[str, str]
    speech_model_specs: dict[str, SpeechModelSpecRead]
    speech_model_status: WhisperModelStatusRead | None = None
    speech_model_banner: bool = False
    tts_voice_status: VoiceStatusRead | None = None
    tts_voice_banner: bool = False
    llm_presets: list[LLMPresetOptionRead] = Field(default_factory=list)
    llm_providers: list[LLMProviderRead] = Field(default_factory=list)
    selected_llm_preset_id: str | None = None
    error: str | None = None
    message: str | None = None


class NewLLMModel(BaseModel):
    """User input for adding a catalog model.

    The stable catalog id is derived from ``display_name`` when the model is
    persisted, so it is not part of the user-supplied input.

    Attributes:
        display_name: Human-readable label shown in the UI.
        base_url: OpenAI-compatible base URL.
        model: Provider model name.
        api_key: Optional API key stored with the catalog entry.
        accepts_audio_input: Whether the model supports multimodal audio answers.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        str_strip_whitespace=True, frozen=True
    )

    display_name: str
    base_url: str
    model: str
    api_key: str | None = None
    accepts_audio_input: bool = False

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str) -> str:
        if not value:
            raise ValueError("Display name is required")
        return value

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized:
            raise ValueError("Base URL is required")
        return normalized

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str) -> str:
        if not value:
            raise ValueError("Model name is required")
        return value

    @field_validator("api_key", mode="before")
    @classmethod
    def _normalize_api_key(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return str(value).strip() or None


class LLMProviderForm(BaseModel):
    """User input for creating or updating a catalog provider.

    Attributes:
        display_name: Human-readable label shown in the UI.
        base_url: OpenAI-compatible base URL.
        provider_type: Provider adapter id.
        api_key: Replacement API key; empty or ``None`` keeps the stored key.
        clear_api_key: Whether to remove the stored key.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        str_strip_whitespace=True, frozen=True
    )

    display_name: str
    base_url: str
    provider_type: str = "openai-compatible"
    api_key: str | None = None
    clear_api_key: bool = False

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str) -> str:
        if not value:
            raise ValueError("Display name is required")
        return value

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized:
            raise ValueError("Base URL is required")
        return normalized

    @field_validator("provider_type")
    @classmethod
    def _validate_provider_type(cls, value: str) -> str:
        if not value:
            raise ValueError("Provider type is required")
        return value

    @field_validator("api_key", mode="before")
    @classmethod
    def _normalize_api_key(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip() or None
        return str(value).strip() or None


class ModelAudioInputForm(BaseModel):
    """User input for toggling one model's audio-input capability flag.

    Attributes:
        accepts_audio_input: Whether the model supports multimodal audio answers.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    accepts_audio_input: bool = False


class LLMModelForm(BaseModel):
    """User input for adding or updating a model under a provider.

    Attributes:
        display_name: Human-readable label shown in the UI.
        model: Provider model name.
        accepts_audio_input: Whether the model supports multimodal audio answers.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        str_strip_whitespace=True, frozen=True
    )

    display_name: str
    model: str
    accepts_audio_input: bool = False

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str) -> str:
        if not value:
            raise ValueError("Display name is required")
        return value

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str) -> str:
        if not value:
            raise ValueError("Model name is required")
        return value


class SaveConfigBody(BaseModel):
    """JSON body for saving the AI provider configuration.

    Attributes:
        llm_preset_id: Selected catalog model id.
        api_key: API key field value (may be empty or masked placeholder).
        timeout: Request timeout in seconds.
        locale: Interview language code.
        speech_model_size: Whisper model size slug.
        question_voice_enabled: Whether Silero TTS reads questions aloud.
    """

    llm_preset_id: str
    api_key: str = ""
    timeout: float = 60.0
    locale: str = DEFAULT_LOCALE
    speech_model_size: str = DEFAULT_STT_MODEL_SIZE
    question_voice_enabled: bool = False


class ConfigTestResponse(BaseModel):
    """Response for POST /api/config/test.

    Attributes:
        success: Whether the provider connection probe passed.
        message: Result message to show in the UI.
    """

    success: bool
    message: str


class ConfigSaveResponse(BaseModel):
    """Response for POST and DELETE /api/config.

    Attributes:
        success: Whether the operation succeeded.
        message: Result message to show in the UI.
        page: Fresh config page context after the operation.
    """

    success: bool
    message: str
    page: ConfigPageContext


class AddLLMModelResponse(BaseModel):
    """Response for POST /api/config/llm-models.

    Attributes:
        error: Optional validation or connection error message.
        message: Optional success message.
        selected_preset_id: Catalog id to preselect on the config page.
        page: Fresh config page context after the operation.
    """

    error: str | None = None
    message: str | None = None
    selected_preset_id: str | None = None
    page: ConfigPageContext


class CatalogActionResult(BaseModel):
    """Response for provider and model catalog mutations.

    Attributes:
        error: Optional validation or connection error message.
        message: Optional success message.
        page: Fresh config page context after the operation.
    """

    error: str | None = None
    message: str | None = None
    page: ConfigPageContext


class DiscoverModelsResponse(BaseModel):
    """Response for POST /api/config/providers/{id}/discover-models.

    Attributes:
        models: Model ids reported by the provider endpoint.
        error: Optional error message when discovery failed.
    """

    models: list[str] = Field(default_factory=list)
    error: str | None = None


def speech_model_specs_for_config() -> dict[str, SpeechModelSpecRead]:
    """Build speech model spec read models keyed by size for the config page.

    Returns:
        Dict mapping size slug to read model (matches page iteration).
    """
    return {
        size: speech_model_spec_read_from(spec)
        for size, spec in STT_MODEL_BY_SIZE.items()
    }


def speech_model_spec_read_from(spec: SttModelSpec) -> SpeechModelSpecRead:
    """Map a speech model spec to a read model.

    Args:
        spec: Whisper model metadata from speech services.

    Returns:
        Immutable read model.
    """
    return SpeechModelSpecRead(
        size=spec.size,
        display_name=spec.display_name,
        hf_repo_id=spec.hf_repo_id,
        approx_download_mb=spec.approx_download_mb,
        ram_hint=spec.ram_hint,
        speed_hint=spec.speed_hint,
        quality_hint=spec.quality_hint,
    )
