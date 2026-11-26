# Changelog

Versions use the release date: `YYYY.M.d` (newest first).

Work in progress is accumulated under `[Unreleased]`; on release, that section becomes the new dated version.

## [Unreleased]

### Added

- **Automatic model import** — adding a provider immediately loads the model list from its endpoint into the catalog; **Load models** on the provider card re-imports it on demand. A failed attempt shows a **Discovery failed** mark with the error on the provider card
- **Per-model audio flag** — every model in the provider list has an inline **audio** checkbox (defaults to off for imported models); toggling it no longer requires opening the edit form

### Changed

- **Question voice engine** — Piper is replaced by **Silero TTS** (in-process, CPU PyTorch). Russian uses `v5_5_ru` (automatic stress, homographs, question intonation); en/de/es/fr use Silero v3 models. Voices download from `models.silero.ai` into `data/silero-voices/` (no Hugging Face token needed). Saved Piper voice ids in `config.json` are remapped automatically — re-download the voice on `/config`. Silero models are licensed CC BY-NC 4.0 (see `NOTICE`)
- **Russian question narration** — Latin technical terms (Kubernetes, CI/CD, PostgreSQL…) and numbers are expanded to Cyrillic words before synthesis; the TTS cache moves to `data/tts-cache/v3/`
- **Docker image** — about 1.2 GB larger (920 MB → 2.1 GB) because of the CPU-only PyTorch wheel; `piper-tts` is removed
- **STT/TTS naming** — unified entity naming: general speech-to-text / text-to-speech concepts are now `Stt` / `Tts`, concrete implementations are `WhisperStt` / `PiperTts` (e.g. `WhisperSttRuntime`, `PiperTtsRuntime`, `stt_models`, `whisper_stt`). Internal only; no API or config format changes.
- **Configuration navigation** — the config page sections are now a proper sidebar list (icon, label, description) instead of plain buttons
- **Static assets** — the SPA shell, styles and scripts are served with `Cache-Control: no-cache`, so a rebuilt UI is never masked by a stale browser cache

### Fixed

- **HTML escaping** — quotes in dynamic values (provider error messages, model names from an endpoint) are now escaped, closing an attribute-injection vector in tooltips and option attributes
- **AI evaluation timeout** — each evaluation now has a hard total time budget (2× the configured timeout; session completion allows 3 sequential evaluations). A slow or failing provider is cut off at that deadline with a clear message instead of leaving the page stuck on an invisible watchdog. The browser no longer shows a misleading "check /config" error on a timer — it waits for the server and surfaces the real provider error (including upstream 5xx errors)
- **Provider error messages** — upstream outages are recognized only from structured provider fields (`error code: 5xx`, `upstream`, `server_error`), so unrelated messages that merely contain numbers are no longer reported as a provider server error

### Removed

## 2026.8.9

### Added

### Changed

- **Updated UI** — light theme is now the default, with a **dark theme toggle** (sun/moon) in the navigation bar. Your choice is remembered and falls back to your system preference on first visit. The whole palette moved to a warm, restrained **«ember»** (orange/red) accent with better contrast throughout
- **Theory answer evaluation** — load `expected_points` rubric bullets from question banks, pass them through evaluation prompts with explicit candidate-only scoring rules, and use temperature 0 for structured LLM evaluation

### Fixed

- **Coding timer** — when a coding round timer expires, the round now submits automatically and the session advances even if you refresh the page
- **Whisper transcription** — more robust audio transcription (voice-activity detection disabled) with clearer audio-answer logging

### Removed

## 2026.7.14

### Added

### Changed

- **Question bank overhaul** — restructured and expanded question sets across all tracks (Python, Database, Airflow, Docker, Kubernetes, Observability, Kafka, RabbitMQ); updated questions map

### Fixed

- **Session timeout** — fixed timer handling that caused premature session expiration or stuck rounds

### Removed

## 2026.6.16

### Added

- **Known questions** — mark theory or coding bank items as known during an interview (**I know this**) or on review pages; optionally exclude them when starting a new session; manage the list from **Known Questions** in the navigation bar

### Changed

- **Add model to catalog** — the catalog model id is generated automatically from the display name; removed the **Model id** field on `/config`
- **UI** — refreshed dark theme with clearer hierarchy, IDE-style coding editor, terminal-style run output, and updated status badges on the dashboard

### Fixed

- **Theory then coding sessions** — fixed errors when advancing from theory to coding in a combined session
- **Coding follow-ups** — explanation rounds now submit your typed explanation instead of the code in the editor
- **Coding timers** — expired rounds score 0 and the session advances automatically
- **Setup review** — known-questions option shows the correct hint for the checkbox
- **Early session end** — partial theory/coding scores are kept when you end a session before finishing every task
- **Theory answers** — more reliable submit flow for text and audio answers during AI evaluation
- **Dashboard** — faster interview history on the home page

### Removed

## 2026.6.12

### Added

- **Coding interviews** — practice live coding in the browser: editor, Run on public tests, Submit for evaluation, and a review page after the session; use `docker compose --profile coding` for code execution
- **Coding question bank** — 33 Python language-focused tasks (junior: basics, strings, functions, control flow, exceptions, OOP, collections; middle: refactor, bug hunt, complete code, implement)

### Changed

- **New interview setup** — choose session mode (theory only, coding only, or both in sequence) and configure theory and coding topics separately on one screen

### Fixed

- **First-time configuration** — saving provider settings and downloading Whisper or Piper models works on a fresh install, including in Docker

## 2026.5.31

### Added

- **Audio answers** — per-model “Accepts audio input” in the LLM catalog, WAV upload API, and Record / Send controls on the interview page (Whisper + multimodal model)
- **Question banks** — System Design; Kafka, RabbitMQ, Docker, Kubernetes, Observability, and Airflow tracks; expanded Python and Database categories (en/ru)
- **Alembic migrations** on startup and optional `DATABASE_URL` for the application database

### Changed

- Interview setup uses **track** terminology instead of language; the last follow-up on a question advances immediately while AI scoring finishes in the background

### Fixed

### Removed

## 2026.5.24

### Added

- Optional **per-round timer** on interview setup — expired rounds score 0 and the session moves on
- **Voice input** for answers — offline Whisper; download the model on `/config`
- **Question audio** (optional) — Piper TTS reads questions aloud; enable and download a voice on `/config`
- **LLM model catalog** in `data/llm_models.json` — API keys and model list live separately from `data/config.json`; pick the interview model on `/config`

### Changed

### Fixed

### Removed

## 2026.5.20

First release.

- AI interview sessions with WebSocket chat, scoring, and follow-ups
- Setup: language, level, topic, locale, question count
- Question banks: Python and Database/SQL (YAML)
- Dashboard, provider configuration, Docker Compose deployment
