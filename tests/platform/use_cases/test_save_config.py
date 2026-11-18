# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for SaveConfigUseCase (parse/test + persist orchestration)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.llm_models import LLMModelEntry
from app.platform.domain.config import AppConfig
from app.platform.schemas import ConfigPageContext, SaveConfigBody
from app.platform.use_cases.save_config import SaveConfigUseCase


def _entry(*, api_key: str | None = None) -> LLMModelEntry:
    return LLMModelEntry(
        id="cloud",
        display_name="Cloud",
        provider_type="openai-compatible",
        model="gpt-4",
        base_url="https://api.example.com/v1",
        api_key_required=True,
        api_key=api_key,
    )


def _fake_page() -> ConfigPageContext:
    """A minimal page context to stand in for build_page_context's output."""
    return ConfigPageContext(config=None, locales={}, speech_model_specs={})


def _make_use_case(
    *,
    existing=None,
    success=True,
    message="OK",
    speech_errors=(),
) -> tuple[SaveConfigUseCase, MagicMock, MagicMock]:
    """Build a SaveConfigUseCase with stubbed collaborators.

    Returns:
        The use case, its config service mock, and its coordinator mock.
    """
    entry = _entry()
    catalog_service = MagicMock()
    catalog_service.load_catalog.return_value = SimpleNamespace(
        models={"cloud": entry}
    )

    config_service = MagicMock()
    config_service.get_config.return_value = existing
    config_service.test_model = AsyncMock(return_value=(success, message))

    coordinator = MagicMock()
    coordinator.reload_after_config_save = AsyncMock(return_value=list(speech_errors))

    use_case = SaveConfigUseCase(
        config_service,
        catalog_service,
        coordinator,
        whisper_model_service=MagicMock(),
        voice_status_service=MagicMock(),
    )
    return use_case, config_service, coordinator


def _body(**overrides) -> SaveConfigBody:
    data = {
        "llm_preset_id": "cloud",
        "api_key": "secret",
        "timeout": 30.0,
        "locale": "en",
        "speech_model_size": "small",
        "question_voice_enabled": True,
    }
    data.update(overrides)
    return SaveConfigBody(**data)


class TestExecute:
    """Tests for SaveConfigUseCase.execute."""

    @pytest.mark.asyncio
    async def test_saves_config_and_builds_success_response(self):
        """A valid body persists and returns a successful response."""
        use_case, config_service, coordinator = _make_use_case()
        with patch(
            "app.platform.use_cases.save_config.build_page_context",
            new=AsyncMock(return_value=_fake_page()),
        ) as mock_page:
            result = await use_case.execute(_body())

        assert result.success is True
        assert result.message == "Configuration saved successfully"
        assert result.page == _fake_page()
        config_service.save_config.assert_called_once()
        coordinator.reload_after_config_save.assert_awaited_once()
        mock_page.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_saves_config_even_when_speech_fails(self):
        """Config is still saved when a speech model fails to load."""
        use_case, config_service, coordinator = _make_use_case(
            speech_errors=("Whisper failed to load",)
        )
        with patch(
            "app.platform.use_cases.save_config.build_page_context",
            new=AsyncMock(return_value=_fake_page()),
        ):
            result = await use_case.execute(_body())

        config_service.save_config.assert_called_once()
        assert result.success is True
        assert "Whisper failed to load" in result.message

    @pytest.mark.asyncio
    async def test_write_failure_returns_error_without_reloading(self):
        """A failed persist surfaces as success=False with submitted context (S13)."""
        use_case, config_service, coordinator = _make_use_case()
        config_service.save_config.side_effect = OSError("disk full")
        with patch(
            "app.platform.use_cases.save_config.build_page_context",
            new=AsyncMock(return_value=_fake_page()),
        ) as mock_page:
            result = await use_case.execute(_body())

        assert result.success is False
        assert result.message == "disk full"
        coordinator.reload_after_config_save.assert_not_awaited()
        mock_page.assert_awaited_once()
        _, kwargs = mock_page.call_args
        assert kwargs["mask_secret"] is False
        assert kwargs["error"] == result.message

    @pytest.mark.asyncio
    async def test_invalid_preset_does_not_save_and_returns_error(self):
        """An invalid model id returns an error without persisting."""
        use_case, config_service, _ = _make_use_case()
        with patch(
            "app.platform.use_cases.save_config.normalize_model_id",
            side_effect=ValueError("Unsupported LLM model"),
        ), patch(
            "app.platform.use_cases.save_config.build_page_context",
            new=AsyncMock(return_value=_fake_page()),
        ) as mock_page:
            result = await use_case.execute(_body(llm_preset_id="invalid"))

        assert result.success is False
        assert "Unsupported LLM model" in result.message
        config_service.save_config.assert_not_called()
        mock_page.assert_awaited_once()
        # Error page is built from the submitted (fallback) config, unmasked.
        _, kwargs = mock_page.call_args
        assert kwargs["mask_secret"] is False
        assert kwargs["error"] == result.message

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "patch_target, overrides, expected",
        [
            (
                "app.platform.use_cases.save_config.normalize_locale",
                {"locale": "xx"},
                "Unsupported locale 'xx'",
            ),
            (
                "app.platform.use_cases.save_config.normalize_stt_model_size",
                {"speech_model_size": "xl"},
                "Unsupported stt model size 'xl'",
            ),
        ],
    )
    async def test_invalid_normalization_does_not_save_and_returns_error(
        self, patch_target, overrides, expected
    ):
        """An unsupported locale/size returns an error without persisting.

        All ``normalize_*`` helpers validate and raise ``ValueError`` (S8), and
        the use case must catch them so they surface as a graceful failure
        rather than an unhandled error.
        """
        use_case, config_service, _ = _make_use_case()
        with patch(
            patch_target,
            side_effect=ValueError(expected),
        ), patch(
            "app.platform.use_cases.save_config.build_page_context",
            new=AsyncMock(return_value=_fake_page()),
        ) as mock_page:
            result = await use_case.execute(_body(**overrides))

        assert result.success is False
        assert expected in result.message
        config_service.save_config.assert_not_called()
        mock_page.assert_awaited_once()
        _, kwargs = mock_page.call_args
        assert kwargs["mask_secret"] is False
        assert kwargs["error"] == result.message


class TestTest:
    """Tests for SaveConfigUseCase.test."""

    @pytest.mark.asyncio
    async def test_returns_success_without_saving(self):
        """A valid body returns success and never persists."""
        use_case, config_service, _ = _make_use_case()
        with patch(
            "app.platform.use_cases.save_config.build_page_context",
            new=AsyncMock(return_value=_fake_page()),
        ):
            result = await use_case.test(_body())

        assert result.success is True
        assert result.message == "OK"
        config_service.save_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_failure_message(self):
        """A connection failure is surfaced without saving."""
        use_case, config_service, _ = _make_use_case(
            success=False, message="Connection refused"
        )
        result = await use_case.test(_body(api_key="bad"))

        assert result.success is False
        assert result.message == "Connection refused"
        config_service.save_config.assert_not_called()


class TestProviderProbeScheduling:
    """S11: the live provider probe runs only on /test or when provider fields change."""

    @pytest.mark.asyncio
    async def test_test_always_probes_even_when_provider_unchanged(self):
        """The explicit /test endpoint probes regardless of field changes."""
        existing = AppConfig(
            llm_preset_id="cloud",
            timeout=30.0,
            locale="en",
        )
        use_case, config_service, _ = _make_use_case(existing=existing)
        result = await use_case.test(_body(api_key=""))

        assert result.success is True
        config_service.test_model.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_skips_probe_when_provider_unchanged(self):
        """Saving with unchanged provider fields avoids the network round-trip."""
        existing = AppConfig(
            llm_preset_id="cloud",
            timeout=30.0,
            locale="en",
        )
        use_case, config_service, coordinator = _make_use_case(existing=existing)
        with patch(
            "app.platform.use_cases.save_config.build_page_context",
            new=AsyncMock(return_value=_fake_page()),
        ) as mock_page:
            result = await use_case.execute(
                _body(api_key="", locale="en", speech_model_size="small")
            )

        assert result.success is True
        config_service.test_model.assert_not_awaited()
        config_service.save_config.assert_called_once()
        coordinator.reload_after_config_save.assert_awaited_once()
        mock_page.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_probes_when_provider_fields_changed(self):
        """Changing a provider-relevant field (API key) triggers a probe."""
        existing = AppConfig(
            llm_preset_id="cloud",
            timeout=30.0,
            locale="en",
        )
        use_case, config_service, coordinator = _make_use_case(existing=existing)
        with patch(
            "app.platform.use_cases.save_config.build_page_context",
            new=AsyncMock(return_value=_fake_page()),
        ):
            result = await use_case.execute(_body(api_key="newkey"))

        assert result.success is True
        config_service.test_model.assert_awaited_once()
        config_service.save_config.assert_called_once()
        coordinator.reload_after_config_save.assert_awaited_once()
