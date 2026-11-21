# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Use case for saving application configuration and syncing speech runtimes."""

from __future__ import annotations

from app.ai.llm_models import LLMCatalog, normalize_model_id
from app.platform.domain.config import (
    ApiKeyDecision,
    ApiKeyKind,
    AppConfig,
    ConfigService,
    provider_config_changed,
    resolve_api_key_from_form,
    resolve_tts_voice_id,
)
from app.platform.domain.effective_config import EffectiveModelConfig
from app.platform.domain.llm_catalog import LLMCatalogService
from app.platform.domain.speech_runtime import SpeechRuntimeCoordinator
from app.platform.queries.platform_page import build_page_context
from app.platform.schemas import (
    ConfigSaveResponse,
    ConfigTestResponse,
    SaveConfigBody,
)
from app.question_voice.queries.voice_status import VoiceStatus
from app.shared.infrastructure.gateways.whisper_model import WhisperModelService
from app.shared.locales import normalize_locale
from app.shared.stt_models import normalize_stt_model_size


def _fallback_config(body: SaveConfigBody, existing: AppConfig | None) -> AppConfig:
    """Build a page-ready config when normalization fails.

    The submitted ``locale``/``speech_model_size`` may be unsupported, so the
    fallback is constructed from the raw form values without re-normalizing
    (normalization already failed and would raise again). Prefers the persisted
    config when present, mirroring the previous behaviour.

    Args:
        body: Submitted config form values.
        existing: Previously persisted config, if any.

    Returns:
        A config used only to render the error page.
    """
    if existing is not None:
        return existing
    return AppConfig(
        timeout=body.timeout,
        locale=body.locale,
        speech_model_size=body.speech_model_size,
        question_voice_enabled=body.question_voice_enabled,
    )


class SaveConfigUseCase:
    """Validate, persist and build the config response for the save flow.

    Owns the whole ``save_config`` path: parsing and testing the submitted
    form, persisting the config (always, even when a speech model fails to
    load), reloading the speech runtimes, and assembling the pydantic response
    (including the fresh config page context). The HTTP handler only passes the
    form body and returns the response.
    """

    def __init__(
        self,
        config_service: ConfigService,
        catalog_service: LLMCatalogService,
        coordinator: SpeechRuntimeCoordinator,
        whisper_model_service: WhisperModelService,
        voice_status_service: type[VoiceStatus],
    ) -> None:
        self._config_service: ConfigService = config_service
        self._catalog_service: LLMCatalogService = catalog_service
        self._coordinator: SpeechRuntimeCoordinator = coordinator
        self._whisper_model_service: WhisperModelService = whisper_model_service
        self._voice_status_service: type[VoiceStatus] = voice_status_service

    async def execute(self, body: SaveConfigBody) -> ConfigSaveResponse:
        """Parse, test, persist and respond for the save endpoint.

        Args:
            body: Submitted config form values.

        Returns:
            Pydantic response with the success flag, a message, and the fresh
            config page context (built from the submitted values). A failed
            write is reported as ``success=False`` built from the submitted
            form rather than propagating as an unhandled error (S13/S14).
        """
        config, decision, success, message = await self._parse_and_test(
            body, force_test=False
        )
        if not success:
            page = await build_page_context(
                config=config,
                whisper_model_service=self._whisper_model_service,
                voice_status_service=self._voice_status_service,
                error=message,
                mask_secret=False,
            )
            return ConfigSaveResponse(success=False, message=message, page=page)

        try:
            self._config_service.save_config(config, decision)
        except (OSError, ValueError) as exc:
            # The write failed (e.g. permission error or a corrupt value), so the
            # save did not happen. Surface a graceful failure built from the
            # submitted form values, mirroring the error branch above (S13/S14).
            page = await build_page_context(
                config=config,
                whisper_model_service=self._whisper_model_service,
                voice_status_service=self._voice_status_service,
                error=str(exc),
                mask_secret=False,
            )
            return ConfigSaveResponse(success=False, message=str(exc), page=page)

        speech_errors = await self._coordinator.reload_after_config_save(config)
        if speech_errors:
            warning = (
                "Configuration saved, but a speech model failed to load: "
                + " | ".join(speech_errors)
            )
            page = await build_page_context(
                config=config,
                whisper_model_service=self._whisper_model_service,
                voice_status_service=self._voice_status_service,
                message=warning,
            )
            return ConfigSaveResponse(success=True, message=warning, page=page)

        message = "Configuration saved successfully"
        page = await build_page_context(
            config=config,
            whisper_model_service=self._whisper_model_service,
            voice_status_service=self._voice_status_service,
            message=message,
        )
        return ConfigSaveResponse(success=True, message=message, page=page)

    async def test(self, body: SaveConfigBody) -> ConfigTestResponse:
        """Parse and test the form without persisting.

        Args:
            body: Submitted config form values.

        Returns:
            Pydantic response with the connection success flag and message.
        """
        _config, _decision, success, message = await self._parse_and_test(
            body, force_test=True
        )
        return ConfigTestResponse(success=success, message=message)

    async def _parse_and_test(
        self, body: SaveConfigBody, *, force_test: bool
    ) -> tuple[AppConfig, ApiKeyDecision, bool, str]:
        """Parse the form, build the config, and optionally probe the provider.

        The live provider probe runs only when explicitly requested (``test``) or
        when the provider-relevant fields (provider type, base URL, model, API
        key) changed since the last save (S11). Otherwise the connection is
        assumed healthy and saving skips the network round-trip.

        Args:
            body: Submitted config form values.
            force_test: Always probe the provider, regardless of field changes.

        Returns:
            Tuple of the built config (or a fallback on failure), the API key
            decision, the connection success flag, and a message.
        """
        existing = self._config_service.get_config()
        catalog = self._load_catalog()
        try:
            normalized_locale = normalize_locale(body.locale)
            normalized_size = normalize_stt_model_size(body.speech_model_size)
            normalized_preset_id = normalize_model_id(body.llm_preset_id, catalog)
        except ValueError as exc:
            return (
                _fallback_config(body, existing),
                ApiKeyDecision(ApiKeyKind.KEEP),
                False,
                str(exc),
            )

        entry = catalog.models.get(normalized_preset_id)
        if entry is None:
            return (
                _fallback_config(body, existing),
                ApiKeyDecision(ApiKeyKind.KEEP),
                False,
                "Interview model not found",
            )

        tts_voice_id = resolve_tts_voice_id(existing, normalized_locale)

        config = AppConfig(
            timeout=body.timeout,
            locale=normalized_locale,
            speech_model_size=normalized_size,
            question_voice_enabled=body.question_voice_enabled,
            tts_voice_id=tts_voice_id,
            llm_preset_id=normalized_preset_id,
        )
        decision = resolve_api_key_from_form(body.api_key, entry)
        effective = EffectiveModelConfig(
            provider_type=entry.provider_type,
            base_url=entry.base_url,
            model=entry.model,
            api_key=decision.value,
            timeout=body.timeout,
            accepts_audio_input=entry.accepts_audio_input,
        )
        success, message = True, ""
        if force_test or self._provider_changed(existing, catalog, effective, decision):
            success, message = await self._config_service.test_model(effective)
        return config, decision, success, message

    def _provider_changed(
        self,
        existing: AppConfig | None,
        catalog: LLMCatalog,
        proposed: EffectiveModelConfig,
        decision: ApiKeyDecision,
    ) -> bool:
        """Whether the save changes the provider endpoint, requiring a probe.

        Compares the newly proposed effective provider settings against the
        currently saved state. ``None`` previous state (no config or no prior
        selection) is treated as a change.

        Args:
            existing: Previously persisted config, if any.
            catalog: Loaded model catalog.
            proposed: Effective provider settings being saved.
            decision: API key decision for the submitted form.

        Returns:
            True when a live provider probe is needed before persisting.
        """
        if existing is None or existing.llm_preset_id is None:
            return True
        old_entry = catalog.models.get(existing.llm_preset_id)
        if old_entry is None:
            return True
        previous = EffectiveModelConfig.from_entry(old_entry, timeout=existing.timeout)
        return provider_config_changed(previous, proposed)

    def _load_catalog(self) -> LLMCatalog:
        """Load the interview model catalog exactly once for a parse.

        Returns:
            The loaded catalog.
        """
        return self._catalog_service.load_catalog()
