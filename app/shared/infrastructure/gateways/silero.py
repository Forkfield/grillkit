# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""In-process Silero voice loading and synthesis."""

import asyncio
import gc
import io
import logging
import re
from typing import Any
import wave

import numpy as np

from app.shared.infrastructure.gateways.silero_storage import (
    is_voice_installed,
    model_path,
    voice_dir,
)
from app.shared.infrastructure.in_process_runtime import InProcessArtifactRuntime
from app.shared.tts_voices import (
    SileroVoiceSpec,
    normalize_tts_voice_id,
    voice_spec_for_id,
)

logger = logging.getLogger(__name__)

# Silero refuses texts longer than ~1000 symbols; chunk well below the limit.
_MAX_CHUNK_CHARS = 400
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
_WHITESPACE_RE = re.compile(r"\s+")


class SileroTtsGateway(InProcessArtifactRuntime):
    """Hold a loaded Silero model for the configured question voice.

    Satisfies the :class:`TtsEngine` protocol, so it can be injected into the
    :class:`SpeechRuntimeCoordinator` as the TTS backend. PyTorch is imported
    lazily inside :meth:`_load_sync`, mirroring the previous Piper gateway, so
    importing this module (and running tests) works without a loaded model.
    """

    def _normalize_key(self, key: str) -> str:
        """Normalize a Silero voice identifier."""
        return normalize_tts_voice_id(key)

    def _is_installed(self, key: str) -> bool:
        """Return whether a valid Silero voice is on disk for ``key``."""
        return is_voice_installed(key)

    def _load_sync(self, key: str) -> Any:
        """Load the Silero ``.pt`` package from disk (blocking)."""
        import os

        import torch
        from torch.package.package_importer import PackageImporter

        torch.set_grad_enabled(False)
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        importer = PackageImporter(str(model_path(key)))
        return importer.load_pickle("tts_models", "model")

    def is_installed(self, voice_id: str) -> bool:
        """Return whether a valid Silero voice is on disk for ``voice_id``."""
        return self._is_installed(voice_id)

    def is_loaded(self, voice_id: str) -> bool:
        """Return whether the voice for ``voice_id`` is loaded in memory."""
        return self._has_loaded_key(voice_id)

    async def load_voice(self, voice_id: str) -> bool:
        """Load or reload the Silero voice for ``voice_id`` from disk.

        Args:
            voice_id: Silero voice identifier.

        Returns:
            True if a voice is loaded for the id after this call.
        """
        code = self._normalize_key(voice_id)
        loaded = await self._load(voice_id)
        if loaded:
            logger.info("Loaded Silero voice %s from %s", code, voice_dir(code))
        return loaded

    def on_loaded(self, key: str, artifact: Any) -> None:
        """Log successful voice load."""
        del artifact
        logger.debug("Silero voice %s loaded into memory", key)

    def on_unloaded(self) -> None:
        """Log successful voice unload."""
        logger.debug("Silero voice unloaded from memory")
        _ = gc.collect()

    def synthesize_wav_bytes_sync(self, text: str) -> bytes:
        """Synthesize WAV audio for ``text`` using the loaded voice (blocking).

        Long texts are split into sentence-boundary chunks within the model's
        input limit and concatenated into one mono 16-bit WAV stream.

        Args:
            text: Prepared question text snapshot.

        Returns:
            Raw WAV file bytes.

        Raises:
            RuntimeError: When no voice is loaded.
        """
        model = self._artifact
        if model is None or self._loaded_key is None:
            raise RuntimeError("Silero voice is not loaded")
        spec = voice_spec_for_id(self._loaded_key)
        samples = synthesize_samples(model, spec, text)
        return samples_to_wav_bytes(samples, spec.sample_rate)

    async def synthesize_wav_bytes(self, text: str) -> bytes:
        """Synthesize WAV audio for ``text`` in a worker thread.

        Args:
            text: Prepared question text snapshot.

        Returns:
            Raw WAV file bytes.
        """
        return await asyncio.to_thread(self.synthesize_wav_bytes_sync, text)


def split_text_chunks(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> list[str]:
    """Split text into sentence-aligned chunks within the model input limit.

    Args:
        text: Prepared question text.
        max_chars: Maximum characters per chunk.

    Returns:
        Whitespace-normalized chunks, each at most ``max_chars`` long.
    """
    normalized = _WHITESPACE_RE.sub(" ", text.strip())
    if not normalized:
        return []
    chunks: list[str] = []
    current = ""
    for sentence in _SENTENCE_SPLIT_RE.split(normalized):
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(sentence) > max_chars:
            head, sentence = _split_at_word(sentence, max_chars)
            chunks.append(head)
        current = sentence
    if current:
        chunks.append(current)
    return chunks


def _split_at_word(text: str, max_chars: int) -> tuple[str, str]:
    """Split ``text`` at the last word boundary before ``max_chars``."""
    cut = text.rfind(" ", 0, max_chars)
    if cut <= 0:
        cut = max_chars
    head = text[:cut]
    rest = text[cut:].lstrip()
    return head, rest


def synthesize_samples(model: Any, spec: SileroVoiceSpec, text: str) -> np.ndarray:
    """Synthesize ``text`` into float32 samples in ``[-1, 1]``.

    Args:
        model: Loaded Silero model package object.
        spec: Voice spec providing speaker and sample rate.
        text: Prepared question text.

    Returns:
        Mono float32 waveform samples.
    """
    chunks = split_text_chunks(text)
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    parts = [_chunk_samples(model, spec, chunk) for chunk in chunks]
    if len(parts) == 1:
        return parts[0]
    return np.concatenate(parts)


def _chunk_samples(model: Any, spec: SileroVoiceSpec, chunk: str) -> np.ndarray:
    """Synthesize one chunk via ``apply_tts`` and decode it to float32."""
    audio = model.apply_tts(
        text=chunk,
        speaker=spec.speaker,
        sample_rate=spec.sample_rate,
    )
    samples = audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio)
    return np.asarray(samples, dtype=np.float32).reshape(-1)


def samples_to_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    """Encode float32 samples in ``[-1, 1]`` as mono 16-bit WAV bytes.

    Args:
        samples: Waveform samples.
        sample_rate: Sample rate in hertz.

    Returns:
        Raw WAV file bytes.
    """
    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2").tobytes()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


# Single in-process runtime instance shared by the coordinator and status services.
SileroTtsRuntime = SileroTtsGateway()
