# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Configuration service module.

This module provides service layer for managing application settings
stored in data/config.json and LLM selection via data/llm_models.json.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.ai.audio_probe import minimal_wav_bytes
from app.ai.base import AIProvider, AudioCapableProvider
from app.ai.factory import ProviderFactory
from app.ai.llm_models import LLMModelEntry
from app.platform.domain.effective_config import EffectiveModelConfig
from app.platform.domain.llm_catalog import LLMCatalogService
from app.shared.locales import DEFAULT_LOCALE
from app.shared.stt_models import DEFAULT_STT_MODEL_SIZE
from app.shared.tts_voices import DEFAULT_TTS_VOICE_ID, default_voice_for_locale

MASKED_API_KEY_PLACEHOLDER = "***"
CLEAR_API_KEY_MARKER = "__clear__"


class ApiKeyKind(StrEnum):
    """State of an API key after saving a config form."""

    KEEP = "keep"  # leave the stored catalog key untouched
    SET = "set"  # replace the stored catalog key with a submitted value
    CLEAR = "clear"  # remove the stored catalog key


@dataclass(frozen=True)
class ApiKeyDecision:
    """How the submitted API-key field should affect the stored catalog key.

    Attributes:
        kind: Whether to keep, set, or clear the stored key.
        value: Effective key for provider/test use; meaningful for ``KEEP``
            (existing key) and ``SET`` (submitted value), ``None`` for ``CLEAR``.
    """

    kind: ApiKeyKind
    value: str | None = None


def resolve_api_key_from_form(
    submitted: str,
    entry: LLMModelEntry | None,
) -> ApiKeyDecision:
    """Resolve the API key given a submitted form value into a decision.

    Domain rule for how a raw ``api_key`` form value affects the key persisted
    on the selected catalog model:

    - an explicit clear marker (:data:`CLEAR_API_KEY_MARKER`) removes the stored
      key (:attr:`ApiKeyKind.CLEAR`);
    - any other non-empty value that is not the display mask
      (:data:`MASKED_API_KEY_PLACEHOLDER`) replaces the stored key
      (:attr:`ApiKeyKind.SET`);
    - an empty value or the display mask keeps the stored catalog key
      (:attr:`ApiKeyKind.KEEP`), carrying the existing key (or ``None``) as
      ``value`` for provider/test use.

    Args:
        submitted: Raw ``api_key`` form value (may be empty, masked, or the
            clear marker).
        entry: The selected catalog entry, used to look up a stored key when
            ``submitted`` is empty or masked.

    Returns:
        The API key decision for this form submission.
    """
    value = submitted.strip()
    if value == CLEAR_API_KEY_MARKER:
        return ApiKeyDecision(ApiKeyKind.CLEAR)
    if value and value != MASKED_API_KEY_PLACEHOLDER:
        return ApiKeyDecision(ApiKeyKind.SET, value)
    if entry and entry.api_key:
        return ApiKeyDecision(ApiKeyKind.KEEP, entry.api_key)
    return ApiKeyDecision(ApiKeyKind.KEEP)


@dataclass
class AppConfig:
    """Application settings plus a reference to the active catalog model.

    LLM provider details (:class:`EffectiveModelConfig`) are derived from the
    selected catalog entry and are never stored on ``AppConfig`` directly.

    Attributes:
        timeout: Request timeout in seconds.
        locale: Interview language for AI feedback and voice input.
        speech_model_size: Whisper model size for offline dictation.
        question_voice_enabled: Read interview questions aloud when TTS is available.
        tts_voice_id: Piper voice id for question audio synthesis.
        llm_preset_id: Active catalog model id from ``llm_models.json``.
    """

    timeout: float = 60.0
    locale: str = DEFAULT_LOCALE
    speech_model_size: str = DEFAULT_STT_MODEL_SIZE
    question_voice_enabled: bool = False
    tts_voice_id: str = DEFAULT_TTS_VOICE_ID
    llm_preset_id: str | None = None


def resolve_tts_voice_id(
    existing: AppConfig | None,
    normalized_locale: str,
) -> str:
    """Choose the effective TTS voice for a config save.

    Domain rule: if a config already exists for the same (already-normalized)
    locale, keep the user-selected voice; otherwise fall back to the default
    voice for the new locale. Preserving the user's voice across unrelated
    saves is intentional.

    Args:
        existing: Previously persisted config, if any.
        normalized_locale: The submitted locale, already normalized.

    Returns:
        The TTS voice id to persist.
    """
    if existing is not None and existing.locale == normalized_locale:
        return existing.tts_voice_id
    return default_voice_for_locale(normalized_locale)


def provider_config_changed(
    previous: EffectiveModelConfig | None,
    proposed: EffectiveModelConfig,
) -> bool:
    """Return True when a save requires a fresh live provider probe.

    The provider endpoint only needs re-testing when fields that affect
    connectivity changed (provider type, base URL, model, API key), or when
    nothing is saved yet. Purely cosmetic changes (locale, speech model size,
    TTS voice) do not warrant a network round-trip.

    Args:
        previous: Effective provider settings of the currently saved state, or
            ``None`` when no config is saved yet.
        proposed: Effective provider settings being saved.

    Returns:
        True to probe the provider endpoint before persisting; otherwise False.
    """
    if previous is None:
        return True
    return (
        previous.provider_type != proposed.provider_type
        or previous.base_url != proposed.base_url
        or previous.model != proposed.model
        or previous.api_key != proposed.api_key
    )


class ConfigRepositoryProtocol(Protocol):
    """Port for reading and persisting application configuration.

    The concrete implementation lives in the infrastructure layer and is
    injected into :class:`ConfigService`, so the domain never depends on a
    specific filesystem repository.
    """

    def exists(self) -> bool: ...

    def load(self) -> AppConfig | None: ...

    def save(self, config: AppConfig) -> None: ...

    def delete(self) -> None: ...


class ConfigService:
    """Service for managing provider configuration.

    The service depends only on :class:`ConfigRepositoryProtocol` (a domain
    port); the concrete repository is injected by the composition root.
    """

    def __init__(
        self,
        repo: ConfigRepositoryProtocol,
        catalog_service: LLMCatalogService,
    ) -> None:
        """Initialize the service with its config repository and catalog service.

        Args:
            repo: Config repository (port) used for ``config.json`` I/O.
            catalog_service: LLM catalog service for ``llm_models.json`` lookups.
        """
        self._repo = repo
        self._catalog_service = catalog_service

    def load_active(self) -> tuple[AppConfig | None, LLMModelEntry | None]:
        """Load the saved configuration and the active catalog entry once.

        ``get_config()`` needs the catalog only to fill ``llm_preset_id``; page
        builders also need the entry's audio capability. Returning both from a
        single catalog read avoids re-reading ``llm_models.json`` per lookup.

        Returns:
            Configuration and selected catalog entry, or ``(None, None)`` when
            no configuration file is saved.
        """
        config = self._repo.load()
        if config is None:
            return None, None
        selected = self._catalog_service.get_selected_model()
        if selected is None:
            return config, None
        config.llm_preset_id = selected.id
        return config, selected

    def get_config(self) -> AppConfig | None:
        """Load configuration from disk via the config repository.

        Returns:
            AppConfig with shared settings and the active model id, or None.
        """
        config, _ = self.load_active()
        return config

    def resolve_effective_config(self, config: AppConfig) -> EffectiveModelConfig:
        """Resolve the selected catalog entry into an effective provider config.

        Args:
            config: Stored or submitted provider configuration.

        Returns:
            Aggregate of provider fields and request timeout.

        Raises:
            ValueError: When no interview model is selected.
        """
        entry = self._catalog_service.get_model(config.llm_preset_id)
        if entry is None:
            raise ValueError("No interview model selected")
        return EffectiveModelConfig.from_entry(entry, timeout=config.timeout)

    def save_config(
        self, config: AppConfig, api_key_decision: ApiKeyDecision | None = None
    ) -> None:
        """Save application settings and LLM selection.

        Args:
            config: Configuration to save.
            api_key_decision: How to update the stored catalog key. ``None`` or
                :attr:`ApiKeyKind.KEEP` leaves the stored key untouched;
                :attr:`ApiKeyKind.SET` stores ``value``; :attr:`ApiKeyKind.CLEAR`
                removes the stored key.
        """
        if config.llm_preset_id:
            if api_key_decision is None or api_key_decision.kind is ApiKeyKind.KEEP:
                self._catalog_service.set_selected_model(config.llm_preset_id)
            else:
                api_key = (
                    api_key_decision.value
                    if api_key_decision.kind is ApiKeyKind.SET
                    else None
                )
                self._catalog_service.save_model_selection(config.llm_preset_id, api_key)
        self._repo.save(config)

    def delete_config(self) -> None:
        """Remove configuration file via the config repository."""
        self._repo.delete()

    async def test_model(self, probe: EffectiveModelConfig) -> tuple[bool, str]:
        """Probe a model's provider connection in a single pass.

        Runs the text/provider validation and, when the model supports audio input
        (``probe.accepts_audio_input``), the audio probe — reusing one provider
        instance and one error/cleanup path (no nested test calls).

        Args:
            probe: Effective provider settings, carrying the model's
                audio-input capability flag.

        Returns:
            Tuple of (success: bool, message: str).
        """
        provider: AIProvider | None = None
        try:
            provider = self._provider_from_effective(probe)
            is_valid = await provider.validate()
            if not is_valid:
                return False, "Invalid API key or unreachable endpoint"
            if not probe.accepts_audio_input:
                return True, "Connection successful"
            if not isinstance(provider, AudioCapableProvider):
                return False, "Provider does not support audio input."
            audio_ok = await provider.probe_audio_input(minimal_wav_bytes())
            if audio_ok:
                return True, "Audio connection successful"
            return False, (
                "Model does not accept audio input or rejected the audio probe."
            )
        except ValueError as exc:
            return False, str(exc)
        except Exception as exc:
            return False, f"Connection failed: {exc}"
        finally:
            if provider is not None:
                await provider.close()

    def create_provider_from_config(self) -> AIProvider:
        """Create AI provider from saved configuration.

        Returns:
            Configured AI provider instance.

        Raises:
            ValueError: If no configuration exists.
        """
        config = self.get_config()
        if not config:
            raise ValueError("No configuration found")
        effective = self.resolve_effective_config(config)
        return self._provider_from_effective(effective)

    def _provider_from_effective(self, probe: EffectiveModelConfig) -> AIProvider:
        """Create an AI provider from an effective model config.

        Args:
            probe: Aggregate of provider fields and timeout.

        Returns:
            Configured AI provider instance.
        """
        return ProviderFactory.from_effective(probe)
