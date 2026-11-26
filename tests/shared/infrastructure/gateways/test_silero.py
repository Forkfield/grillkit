# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the in-process Silero TTS gateway."""

import io
import wave

import numpy as np
import pytest

from app.shared.infrastructure.gateways.silero import (
    SileroTtsGateway,
    samples_to_wav_bytes,
    split_text_chunks,
    synthesize_samples,
)
from app.shared.tts_voices import voice_spec_for_id


class _FakeTensor:
    """Minimal torch-tensor lookalike exposing ``numpy()``."""

    def __init__(self, samples: np.ndarray) -> None:
        """Store the waveform samples."""
        self._samples = np.asarray(samples, dtype=np.float32)

    def numpy(self) -> np.ndarray:
        """Return the underlying array like ``torch.Tensor.numpy``."""
        return self._samples


class _FakeModel:
    """Silero model lookalike recording ``apply_tts`` calls."""

    def __init__(self, chunk_seconds: float = 0.05) -> None:
        """Initialize with a fixed chunk duration in seconds."""
        self._chunk_seconds = chunk_seconds
        self.calls: list[tuple[str, str, int]] = []

    def apply_tts(self, *, text: str, speaker: str, sample_rate: int) -> _FakeTensor:
        """Record the call and return silence for the chunk."""
        self.calls.append((text, speaker, sample_rate))
        return _FakeTensor(
            np.zeros(int(sample_rate * self._chunk_seconds), dtype=np.float32)
        )


class TestSplitTextChunks:
    """Tests for split_text_chunks."""

    def test_empty_text_yields_no_chunks(self):
        """Blank input produces no chunks."""
        assert split_text_chunks("   ") == []

    def test_short_sentences_merge(self):
        """Sentences below the limit are merged into one chunk."""
        assert split_text_chunks("Один.  Два! ", max_chars=100) == ["Один. Два!"]

    def test_long_text_splits_on_sentence_boundaries(self):
        """Text above the limit splits at sentence boundaries."""
        text = "Первое предложение. Второе предложение. Третье предложение."
        chunks = split_text_chunks(text, max_chars=40)
        assert all(len(chunk) <= 40 for chunk in chunks)
        assert " ".join(chunks).startswith("Первое")

    def test_oversized_sentence_hard_splits_at_word_boundary(self):
        """A single long sentence splits inside at word boundaries."""
        text = " ".join(["слово"] * 60)
        chunks = split_text_chunks(text, max_chars=30)
        assert chunks
        assert all(len(chunk) <= 30 for chunk in chunks)
        assert all(" " not in chunk or len(chunk) <= 30 for chunk in chunks)

    def test_chunks_preserve_all_content(self):
        """Every character (except collapsed whitespace) appears in chunks."""
        text = "Первое. Второе. Третье. Четвёртое."
        chunks = split_text_chunks(text, max_chars=12)
        rejoined = " ".join(chunks)
        for sentence in text.split():
            assert sentence in rejoined


class TestSamplesToWavBytes:
    """Tests for samples_to_wav_bytes."""

    def test_encodes_mono_16bit_wav(self):
        """Output parses as mono 16-bit WAV at the given rate."""
        wav_bytes = samples_to_wav_bytes(
            np.array([0.0, 0.5, -0.5], dtype=np.float32), 24000
        )
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            assert wav_file.getnchannels() == 1
            assert wav_file.getsampwidth() == 2
            assert wav_file.getframerate() == 24000
            assert wav_file.getnframes() == 3

    def test_clips_out_of_range_samples(self):
        """Samples beyond [-1, 1] are clipped, not wrapped."""
        wav_bytes = samples_to_wav_bytes(np.array([2.0, -2.0], dtype=np.float32), 24000)
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            frames = wav_file.readframes(2)
        assert frames[0:2] == b"\xff\x7f"
        assert frames[2:4] == b"\x01\x80"

    def test_empty_samples_write_valid_header(self):
        """Zero samples still produce a parseable WAV file."""
        wav_bytes = samples_to_wav_bytes(np.zeros(0, dtype=np.float32), 24000)
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            assert wav_file.getnframes() == 0


class TestSynthesizeSamples:
    """Tests for synthesize_samples."""

    def test_calls_model_per_chunk_with_spec_arguments(self):
        """Each chunk is synthesized with the voice spec speaker and rate."""
        model = _FakeModel()
        spec = voice_spec_for_id("ru-aidar")
        text = "Первое предложение. " * 30
        _ = synthesize_samples(model, spec, text)
        assert model.calls
        for chunk, speaker, sample_rate in model.calls:
            assert len(chunk) <= 400
            assert speaker == spec.speaker
            assert sample_rate == spec.sample_rate

    def test_concatenates_chunk_audio(self):
        """Chunk audio is concatenated in order."""
        model = _FakeModel(chunk_seconds=0.05)
        spec = voice_spec_for_id("ru-aidar")
        samples = synthesize_samples(model, spec, "Один. Два!")
        expected_frames = int(spec.sample_rate * 0.05) * len(model.calls)
        assert samples.shape[0] == expected_frames

    def test_empty_text_returns_no_samples(self):
        """Empty text synthesizes nothing."""
        model = _FakeModel()
        spec = voice_spec_for_id("ru-aidar")
        samples = synthesize_samples(model, spec, "  ")
        assert samples.shape[0] == 0
        assert model.calls == []


class TestGatewaySynthesize:
    """Tests for the gateway synthesis path."""

    def _loaded_gateway(self) -> tuple[SileroTtsGateway, _FakeModel]:
        """Build a gateway whose voice is loaded with a fake model."""
        gateway = SileroTtsGateway()
        model = _FakeModel()
        gateway._artifact = model
        gateway._loaded_key = "ru-aidar"
        return gateway, model

    def test_synthesize_sync_returns_wav_bytes(self):
        """Blocking synthesis returns a WAV stream at the spec rate."""
        gateway, _model = self._loaded_gateway()
        wav_bytes = gateway.synthesize_wav_bytes_sync("Как работает дикт?")
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            assert wav_file.getframerate() == 24000
            assert wav_file.getnframes() > 0

    async def test_synthesize_runs_in_worker_thread(self):
        """Async synthesis returns the same WAV payload."""
        gateway, _model = self._loaded_gateway()
        wav_bytes = await gateway.synthesize_wav_bytes("Как работает дикт?")
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            assert wav_file.getnframes() > 0

    def test_synthesize_without_loaded_voice_raises(self):
        """Synthesis without a loaded voice raises RuntimeError."""
        gateway = SileroTtsGateway()
        with pytest.raises(RuntimeError, match="not loaded"):
            _ = gateway.synthesize_wav_bytes_sync("текст")
