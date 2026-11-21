/* GrillKit SPA shell — vanilla hash router + page registry.
 *
 * Routing model:
 *   - The SPA shell is served by the frontend container at `/`.
 *   - Hash routes (e.g. `#/dashboard`) are rendered client-side.
 *   - Pages that have NOT been migrated yet (Stage 2) fall back to a
 *     "legacy" card that links to the real server-rendered URL, which
 *     nginx proxies to the backend.
 *   - Page data is fetched from the backend JSON API (`/api/...`).
 */
(function () {
  "use strict";

  var view = document.getElementById("app-view");
  if (!view) {
    return;
  }

  /* ------------------------------------------------------------------ *
   * Utilities
   * ------------------------------------------------------------------ */

  function escapeHtml(value) {
    var div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  async function fetchJSON(path, options) {
    var opts = options || {};
    var headers = opts.headers || {};
    if (!("Accept" in headers)) {
      headers.Accept = "application/json";
    }
    var response = await fetch(path, {
      method: opts.method || "GET",
      headers: headers,
      body: opts.body,
    });
    if (!response.ok) {
      var detail = "";
      try {
        var body = await response.json();
        detail = body && body.detail ? body.detail : "";
      } catch (_e) {
        /* non-JSON error body */
      }
      var err = new Error(detail || ("Request failed: " + response.status));
      err.status = response.status;
      throw err;
    }
    return response.json();
  }

  function postJSON(path, body) {
    return fetchJSON(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  /* Load a script and resolve once it executes (or is already-cached). */
  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[src="' + src + '"]');
      if (existing && existing.dataset.loaded === "true") {
        resolve();
        return;
      }
      var script = document.createElement("script");
      script.src = src;
      script.async = false;
      script.onload = function () {
        script.dataset.loaded = "true";
        resolve();
      };
      script.onerror = function () {
        reject(new Error("Failed to load script: " + src));
      };
      document.head.appendChild(script);
    });
  }

  function loadScripts(sources) {
    return sources.reduce(function (chain, src) {
      return chain.then(function () {
        return loadScript(src);
      });
    }, Promise.resolve());
  }

  function errMessage(err, fallback) {
    return (err && err.message) || fallback || "Something went wrong.";
  }

  function errorCard(message) {
    return (
      '<div class="error-box">' +
      "<p>" + escapeHtml(message) + "</p>" +
      "</div>"
    );
  }

  function alertError(message) {
    return '<div class="alert alert-error">' + escapeHtml(message) + "</div>";
  }

  function alertSuccess(message) {
    return '<div class="alert alert-success">' + escapeHtml(message) + "</div>";
  }

  function legacyCard(url, label) {
    return (
      '<div class="card">' +
      "<h1>" + escapeHtml(label) + "</h1>" +
      "<p>This page has not been migrated to the new frontend yet.</p>" +
      '<p><a class="btn" href="' + escapeHtml(url) + '">Open legacy page</a></p>' +
      "</div>"
    );
  }

  /* ------------------------------------------------------------------ *
   * Page registry.
   * Each page: function(view, params) -> void (may be async).
   * ------------------------------------------------------------------ */

  var pages = {};

  /* ------------------------------------------------------------------ *
   * Dashboard page.
   * ------------------------------------------------------------------ */

  pages.dashboard = function (container) {
    container.innerHTML =
      '<div class="empty-state">' +
      '<div class="empty-state-icon">&#x1F393;</div>' +
      "<h3>Ready to practice?</h3>" +
      "<p>Start a new interview session to sharpen your skills with AI-powered feedback.</p>" +
      '<div class="button-group" style="justify-content: center;">' +
      '<a href="#/setup" class="btn btn-primary btn-lg">Start New Interview</a>' +
      '<a href="#/config" class="btn btn-outline btn-lg">Configure AI Provider</a>' +
      "</div>" +
      "</div>";

    fetchJSON("/api/dashboard")
      .then(function (rows) {
        if (!rows || !rows.length) {
          return;
        }
        var body = rows
          .map(function (row) {
            var historyHref = toHashPath(row.url);
            return (
              '<tr class="history-row history-row--' + escapeHtml(row.status) + '" ' +
              'onclick="window.location.hash=\'' + escapeHtml(historyHref) + '\'" role="link" tabindex="0">' +
              "<td>" +
              '<a href="' + escapeHtml(historyHref) + '" class="history-link">' + escapeHtml(row.title) + "</a>" +
              '<span class="history-mode-badge">' + escapeHtml(row.session_mode_label) + "</span>" +
              "</td>" +
              "<td>" + escapeHtml(row.question_count) + "</td>" +
              "<td>" + escapeHtml(row.score_display) + "</td>" +
              "<td><span class=\"history-status history-status--" + escapeHtml(row.status) + "\">" +
              escapeHtml(row.status_label) + "</span></td>" +
              '<td class="history-date">' + escapeHtml(row.datetime_display) + "</td>" +
              "</tr>"
            );
          })
          .join("");

        var history =
          '<div class="card interview-history-card">' +
          '<div class="card-header">' +
          '<h2 class="card-title">Interview history</h2>' +
          '<p class="card-subtitle">Your recent sessions (up to 20)</p>' +
          "</div>" +
          '<div class="history-table-wrap"><table class="history-table"><thead><tr>' +
          "<th>Interview</th><th>Questions</th><th>Score</th><th>Status</th><th>Date</th>" +
          "</tr></thead><tbody>" +
          body +
          "</tbody></table></div>" +
          "</div>";

        container.insertAdjacentHTML("beforeend", history);
      })
      .catch(function (err) {
        container.insertAdjacentHTML(
          "beforeend",
          errorCard(errMessage(err, "Could not load interview history."))
        );
      });
  };

  /* ------------------------------------------------------------------ *
   * Known Questions manage page.
   * ------------------------------------------------------------------ */

  function knownManageView() {
    return fetchJSON("/api/known-questions/manage");
  }

  function knownPlural(count) {
    return count === 1 ? "question" : "questions";
  }

  function buildKnownSection(branch, label, items, emptyText) {
    if (!items.length) {
      return (
        '<section class="known-questions-section">' +
        "<h2>" + escapeHtml(label) + "</h2>" +
        '<p class="known-questions-empty">' + escapeHtml(emptyText) + "</p>" +
        "</section>"
      );
    }
    return (
      '<section class="known-questions-section">' +
      "<h2>" + escapeHtml(label) + "</h2>" +
      '<ul class="known-questions-list" data-branch="' + escapeHtml(branch) + '">' +
      items
        .map(function (item) {
          return (
            '<li class="known-questions-item">' +
            '<div class="known-questions-body">' +
            '<p class="known-questions-text">' + escapeHtml(item.text) + "</p>" +
            '<code class="known-questions-id">' + escapeHtml(item.id) + "</code>" +
            "</div>" +
            '<button type="button" class="btn btn-outline btn-sm known-questions-unmark" ' +
            'data-branch="' + escapeHtml(branch) + '" ' +
            'data-item-id="' + escapeHtml(item.id) + '">Unmark</button>' +
            "</li>"
          );
        })
        .join("") +
      "</ul>" +
      "</section>"
    );
  }

  function renderKnownView(container) {
    return knownManageView().then(function (data) {
      container.innerHTML =
        '<div class="known-questions-page">' +
        '<header class="section-review__header">' +
        "<div>" +
        '<p class="section-review__eyebrow">Question bank</p>' +
        '<h1 class="section-review__title">Known questions</h1>' +
        '<p class="section-review__meta">' +
        escapeHtml(data.total_count) + " " + escapeHtml(knownPlural(data.total_count)) +
        " marked as known</p>" +
        "</div>" +
        '<div class="section-review__actions">' +
        '<a href="#/setup" class="btn btn-outline">Back to Setup</a>' +
        '<a href="#/dashboard" class="btn btn-outline">Dashboard</a>' +
        "</div>" +
        "</header>" +
        '<p class="form-hint">' +
        "Known questions are excluded from new sessions when " +
        "&ldquo;Exclude questions I already know&rdquo; is enabled on setup." +
        "</p>" +
        buildKnownSection(
          "theory",
          "Theory",
          data.theory_items || [],
          "No theory questions marked as known."
        ) +
        buildKnownSection(
          "coding",
          "Coding",
          data.coding_items || [],
          "No coding tasks marked as known."
        ) +
        "</div>";
    });
  }

  pages["known-questions"] = function (container) {
    renderKnownView(container).catch(function (err) {
      container.innerHTML = errorCard(errMessage(err, "Could not load known questions."));
    });

    container.addEventListener("click", function (event) {
      var target = event.target;
      if (!target || typeof target.closest !== "function") {
        return;
      }
      var button = target.closest(".known-questions-unmark");
      if (!button) {
        return;
      }
      var branch = button.dataset.branch;
      var itemId = button.dataset.itemId;
      button.disabled = true;
      fetchJSON("/known-questions", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ branch: branch, item_id: itemId }),
      })
        .then(function () {
          return renderKnownView(container);
        })
        .catch(function (err) {
          button.disabled = false;
          container.insertAdjacentHTML(
            "beforeend",
            errorCard(errMessage(err, "Could not unmark question. Try again."))
          );
        });
    });
  };

  /* ------------------------------------------------------------------ *
   * Configuration page.
   * ------------------------------------------------------------------ */

  function selectedFormLocale(container) {
    var select = container.querySelector("#locale");
    return select ? select.value : "en";
  }

  function selectedSpeechSize(container) {
    var checked = container.querySelector(
      'input[name="speech_model_size"]:checked'
    );
    return checked ? checked.value : "small";
  }

  function buildConfigFormHTML(data) {
    var config = data.config || {};
    var selectedPreset = data.selected_llm_preset_id;

    var presetOptions;
    if (data.llm_presets && data.llm_presets.length) {
      presetOptions =
        '<select name="llm_preset_id" id="llm_preset_id" class="form-control" required>' +
        data.llm_presets
          .map(function (preset) {
            return (
              '<option value="' + escapeHtml(preset.id) + '"' +
              (preset.id === selectedPreset ? " selected" : "") +
              ' data-description="' + escapeHtml(preset.description || "") + '"' +
              ' data-api-key-required="' + (preset.api_key_required ? "true" : "false") + '"' +
              ' data-accepts-audio-input="' + (preset.accepts_audio_input ? "true" : "false") + '">' +
              escapeHtml(preset.display_name) +
              (preset.accepts_audio_input ? " (audio)" : "") +
              "</option>"
            );
          })
          .join("") +
        '</select><p class="form-hint" id="llm-preset-description"></p>';
    } else {
      presetOptions =
        '<div class="alert alert-info">' +
        "No models in the catalog yet. Add one below, then select it and save." +
        "</div>" +
        '<input type="hidden" name="llm_preset_id" value="">';
    }

    var localeOptions = Object.keys(data.locales || {})
      .map(function (code) {
        var selected =
          (config && config.locale === code) || (!config && code === "en");
        return (
          '<option value="' + escapeHtml(code) + '"' + (selected ? " selected" : "") + ">" +
          escapeHtml(data.locales[code]) + "</option>"
        );
      })
      .join("");

    var sizeOptions = Object.keys(data.speech_model_specs || {})
      .map(function (size) {
        var spec = data.speech_model_specs[size];
        var checked =
          (config && config.speech_model_size === size) ||
          (!config && size === "small");
        return (
          "<label class=\"speech-model-size-option\">" +
          '<input type="radio" name="speech_model_size" value="' + escapeHtml(size) + '"' +
          (checked ? " checked" : "") + ">" +
          '<span class="speech-model-size-option-title">' + escapeHtml(spec.display_name) + "</span>" +
          '<span class="speech-model-size-option-meta">~' + escapeHtml(spec.approx_download_mb) +
          " MB download &middot; " + escapeHtml(spec.ram_hint) + " RAM &middot; " +
          escapeHtml(spec.speed_hint) + " &middot; " + escapeHtml(spec.quality_hint) + "</span>" +
          "</label>"
        );
      })
      .join("");

    var timeoutValue = config && config.timeout != null ? config.timeout : 60;
    var questionVoiceChecked = config && config.question_voice_enabled ? " checked" : "";
    var removeButton =
      config && config.llm_preset_id
        ? '<div class="divider"></div>' +
          '<button type="button" id="config-remove-btn" class="btn btn-danger">Remove Configuration</button>'
        : "";

    return (
      (data.error ? alertError(data.error) : "") +
      (data.message ? alertSuccess(data.message) : "") +
      '<div class="card">' +
      '<div class="card-header">' +
      '<h1 class="card-title">AI Provider Configuration</h1>' +
      '<p class="card-subtitle">Configure your AI provider for interview feedback and evaluation</p>' +
      "</div>" +
      '<form id="config-form" class="form">' +
      '<div class="form-group" id="llm-preset-group">' +
      '<label for="llm_preset_id" class="form-label form-label-required">Interview model</label>' +
      presetOptions +
      "</div>" +
      '<div class="form-group" id="api-key-group">' +
      '<label for="api_key" class="form-label">API Key <span class="text-muted">(optional for local providers)</span></label>' +
      '<input type="password" name="api_key" id="api_key" class="form-control" value="" autocomplete="off" ' +
      'placeholder="' + (config.api_key ? "Leave blank to keep existing key" : "sk-...") + '">' +
      '<p class="form-hint">Stored in <code>data/llm_models.json</code> with the selected model.</p>' +
      "</div>" +
      '<div class="form-group">' +
      '<label for="locale" class="form-label form-label-required">Interview language</label>' +
      '<select name="locale" id="locale" class="form-control" required>' + localeOptions + "</select>" +
      '<p class="form-hint">Language for AI feedback and voice dictation transcription.</p>' +
      "</div>" +
      '<div class="form-group">' +
      "<label class=\"form-label\">" +
      '<input type="checkbox" name="question_voice_enabled" id="question_voice_enabled" value="true"' + questionVoiceChecked + ">" +
      " Read questions aloud</label>" +
      '<p class="form-hint">When enabled, the interview page reads each question aloud using an offline Piper voice (download on the Configuration page below).</p>' +
      "</div>" +
      '<div class="form-group">' +
      '<span class="form-label form-label-required">Speech model size</span>' +
      '<p class="form-hint">Offline Whisper model for voice input. Larger models are more accurate but slower and use more disk and RAM.</p>' +
      '<div class="speech-model-size-options" id="speech-model-size-group">' + sizeOptions + "</div>" +
      "</div>" +
      '<div class="form-group">' +
      '<label for="timeout" class="form-label">Timeout (seconds)</label>' +
      '<input type="number" name="timeout" id="timeout" class="form-control" value="' + escapeHtml(timeoutValue) +
      '" min="1" max="300" step="1">' +
      "</div>" +
      '<div class="divider"></div>' +
      '<div class="button-group">' +
      '<button type="submit" id="config-save-btn" class="btn btn-primary"' +
      (data.llm_presets && data.llm_presets.length ? "" : " disabled") + ">Save Configuration</button>" +
      '<button type="button" id="config-test-btn" class="btn btn-secondary"' +
      (data.llm_presets && data.llm_presets.length ? "" : " disabled") + ">Test Connection</button>" +
      "</div>" +
      removeButton +
      "</form>" +
      "</div>" +
      '<div class="card" id="add-llm-model-panel">' +
      '<div class="card-header">' +
      '<h2 class="card-title">Add model to catalog</h2>' +
      '<p class="card-subtitle">Save an OpenAI-compatible provider for reuse in the interview model list</p>' +
      "</div>" +
      '<form id="add-model-form" class="form">' +
      '<div class="form-group">' +
      '<label for="catalog_display_name" class="form-label form-label-required">Display name</label>' +
      '<input type="text" name="display_name" id="catalog_display_name" class="form-control" required placeholder="Work GPT-4">' +
      '<p class="form-hint">A stable id is generated from this name and stored in <code>data/llm_models.json</code>.</p>' +
      "</div>" +
      '<div class="form-group">' +
      '<label for="catalog_base_url" class="form-label form-label-required">Base URL</label>' +
      '<input type="url" name="base_url" id="catalog_base_url" class="form-control" required placeholder="https://api.openai.com/v1">' +
      "</div>" +
      '<div class="form-group">' +
      '<label for="catalog_model" class="form-label form-label-required">Model name</label>' +
      '<input type="text" name="model" id="catalog_model" class="form-control" required placeholder="gpt-4">' +
      "</div>" +
      '<div class="form-group">' +
      '<label for="catalog_api_key" class="form-label">API key</label>' +
      '<input type="password" name="api_key" id="catalog_api_key" class="form-control" autocomplete="off" placeholder="sk-...">' +
      '<p class="form-hint">Optional. Stored in <code>data/llm_models.json</code> with the model.</p>' +
      "</div>" +
      '<div class="form-group">' +
      "<label class=\"form-label\">" +
      '<input type="checkbox" name="api_key_required" id="catalog_api_key_required" value="true"> API key required</label>' +
      "</div>" +
      '<div class="form-group">' +
      "<label class=\"form-label\">" +
      '<input type="checkbox" name="accepts_audio_input" id="catalog_accepts_audio_input" value="true"> Accepts audio input</label>' +
      '<p class="form-hint">When enabled, the model is tested with a short audio probe on add and when saving configuration. Whisper must be installed for the selected speech model size.</p>' +
      "</div>" +
      '<button type="submit" class="btn btn-secondary">Add model</button>' +
      "</form>" +
      "</div>" +
      '<div class="card" id="speech-model-panel">' +
      '<div class="card-header">' +
      '<h2 class="card-title">Speech recognition model</h2>' +
      '<p class="card-subtitle" id="speech-model-subtitle"></p>' +
      "</div>" +
      '<div id="speech-model-status"></div>' +
      "</div>" +
      '<div class="card" id="question-voice-panel">' +
      '<div class="card-header">' +
      '<h2 class="card-title">Question voice (TTS)</h2>' +
      '<p class="card-subtitle" id="question-voice-subtitle"></p>' +
      "</div>" +
      '<div id="speech-tts-status"></div>' +
      "</div>"
    );
  }

  function artifactStatusHTML(status) {
    /* status: {state, percent, message, ...} */
    var hint =
      "<p class=\"form-hint\">" + escapeHtml(status.message) + "</p>";
    if (status.state === "missing") {
      return (
        hint +
        '<div class="alert alert-warning">Not installed yet.</div>'
      );
    }
    if (status.state === "ready") {
      return hint + '<div class="alert alert-success">' + escapeHtml(status.message) + "</div>";
    }
    if (status.state === "downloading") {
      return (
        hint +
        '<div class="alert alert-info">Downloading&hellip; ' + escapeHtml(status.percent) + "%</div>" +
        '<div class="progress-bar" role="progressbar" aria-valuenow="' + escapeHtml(status.percent) +
        '" aria-valuemin="0" aria-valuemax="100">' +
        '<div class="progress-bar-fill" style="width: ' + escapeHtml(status.percent) + '%;"></div>' +
        "</div>"
      );
    }
    if (status.state === "error" || status.state === "unavailable") {
      return hint + '<div class="alert alert-error">' + escapeHtml(status.message) + "</div>";
    }
    return hint;
  }

  function renderSpeechModelArtifact(target) {
    var size = selectedSpeechSize(target);
    var locale = selectedFormLocale(target);
    var subtitle = target.querySelector("#speech-model-subtitle");
    var sizeOption = target.querySelector(
      '.speech-model-size-option input[value="' + size + '"]'
    );
    var sizeLabel = sizeOption
      ? sizeOption.closest(".speech-model-size-option").querySelector(".speech-model-size-option-title").textContent.trim()
      : size;
    var localeLabel = target.querySelector("#locale");
    var label =
      localeLabel && localeLabel.selectedOptions && localeLabel.selectedOptions[0]
        ? localeLabel.selectedOptions[0].text
        : locale;
    if (subtitle) {
      subtitle.textContent = "Offline Whisper (" + sizeLabel + ") — dictation in " + label;
    }
    fetchJSON(
      "/speech/model/status?size=" + encodeURIComponent(size) + "&locale=" + encodeURIComponent(locale)
    )
      .then(function (status) {
        var host = target.querySelector("#speech-model-status");
        if (host) {
          host.dataset.state = status.state;
          host.dataset.percent = status.percent;
          host.innerHTML =
            artifactStatusHTML(status) +
            (status.state === "missing" || status.state === "error"
              ? '<button type="button" class="btn btn-secondary speech-download-btn" ' +
                'data-url="/speech/model/download?size=' + encodeURIComponent(size) +
                "&locale=" + encodeURIComponent(locale) + "\">Download speech model</button>"
              : "");
        }
        scheduleSpeechPoll(target);
      })
      .catch(function () {
        /* transient */
      });
  }

  function renderQuestionVoiceArtifact(target) {
    var locale = selectedFormLocale(target);
    var localeLabel = target.querySelector("#locale");
    var label =
      localeLabel && localeLabel.selectedOptions && localeLabel.selectedOptions[0]
        ? localeLabel.selectedOptions[0].text
        : locale;
    var subtitle = target.querySelector("#question-voice-subtitle");
    if (subtitle) {
      subtitle.textContent = "Offline Piper voice for reading interview questions aloud in " + label;
    }
    fetchJSON("/speech/tts/status?locale=" + encodeURIComponent(locale))
      .then(function (status) {
        var host = target.querySelector("#speech-tts-status");
        if (host) {
          host.dataset.state = status.state;
          host.dataset.percent = status.percent;
          var downloadButton =
            status.state === "missing" || status.state === "error"
              ? '<button type="button" class="btn btn-secondary speech-download-btn" ' +
                'data-url="/speech/tts/voice/download?locale=' + encodeURIComponent(locale) + "\">Download question voice</button>"
              : "";
          host.innerHTML = artifactStatusHTML(status) + downloadButton;
        }
        scheduleQuestionVoicePoll(target);
      })
      .catch(function () {
        /* transient */
      });
  }

  var speechPollTimer = null;
  var questionVoicePollTimer = null;

  function scheduleSpeechPoll(target) {
    if (speechPollTimer) {
      clearInterval(speechPollTimer);
      speechPollTimer = null;
    }
    var host = target.querySelector("#speech-model-status");
    if (!host || host.dataset.state !== "downloading") {
      return;
    }
    speechPollTimer = setInterval(function () {
      var size = selectedSpeechSize(target);
      var locale = selectedFormLocale(target);
      fetchJSON(
        "/speech/model/status?size=" + encodeURIComponent(size) + "&locale=" + encodeURIComponent(locale)
      )
        .then(function (status) {
          var current = target.querySelector("#speech-model-status");
          if (!current) {
            return;
          }
          current.dataset.state = status.state;
          renderSpeechModelArtifact(target);
        })
        .catch(function () {
          /* transient */
        });
    }, 1500);
  }

  function scheduleQuestionVoicePoll(target) {
    if (questionVoicePollTimer) {
      clearInterval(questionVoicePollTimer);
      questionVoicePollTimer = null;
    }
    var host = target.querySelector("#speech-tts-status");
    if (!host || host.dataset.state !== "downloading") {
      return;
    }
    questionVoicePollTimer = setInterval(function () {
      var locale = selectedFormLocale(target);
      fetchJSON("/speech/tts/status?locale=" + encodeURIComponent(locale))
        .then(function (status) {
          var current = target.querySelector("#speech-tts-status");
          if (!current) {
            return;
          }
          current.dataset.state = status.state;
          renderQuestionVoiceArtifact(target);
        })
        .catch(function () {
          /* transient */
        });
    }, 1500);
  }

  function applyPresetMode(container) {
    var presetSelect = container.querySelector("#llm_preset_id");
    var description = container.querySelector("#llm-preset-description");
    var apiKeyGroup = container.querySelector("#api-key-group");
    if (!presetSelect) {
      return;
    }
    var option = presetSelect.options[presetSelect.selectedIndex];
    if (!option) {
      return;
    }
    var apiKeyRequired = option.dataset.apiKeyRequired === "true";
    var acceptsAudio = option.dataset.acceptsAudioInput === "true";
    var audioHint =
      "This model accepts audio answers. Whisper must be installed for the selected speech model size.";
    if (description) {
      var base = option.dataset.description || "";
      description.textContent = acceptsAudio
        ? (base ? base + " — " : "") + audioHint
        : base;
    }
    if (apiKeyGroup) {
      apiKeyGroup.hidden = !apiKeyRequired;
    }
  }

  function collectConfigForm(container) {
    var locale = container.querySelector("#locale");
    var size = container.querySelector("input[name=\"speech_model_size\"]:checked");
    var voice = container.querySelector("#question_voice_enabled");
    var timeout = container.querySelector("#timeout");
    var preset = container.querySelector("#llm_preset_id");
    return {
      llm_preset_id: preset ? preset.value : "",
      api_key: container.querySelector("#api_key") ? container.querySelector("#api_key").value : "",
      timeout: timeout ? parseFloat(timeout.value) || 60 : 60,
      locale: locale ? locale.value : "en",
      speech_model_size: size ? size.value : "small",
      question_voice_enabled: voice ? voice.checked : false,
    };
  }

  function collectAddModelForm(container) {
    return {
      display_name: container.querySelector("#catalog_display_name").value,
      base_url: container.querySelector("#catalog_base_url").value,
      model: container.querySelector("#catalog_model").value,
      api_key: container.querySelector("#catalog_api_key").value,
      api_key_required: container.querySelector("#catalog_api_key_required").checked,
      accepts_audio_input: container.querySelector("#catalog_accepts_audio_input").checked,
    };
  }

  function renderConfigPage(container, data) {
    container.innerHTML = buildConfigFormHTML(data);
    applyPresetMode(container);
    renderSpeechModelArtifact(container);
    renderQuestionVoiceArtifact(container);

    var presetSelect = container.querySelector("#llm_preset_id");
    if (presetSelect) {
      presetSelect.addEventListener("change", function () {
        applyPresetMode(container);
      });
    }
    container.querySelectorAll('input[name="speech_model_size"]').forEach(function (radio) {
      radio.addEventListener("change", function () {
        renderSpeechModelArtifact(container);
      });
    });
    container.querySelector("#locale").addEventListener("change", function () {
      renderSpeechModelArtifact(container);
      renderQuestionVoiceArtifact(container);
    });

    container.querySelector("#config-save-btn").addEventListener("click", function (event) {
      event.preventDefault();
      var btn = event.target;
      btn.disabled = true;
      postJSON("/api/config", collectConfigForm(container))
        .then(function (result) {
          renderConfigPage(container, result.page);
        })
        .catch(function (err) {
          btn.disabled = false;
          container.insertAdjacentHTML(
            "beforeend",
            errorCard(errMessage(err, "Could not save configuration."))
          );
        });
    });

    container.querySelector("#config-test-btn").addEventListener("click", function (event) {
      event.preventDefault();
      var btn = event.target;
      btn.disabled = true;
      postJSON("/api/config/test", collectConfigForm(container))
        .then(function (result) {
          btn.disabled = false;
          var html = result.success
            ? alertSuccess(result.message)
            : alertError(result.message);
          var target = container.querySelector(".alert");
          var inserted = document.createElement("div");
          inserted.innerHTML = html;
          if (target) {
            container.replaceChild(inserted.firstChild, target);
          } else {
            container.insertBefore(inserted.firstChild, container.firstChild);
          }
        })
        .catch(function (err) {
          btn.disabled = false;
          container.insertAdjacentHTML(
            "beforeend",
            errorCard(errMessage(err, "Could not test connection."))
          );
        });
    });

    var removeBtn = container.querySelector("#config-remove-btn");
    if (removeBtn) {
      removeBtn.addEventListener("click", function () {
        if (!window.confirm("Remove configuration?")) {
          return;
        }
        removeBtn.disabled = true;
        fetchJSON("/api/config", { method: "DELETE" })
          .then(function (result) {
            renderConfigPage(container, result.page);
          })
          .catch(function (err) {
            removeBtn.disabled = false;
            container.insertAdjacentHTML(
              "beforeend",
              errorCard(errMessage(err, "Could not remove configuration."))
            );
          });
      });
    }

    container.querySelector("#add-model-form").addEventListener("submit", function (event) {
      event.preventDefault();
      var btn = container.querySelector("#add-model-form button[type=\"submit\"]");
      btn.disabled = true;
      postJSON("/api/config/llm-models", collectAddModelForm(container))
        .then(function (result) {
          /* The returned page is used to re-render the config form. */
          if (result.page) {
            renderConfigPage(container, result.page);
          }
        })
        .catch(function (err) {
          btn.disabled = false;
          container.insertAdjacentHTML(
            "beforeend",
            errorCard(errMessage(err, "Could not add model."))
          );
        });
    });

    container.addEventListener("click", function (event) {
      var target = event.target;
      if (!target || typeof target.closest !== "function") {
        return;
      }
      var btn = target.closest(".speech-download-btn");
      if (!btn) {
        return;
      }
      btn.disabled = true;
      fetchJSON(btn.dataset.url, { method: "POST" })
        .then(function () {
          var panel = btn.closest(".card");
          if (panel && panel.querySelector("#speech-model-status")) {
            renderSpeechModelArtifact(panel);
          } else if (panel) {
            renderQuestionVoiceArtifact(panel);
          }
        })
        .catch(function () {
          btn.disabled = false;
        });
    });
  }

  pages.config = function (container) {
    fetchJSON("/api/config")
      .then(function (data) {
        renderConfigPage(container, data);
      })
      .catch(function (err) {
        container.innerHTML = errorCard(errMessage(err, "Could not load configuration."));
      });
  };

  /* ------------------------------------------------------------------ *
   * Setup / New Interview page (multi-track wizard).
   * ------------------------------------------------------------------ */

  var SETUP_STORAGE_KEY = "grillkit_setup_wizard";
  var SETUP_SUBMITTED_KEY = "grillkit_setup_wizard_submitted";

  var SETUP_MODE_LABELS = {
    theory_only: "Theory only",
    coding_only: "Coding only",
    theory_then_coding: "Theory, then coding",
    coding_then_theory: "Coding, then theory",
  };

  function setupFormatTopic(slug) {
    return slug.charAt(0).toUpperCase() + slug.slice(1).replace(/-/g, " ");
  }

  function setupFormatLevel(level) {
    return level.charAt(0).toUpperCase() + level.slice(1);
  }

  function setupSelectedMode(root) {
    var checked = root.querySelector(".session-mode-radio:checked");
    return checked ? checked.value : "theory_only";
  }

  function setupBranchEnabled(mode, branch) {
    if (mode === "theory_only") {
      return branch === "theory";
    }
    if (mode === "coding_only") {
      return branch === "coding";
    }
    return true;
  }

  function setupStepSequence(root) {
    var mode = setupSelectedMode(root);
    var sections = [];
    if (mode === "theory_only") {
      sections.push("theory");
    } else if (mode === "coding_only") {
      sections.push("coding");
    } else if (mode === "theory_then_coding") {
      sections.push("theory", "coding");
    } else {
      sections.push("coding", "theory");
    }
    return ["mode"].concat(sections, ["review"]);
  }

  function setupStepLabel(stepId) {
    if (stepId === "mode") {
      return "Mode";
    }
    if (stepId === "theory") {
      return "Theory";
    }
    if (stepId === "coding") {
      return "Coding";
    }
    return "Review";
  }

  function setupSelectedTheoryTopics(root) {
    var count = 0;
    root.querySelectorAll(".theory-track-block").forEach(function (block) {
      var enable = block.querySelector(".track-enable");
      if (enable && enable.checked) {
        block.querySelectorAll(".topic-checkbox:checked").forEach(function () {
          count += 1;
        });
      }
    });
    return count;
  }

  function setupSelectedCodingTopics(root) {
    var count = 0;
    root.querySelectorAll(".coding-track-block").forEach(function (block) {
      var enable = block.querySelector(".coding-track-enable");
      if (enable && enable.checked) {
        block.querySelectorAll(".coding-topic-checkbox:checked").forEach(function () {
          count += 1;
        });
      }
    });
    return count;
  }

  function setupLinkTopics(block) {
    var prefix = block.classList.contains("theory-track-block") ? "" : "coding-";
    var levelSelect = block.querySelector("." + prefix + "track-level");
    var topicList = block.querySelector(".setup-topic-list");
    var track = block.dataset.track;
    if (!levelSelect || !topicList) {
      return Promise.resolve();
    }
    var level = levelSelect.value;
    var url = prefix
      ? "/api/setup/coding-options?track=" + encodeURIComponent(track) + "&level=" + encodeURIComponent(level)
      : "/api/setup/options?track=" + encodeURIComponent(track) + "&level=" + encodeURIComponent(level);
    var checkboxClass = prefix ? "coding-topic-checkbox" : "topic-checkbox";
    var checked = {};
    topicList.querySelectorAll("." + checkboxClass + ":checked").forEach(function (cb) {
      checked[cb.value] = true;
    });
    return fetchJSON(url)
      .then(function (data) {
        var categories = data.categories || [];
        topicList.innerHTML = "";
        categories.forEach(function (cat) {
          var label = document.createElement("label");
          label.className = "setup-topic-item";
          var input = document.createElement("input");
          input.type = "checkbox";
          input.className = checkboxClass;
          input.value = cat;
          input.dataset.track = track;
          if (checked[cat]) {
            input.checked = true;
          }
          input.addEventListener("change", onSetupFormChange);
          label.appendChild(input);
          label.appendChild(document.createTextNode(" " + setupFormatTopic(cat)));
          topicList.appendChild(label);
        });
      })
      .catch(function () {
        /* keep existing topics on load failure */
      });
  }

  var currentSetupWizard = null;

  function onSetupFormChange() {
    if (currentSetupWizard) {
      currentSetupWizard.onChange();
    }
  }

  function setupTrackSectionHTML(prefix, section) {
    var track = section.slug;
    var levelId = (prefix ? "coding-level-" : "level-") + track;
    var enableClass = prefix ? "coding-track-enable" : "track-enable";
    var levelClass = prefix ? "coding-track-level" : "track-level";
    var topicClass = prefix ? "coding-topic-checkbox" : "topic-checkbox";
    var levels = section.levels
      .map(function (lvl) {
        var selected = lvl === section.default_level ? " selected" : "";
        return '<option value="' + escapeHtml(lvl) + '"' + selected + ">" +
          escapeHtml(setupFormatLevel(lvl)) + "</option>";
      })
      .join("");
    var topics = section.categories
      .map(function (cat) {
        return (
          '<label class="setup-topic-item">' +
          '<input type="checkbox" class="' + topicClass + '" value="' + escapeHtml(cat) + '" data-track="' + escapeHtml(track) + '"> ' +
          escapeHtml(setupFormatTopic(cat)) +
          "</label>"
        );
      })
      .join("");
    return (
      '<fieldset class="setup-track-block ' + (prefix ? "coding-track-block" : "theory-track-block") + '" data-track="' + escapeHtml(track) + '">' +
      '<legend class="setup-track-legend">' +
      '<label class="setup-track-toggle">' +
      '<input type="checkbox" class="' + enableClass + '" data-track="' + escapeHtml(track) + '"> ' +
      escapeHtml(section.label) +
      "</label></legend>" +
      '<div class="setup-track-body" hidden>' +
      '<div class="form-group">' +
      '<label class="form-label form-label-required" for="' + escapeHtml(levelId) + '">Difficulty level</label>' +
      '<select id="' + escapeHtml(levelId) + '" class="form-control ' + levelClass + '" data-track="' + escapeHtml(track) + '">' + levels + "</select>" +
      "</div>" +
      '<div class="form-group">' +
      '<p class="form-label form-label-required">Topics</p>' +
      '<div class="setup-topic-list" data-track="' + escapeHtml(track) + '">' + topics + "</div>" +
      "</div></div></fieldset>"
    );
  }

  function setupModeRadioHTML(mode, checked, disabled) {
    return (
      '<label class="setup-session-mode' + (disabled ? " setup-session-mode-disabled" : "") + '">' +
      '<input type="radio" name="session_mode" value="' + escapeHtml(mode.value) + '" class="session-mode-radio"' +
      (checked ? " checked" : "") + (disabled ? " disabled" : "") + ">" +
      '<span class="setup-session-mode-body">' +
      '<span class="setup-session-mode-title">' + escapeHtml(mode.label) + "</span>" +
      '<span class="setup-session-mode-description">' + escapeHtml(mode.description) + "</span>" +
      (mode.badge ? '<span class="setup-session-mode-badge">' + escapeHtml(mode.badge) + "</span>" : "") +
      "</span></label>"
    );
  }

  function buildSetupWizard(container, data) {
    var localeLabel = data.locale_label || "";
    var initialStep = data.initial_wizard_step || "mode";
    var hasError = Boolean(data.error);
    var currentStep = "mode";

    var html = '';
    if (data.error) {
      html += "<div class=\"alert alert-error\"><strong>Error:</strong> " + escapeHtml(data.error) + "</div>";
    }
    if (data.speech_model_banner && data.speech_model_status) {
      html += "<div class=\"alert alert-warning\">Speech model (" +
        escapeHtml(data.speech_model_status.model_display_name) +
        ") is not installed. " +
        '<a href="#/config">Download it in Configuration</a> to use voice input.</div>';
    }
    html +=
      '<div class="card">' +
      '<div class="card-header">' +
      '<h1 class="card-title">Interview Setup</h1>' +
      '<p class="card-subtitle">Configure your session step by step</p>' +
      "</div>" +
      '<div class="setup-wizard" id="setup-wizard">' +
      '<ol class="setup-wizard-stepper" id="setup-stepper" aria-label="Setup progress"></ol>' +
      '<form class="form" id="setup-form">' +
      '<div class="setup-wizard-step" data-wizard-step="mode">' +
      '<div class="form-group">' +
      '<p class="form-label form-label-required">Session mode</p>' +
      '<p class="form-hint">Choose which sections to include and in what order.</p>' +
      (data.coding_available ? "" : '<p class="form-hint">Coding modes require Judge0 (set CODING_ENABLED and run the coding profile).</p>') +
      '<div class="setup-session-modes" id="session-modes">' +
      (data.session_modes || []).map(function (mode) {
        return setupModeRadioHTML(mode, mode.value === "theory_only", !mode.enabled);
      }).join("") +
      "</div></div></div>" +
      '<div class="setup-wizard-step" data-wizard-step="theory" hidden>' +
      '<div class="form-group">' +
      '<p class="form-label form-label-required">Theory: question banks &amp; topics</p>' +
      '<p class="form-hint">Enable one or more tracks, pick a level per track, then select topics.</p>' +
      (!(data.track_sections || []).length ? '<p class="form-hint">No question banks found.</p>' : "") +
      '<div class="setup-track-sections" id="track-sections">' +
      (data.track_sections || []).map(function (s) { return setupTrackSectionHTML("", s); }).join("") +
      "</div></div>" +
      '<div class="form-group">' +
      '<label for="question_count" class="form-label">Number of theory questions</label>' +
      '<input type="number" name="question_count" id="question_count" class="form-control" value="5" min="' + (data.min_question_count || 1) + '" max="20">' +
      '<p class="form-hint" id="question-count-hint">How many questions in this session (1–20). Must be at least the number of selected topics.</p>' +
      "</div>" +
      '<div class="form-group">' +
      '<label class="form-label"><input type="checkbox" name="enable_question_timer" id="enable_question_timer" value="on"> Enable per-question timer</label>' +
      '<p class="form-hint">When time runs out, the current round scores 0 and the interview moves on.</p>' +
      "</div>" +
      '<div class="form-group" id="question-timer-minutes-group" hidden>' +
      '<label for="question_time_minutes" class="form-label">Minutes per question round</label>' +
      '<input type="number" name="question_time_minutes" id="question_time_minutes" class="form-control" value="3" min="1" max="60">' +
      '<p class="form-hint">Applies to each main question and each AI follow-up (1–60).</p>' +
      "</div></div>" +
      '<div class="setup-wizard-step" data-wizard-step="coding" hidden>' +
      '<div class="form-group">' +
      '<p class="form-label form-label-required">Coding: task banks &amp; topics</p>' +
      '<p class="form-hint">Enable tracks and topics from the coding task bank.</p>' +
      (!(data.coding_track_sections || []).length ? '<p class="form-hint">No coding task banks found.</p>' : "") +
      '<div class="setup-track-sections" id="coding-track-sections">' +
      (data.coding_track_sections || []).map(function (s) { return setupTrackSectionHTML("coding", s); }).join("") +
      "</div></div>" +
      '<div class="form-group">' +
      '<label for="coding_question_count" class="form-label">Number of coding tasks</label>' +
      '<input type="number" name="coding_question_count" id="coding_question_count" class="form-control" value="2" min="' + (data.min_coding_task_count || 1) + '" max="20">' +
      '<p class="form-hint" id="coding-count-hint">How many coding tasks in this session (1–20). Must be at least the number of selected topics.</p>' +
      "</div>" +
      '<div class="form-group">' +
      '<label class="form-label"><input type="checkbox" name="enable_coding_timer" id="enable_coding_timer" value="on"> Enable per-task timer</label>' +
      '<p class="form-hint">When time runs out, the current coding task scores 0 and the session moves on.</p>' +
      "</div>" +
      '<div class="form-group" id="coding-timer-minutes-group" hidden>' +
      '<label for="coding_time_minutes" class="form-label">Minutes per coding task</label>' +
      '<input type="number" name="coding_time_minutes" id="coding_time_minutes" class="form-control" value="10" min="1" max="120">' +
      '<p class="form-hint">Applies to each coding task and follow-up round (1–120).</p>' +
      "</div></div>" +
      '<div class="setup-wizard-step" data-wizard-step="review" hidden>' +
      '<div class="form-group">' +
      '<label class="form-label"><input type="checkbox" id="exclude_known" checked> Exclude questions I already know</label>' +
      '<p class="form-hint" id="exclude-known-hint">Known questions are skipped when building a new session. <a href="#/known-questions">Manage known questions</a></p>' +
      "</div>" +
      '<div class="form-group">' +
      '<p class="form-label">Review your settings</p>' +
      '<p class="form-hint">Confirm everything looks right, then start the interview.</p>' +
      '<div id="setup-review-summary" class="setup-review-summary"></div>' +
      "</div></div>" +
      '<div class="divider"></div>' +
      '<div class="button-group setup-wizard-nav">' +
      '<button type="button" class="btn btn-outline" id="setup-wizard-back" hidden>Back</button>' +
      '<button type="button" class="btn btn-primary" id="setup-wizard-next">Next</button>' +
      '<button type="submit" class="btn btn-primary" id="setup-submit" hidden>Start Interview</button>' +
      '<a href="#/dashboard" class="btn btn-outline">Cancel</a>' +
      "</div></form></div></div>";

    container.innerHTML = html;

    var stepper = container.querySelector("#setup-stepper");
    var form = container.querySelector("#setup-form");
    var nextBtn = container.querySelector("#setup-wizard-next");
    var backBtn = container.querySelector("#setup-wizard-back");
    var submitBtn = container.querySelector("#setup-submit");
    var wizardNav = container.querySelector(".setup-wizard-nav");
    var reviewSummary = container.querySelector("#setup-review-summary");
    var questionCountInput = container.querySelector("#question_count");
    var questionCountHint = container.querySelector("#question-count-hint");
    var codingCountInput = container.querySelector("#coding_question_count");
    var codingCountHint = container.querySelector("#coding-count-hint");
    var timerCheckbox = container.querySelector("#enable_question_timer");
    var timerMinutesGroup = container.querySelector("#question-timer-minutes-group");
    var codingTimerCheckbox = container.querySelector("#enable_coding_timer");
    var codingTimerMinutesGroup = container.querySelector("#coding-timer-minutes-group");
    var excludeKnownCheckbox = container.querySelector("#exclude_known");

    function buildTheorySources() {
      var sources = [];
      container.querySelectorAll(".theory-track-block").forEach(function (block) {
        var track = block.dataset.track;
        var enabled = block.querySelector(".track-enable");
        if (!enabled || !enabled.checked) {
          return;
        }
        var levelSelect = block.querySelector(".track-level");
        var level = levelSelect ? levelSelect.value : "";
        var categories = [];
        block.querySelectorAll(".topic-checkbox:checked").forEach(function (cb) {
          categories.push(cb.value);
        });
        if (categories.length > 0) {
          sources.push({ track: track, level: level, categories: categories });
        }
      });
      return sources;
    }

    function buildCodingSources() {
      var sources = [];
      container.querySelectorAll(".coding-track-block").forEach(function (block) {
        var track = block.dataset.track;
        var enabled = block.querySelector(".coding-track-enable");
        if (!enabled || !enabled.checked) {
          return;
        }
        var levelSelect = block.querySelector(".coding-track-level");
        var level = levelSelect ? levelSelect.value : "";
        var categories = [];
        block.querySelectorAll(".coding-topic-checkbox:checked").forEach(function (cb) {
          categories.push(cb.value);
        });
        if (categories.length > 0) {
          sources.push({ track: track, level: level, categories: categories });
        }
      });
      return sources;
    }

    function buildSelection() {
      var mode = setupSelectedMode(container);
      var theoryEnabled = setupBranchEnabled(mode, "theory");
      var codingEnabled = setupBranchEnabled(mode, "coding");
      var theoryTimerSeconds = timerCheckbox && timerCheckbox.checked
        ? Math.max(1, Number(container.querySelector("#question_time_minutes").value)) * 60
        : null;
      var codingTimerSeconds = codingTimerCheckbox && codingTimerCheckbox.checked
        ? Math.max(1, Number(container.querySelector("#coding_time_minutes").value)) * 60
        : null;
      return {
        version: 2,
        session_mode: mode,
        exclude_known: !excludeKnownCheckbox || excludeKnownCheckbox.checked,
        theory: {
          enabled: theoryEnabled,
          question_count: theoryEnabled ? Number(questionCountInput.value) : 0,
          task_time_limit_seconds: theoryEnabled ? theoryTimerSeconds : null,
          sources: theoryEnabled ? buildTheorySources() : [],
        },
        coding: {
          enabled: codingEnabled,
          question_count: codingEnabled ? Number(codingCountInput.value) : 0,
          task_time_limit_seconds: codingEnabled ? codingTimerSeconds : null,
          sources: codingEnabled ? buildCodingSources() : [],
        },
      };
    }

    function theoryValid(selection) {
      if (!selection.theory.enabled) {
        return true;
      }
      var topics = setupSelectedTheoryTopics(container);
      if (topics === 0 || selection.theory.sources.length === 0) {
        return false;
      }
      var count = Number(questionCountInput.value);
      return count >= topics && count >= 1 && count <= 20;
    }

    function codingValid(selection) {
      if (!selection.coding.enabled) {
        return true;
      }
      var topics = setupSelectedCodingTopics(container);
      if (topics === 0 || selection.coding.sources.length === 0) {
        return false;
      }
      var count = Number(codingCountInput.value);
      return count >= topics && count >= 1 && count <= 20;
    }

    function validateStep(stepId) {
      if (stepId === "mode") {
        return Boolean(container.querySelector(".session-mode-radio:checked"));
      }
      var selection = buildSelection();
      if (stepId === "theory") {
        return theoryValid(selection);
      }
      if (stepId === "coding") {
        return codingValid(selection);
      }
      return theoryValid(selection) && codingValid(selection);
    }

    function syncTimerFields() {
      if (timerCheckbox && timerMinutesGroup) {
        timerMinutesGroup.hidden = !timerCheckbox.checked;
      }
    }

    function syncCodingTimerFields() {
      if (codingTimerCheckbox && codingTimerMinutesGroup) {
        codingTimerMinutesGroup.hidden = !codingTimerCheckbox.checked;
      }
    }

    function syncTheoryCountMin() {
      var topics = setupSelectedTheoryTopics(container);
      var minVal = Math.max(1, topics);
      questionCountInput.min = String(minVal);
      if (Number(questionCountInput.value) < minVal) {
        questionCountInput.value = String(minVal);
      }
      questionCountHint.textContent =
        "How many questions in this session (1–20). Must be at least " +
        minVal + " (one per selected topic).";
    }

    function syncCodingCountMin() {
      var topics = setupSelectedCodingTopics(container);
      var minVal = Math.max(1, topics);
      codingCountInput.min = String(minVal);
      if (Number(codingCountInput.value) < minVal) {
        codingCountInput.value = String(minVal);
      }
      codingCountHint.textContent =
        "How many coding tasks in this session (1–20). Must be at least " +
        minVal + " (one per selected topic).";
    }

    function renderStepper() {
      var sequence = setupStepSequence(container);
      stepper.innerHTML = "";
      var activeIndex = sequence.indexOf(currentStep);
      sequence.forEach(function (stepId, index) {
        var item = document.createElement("li");
        item.className = "setup-wizard-stepper-item";
        if (stepId === currentStep) {
          item.classList.add("setup-wizard-stepper-item-active");
        } else if (index < activeIndex) {
          item.classList.add("setup-wizard-stepper-item-complete");
        }
        var marker = document.createElement("span");
        marker.className = "setup-wizard-stepper-marker";
        marker.textContent = String(index + 1);
        var label = document.createElement("span");
        label.className = "setup-wizard-stepper-label";
        label.textContent = setupStepLabel(stepId);
        item.appendChild(marker);
        item.appendChild(label);
        stepper.appendChild(item);
      });
    }

    function updateNavButtons() {
      var sequence = setupStepSequence(container);
      var index = sequence.indexOf(currentStep);
      backBtn.hidden = index <= 0;
      var onReview = currentStep === "review";
      wizardNav.classList.toggle("setup-wizard-nav-review", onReview);
      nextBtn.hidden = onReview;
      submitBtn.hidden = !onReview;
      if (!onReview) {
        nextBtn.disabled = !validateStep(currentStep);
      } else {
        submitBtn.disabled = !validateStep("review");
      }
    }

    function formatTimer(seconds) {
      if (seconds === null || seconds === undefined) {
        return "Disabled";
      }
      return Math.round(seconds / 60) + " min per round";
    }

    function renderSectionSources(sources) {
      if (!sources.length) {
        return '<p class="setup-review-empty">No topics selected.</p>';
      }
      var items = sources.map(function (source) {
        var topics = source.categories.map(setupFormatTopic).join(", ");
        return "<li><strong>" + setupFormatTopic(source.track) + "</strong> (" +
          setupFormatLevel(source.level) + "): " + topics + "</li>";
      });
      return '<ul class="selection-sources-list">' + items.join("") + "</ul>";
    }

    function renderReviewCard(stepId, title, bodyHtml, editable) {
      var editButton = editable
        ? '<button type="button" class="btn btn-outline btn-sm setup-review-edit" data-edit-step="' + stepId + '">Edit</button>'
        : "";
      return '<div class="setup-review-card">' +
        '<div class="setup-review-card-header">' +
        '<h3 class="setup-review-card-title">' + title + "</h3>" +
        editButton + "</div>" +
        '<div class="setup-review-card-body">' + bodyHtml + "</div></div>";
    }

    function renderKnownExclusionNote() {
      var hint = container.querySelector("#exclude-known-hint");
      if (!hint) {
        return;
      }
      var linkHtml = '<a href="#/known-questions">Manage known questions</a>';
      if (!excludeKnownCheckbox || !excludeKnownCheckbox.checked) {
        hint.innerHTML = "Known questions will be included in this session. " + linkHtml;
        return;
      }
      fetchJSON("/known-questions")
        .then(function (known) {
          var count = (known.theory || []).length + (known.coding || []).length;
          var note = count === 0
            ? "No known questions saved yet. "
            : count + " known question" + (count === 1 ? "" : "s") + " will be excluded. ";
          hint.innerHTML = note + linkHtml;
        })
        .catch(function () {
          hint.innerHTML = "Known questions are skipped when building a new session. " + linkHtml;
        });
    }

    function renderReviewSummary() {
      var selection = buildSelection();
      var mode = selection.session_mode;
      var html = renderReviewCard(
        "mode",
        "Session mode",
        "<p>" + (SETUP_MODE_LABELS[mode] || mode) + "</p>",
        true
      );
      if (selection.theory.enabled) {
        html += renderReviewCard(
          "theory",
          "Theory",
          "<p><strong>Questions:</strong> " + selection.theory.question_count + "</p>" +
          "<p><strong>Timer:</strong> " + formatTimer(selection.theory.task_time_limit_seconds) + "</p>" +
          "<p><strong>Topics:</strong></p>" + renderSectionSources(selection.theory.sources),
          true
        );
      }
      if (selection.coding.enabled) {
        html += renderReviewCard(
          "coding",
          "Coding",
          "<p><strong>Tasks:</strong> " + selection.coding.question_count + "</p>" +
          "<p><strong>Timer:</strong> " + formatTimer(selection.coding.task_time_limit_seconds) + "</p>" +
          "<p><strong>Topics:</strong></p>" + renderSectionSources(selection.coding.sources),
          true
        );
      }
      html += renderReviewCard(
        "mode",
        "Interview language",
        "<p>" + localeLabel + "</p>" +
        '<p class="form-hint">Change in <a href="#/config">Configuration</a>.</p>',
        false
      );
      if (selection.exclude_known) {
        html += renderReviewCard(
          "review",
          "Known questions",
          "<p>Exclude questions marked as known.</p>",
          false
        );
      }
      reviewSummary.innerHTML = html;
      renderKnownExclusionNote();
      reviewSummary.querySelectorAll(".setup-review-edit").forEach(function (button) {
        button.addEventListener("click", function () {
          showStep(button.dataset.editStep);
        });
      });
      submitBtn.disabled = !validateStep("review");
    }

    function showStep(stepId) {
      var sequence = setupStepSequence(container);
      if (sequence.indexOf(stepId) === -1) {
        stepId = sequence[0];
      }
      currentStep = stepId;
      container.querySelectorAll(".setup-wizard-step").forEach(function (panel) {
        panel.hidden = panel.dataset.wizardStep !== stepId;
      });
      renderStepper();
      updateNavButtons();
      if (stepId === "review") {
        renderReviewSummary();
      }
      saveWizardState();
    }

    function goNext() {
      var sequence = setupStepSequence(container);
      var index = sequence.indexOf(currentStep);
      if (index === -1 || index >= sequence.length - 1) {
        return;
      }
      if (!validateStep(currentStep)) {
        return;
      }
      showStep(sequence[index + 1]);
    }

    function goBack() {
      var sequence = setupStepSequence(container);
      var index = sequence.indexOf(currentStep);
      if (index <= 0) {
        return;
      }
      showStep(sequence[index - 1]);
    }

    function collectBranchState(prefix, enableClass, levelClass, topicClass) {
      var tracks = {};
      container.querySelectorAll("." + prefix + "-track-block").forEach(function (block) {
        var track = block.dataset.track;
        var enable = block.querySelector("." + enableClass);
        var levelSelect = block.querySelector("." + levelClass);
        var categories = [];
        block.querySelectorAll("." + topicClass + ":checked").forEach(function (cb) {
          categories.push(cb.value);
        });
        tracks[track] = {
          enabled: Boolean(enable && enable.checked),
          level: levelSelect ? levelSelect.value : "",
          categories: categories,
        };
      });
      return tracks;
    }

    function saveWizardState() {
      var state = {
        sessionMode: setupSelectedMode(container),
        theoryTracks: collectBranchState("theory", "track-enable", "track-level", "topic-checkbox"),
        codingTracks: collectBranchState(
          "coding",
          "coding-track-enable",
          "coding-track-level",
          "coding-topic-checkbox"
        ),
        questionCount: questionCountInput.value,
        codingQuestionCount: codingCountInput.value,
        theoryTimerEnabled: Boolean(timerCheckbox && timerCheckbox.checked),
        theoryTimerMinutes: container.querySelector("#question_time_minutes").value,
        codingTimerEnabled: Boolean(codingTimerCheckbox && codingTimerCheckbox.checked),
        codingTimerMinutes: container.querySelector("#coding_time_minutes").value,
        currentStepId: currentStep,
      };
      try {
        sessionStorage.setItem(SETUP_STORAGE_KEY, JSON.stringify(state));
      } catch (_e) {}
    }

    function clearWizardState() {
      try {
        sessionStorage.removeItem(SETUP_STORAGE_KEY);
      } catch (_e) {}
    }

    function markWizardSubmitted() {
      try {
        sessionStorage.setItem(SETUP_SUBMITTED_KEY, "1");
      } catch (_e) {}
    }

    function clearWizardSubmitted() {
      try {
        sessionStorage.removeItem(SETUP_SUBMITTED_KEY);
      } catch (_e) {}
    }

    function wasWizardSubmitted() {
      try {
        return sessionStorage.getItem(SETUP_SUBMITTED_KEY) === "1";
      } catch (_e) {
        return false;
      }
    }

    function restoreBranchState(prefix, tracks, enableClass, levelClass, topicClass) {
      container.querySelectorAll("." + prefix + "-track-block").forEach(function (block) {
        var track = block.dataset.track;
        var saved = tracks[track];
        if (!saved) {
          return;
        }
        var enable = block.querySelector("." + enableClass);
        var body = block.querySelector(".setup-track-body");
        var levelSelect = block.querySelector("." + levelClass);
        if (enable) {
          enable.checked = saved.enabled;
        }
        if (body) {
          body.hidden = !saved.enabled;
        }
        if (levelSelect && saved.level) {
          levelSelect.value = saved.level;
        }
        var wanted = {};
        (saved.categories || []).forEach(function (c) {
          wanted[c] = true;
        });
        if (saved.enabled) {
          setupLinkTopics(block).then(function () {
            block.querySelectorAll("." + topicClass).forEach(function (cb) {
              cb.checked = Boolean(wanted[cb.value]);
            });
            syncTheoryCountMin();
            syncCodingCountMin();
            updateNavButtons();
          });
        } else {
          block.querySelectorAll("." + topicClass).forEach(function (cb) {
            cb.checked = Boolean(wanted[cb.value]);
          });
        }
      });
    }

    function restoreWizardState() {
      var raw = null;
      try {
        raw = sessionStorage.getItem(SETUP_STORAGE_KEY);
      } catch (_e) {
        return false;
      }
      if (!raw) {
        return false;
      }
      var state = null;
      try {
        state = JSON.parse(raw);
      } catch (_e) {
        return false;
      }
      var modeRadio = container.querySelector('.session-mode-radio[value="' + state.sessionMode + '"]');
      if (modeRadio && !modeRadio.disabled) {
        modeRadio.checked = true;
      }
      restoreBranchState("theory", state.theoryTracks || {}, "track-enable", "track-level", "topic-checkbox");
      restoreBranchState(
        "coding",
        state.codingTracks || {},
        "coding-track-enable",
        "coding-track-level",
        "coding-topic-checkbox"
      );
      if (state.questionCount) {
        questionCountInput.value = state.questionCount;
      }
      if (state.codingQuestionCount) {
        codingCountInput.value = state.codingQuestionCount;
      }
      if (timerCheckbox) {
        timerCheckbox.checked = Boolean(state.theoryTimerEnabled);
      }
      if (state.theoryTimerMinutes) {
        container.querySelector("#question_time_minutes").value = state.theoryTimerMinutes;
      }
      if (codingTimerCheckbox) {
        codingTimerCheckbox.checked = Boolean(state.codingTimerEnabled);
      }
      if (state.codingTimerMinutes) {
        container.querySelector("#coding_time_minutes").value = state.codingTimerMinutes;
      }
      syncTimerFields();
      syncCodingTimerFields();
      syncTheoryCountMin();
      syncCodingCountMin();
      return state;
    }

    container.querySelectorAll(".theory-track-block").forEach(function (block) {
      var enable = block.querySelector(".track-enable");
      var body = block.querySelector(".setup-track-body");
      var levelSelect = block.querySelector(".track-level");
      if (enable && body) {
        enable.addEventListener("change", function () {
          body.hidden = !enable.checked;
          onSetupFormChange();
        });
      }
      if (levelSelect) {
        levelSelect.addEventListener("change", function () {
          setupLinkTopics(block).then(onSetupFormChange);
        });
      }
      block.querySelectorAll(".topic-checkbox").forEach(function (cb) {
        cb.addEventListener("change", onSetupFormChange);
      });
    });

    container.querySelectorAll(".coding-track-block").forEach(function (block) {
      var enable = block.querySelector(".coding-track-enable");
      var body = block.querySelector(".setup-track-body");
      var levelSelect = block.querySelector(".coding-track-level");
      if (enable && body) {
        enable.addEventListener("change", function () {
          body.hidden = !enable.checked;
          onSetupFormChange();
        });
      }
      if (levelSelect) {
        levelSelect.addEventListener("change", function () {
          setupLinkTopics(block).then(onSetupFormChange);
        });
      }
      block.querySelectorAll(".coding-topic-checkbox").forEach(function (cb) {
        cb.addEventListener("change", onSetupFormChange);
      });
    });

    container.querySelectorAll(".session-mode-radio").forEach(function (radio) {
      radio.addEventListener("change", function () {
        var sequence = setupStepSequence(container);
        if (sequence.indexOf(currentStep) === -1) {
          showStep("mode");
        } else {
          renderStepper();
          updateNavButtons();
        }
        onSetupFormChange();
      });
    });

    questionCountInput.addEventListener("input", onSetupFormChange);
    codingCountInput.addEventListener("input", onSetupFormChange);
    if (timerCheckbox) {
      timerCheckbox.addEventListener("change", function () {
        syncTimerFields();
        onSetupFormChange();
      });
    }
    if (codingTimerCheckbox) {
      codingTimerCheckbox.addEventListener("change", function () {
        syncCodingTimerFields();
        onSetupFormChange();
      });
    }
    container.querySelector("#question_time_minutes").addEventListener("input", onSetupFormChange);
    container.querySelector("#coding_time_minutes").addEventListener("input", onSetupFormChange);
    if (excludeKnownCheckbox) {
      excludeKnownCheckbox.addEventListener("change", function () {
        if (currentStep === "review") {
          renderReviewSummary();
        }
        onSetupFormChange();
      });
    }

    nextBtn.addEventListener("click", goNext);
    backBtn.addEventListener("click", goBack);

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var selection = buildSelection();
      if (!theoryValid(selection) || !codingValid(selection)) {
        showStep("review");
        renderReviewSummary();
        return;
      }
      markWizardSubmitted();
      submitBtn.disabled = true;
      postJSON("/api/setup", {
        selection_json: JSON.stringify(selection),
        question_count: selection.theory.enabled ? selection.theory.question_count : 0,
        coding_question_count: selection.coding.enabled ? selection.coding.question_count : 0,
        enable_question_timer: Boolean(selection.theory.task_time_limit_seconds),
        question_time_minutes: selection.theory.task_time_limit_seconds
          ? Math.round(selection.theory.task_time_limit_seconds / 60)
          : 3,
        enable_coding_timer: Boolean(selection.coding.task_time_limit_seconds),
        coding_time_minutes: selection.coding.task_time_limit_seconds
          ? Math.round(selection.coding.task_time_limit_seconds / 60)
          : 10,
      })
        .then(function (result) {
          if (result && result.redirect) {
            clearWizardState();
            navigateTo(result.redirect);
            return;
          }
          submitBtn.disabled = false;
          if (result && result.error) {
            container.insertAdjacentHTML(
              "beforeend",
              errorCard(errMessage(result.error, "Could not start the interview."))
            );
          }
        })
        .catch(function (err) {
          submitBtn.disabled = false;
          container.insertAdjacentHTML(
            "beforeend",
            errorCard(errMessage(err, "Could not start the interview."))
          );
        });
    });

    var wizard = {
      onChange: function () {
        syncTheoryCountMin();
        syncCodingCountMin();
        updateNavButtons();
        if (currentStep === "review") {
          renderReviewSummary();
        } else {
          saveWizardState();
        }
      },
    };

    var restored = restoreWizardState();
    var startStep = initialStep;
    if (hasError && restored) {
      startStep = "review";
    } else if (restored && restored.currentStepId) {
      var seq = setupStepSequence(container);
      if (seq.indexOf(restored.currentStepId) !== -1) {
        startStep = restored.currentStepId;
      }
    }
    if (wasWizardSubmitted()) {
      clearWizardSubmitted();
      clearWizardState();
    }
    showStep(startStep);
    syncTimerFields();
    syncCodingTimerFields();
    return wizard;
  }

  pages.setup = function (container) {
    currentSetupWizard = null;
    fetchJSON("/api/setup")
      .then(function (data) {
        if (!data.configured) {
          window.location.hash = "#/config";
          return;
        }
        currentSetupWizard = buildSetupWizard(container, data);
      })
      .catch(function (err) {
        container.innerHTML = errorCard(errMessage(err, "Could not load the setup page."));
      });
  };

  /* ------------------------------------------------------------------ *
   * Interview page (theory + coding phases).
   * ------------------------------------------------------------------ */

  var interviewModules = {
    theory: [
      "/static/js/known_questions.js",
      "/static/js/session_phases.js",
      "/static/js/interview_timer.js",
      "/static/js/interview_session.js",
      "/static/js/dictation.js",
    ],
    codingBase: [
      "/static/js/known_questions.js",
      "/static/js/session_phases.js",
      "/static/js/coding_editor.js",
    ],
    codingLive: ["/static/js/coding_complete.js", "/static/js/coding_session.js"],
  };

  function interviewStatusBadge(status) {
    var cap = status ? status.charAt(0).toUpperCase() + status.slice(1) : "";
    return '<span id="interview-status">' + escapeHtml(cap) + "</span>";
  }

  function interviewAnswerHtml(answer, interviewStatus, questionVoiceEnabled) {
    var showQuestion =
      answer.answer_text !== null ||
      answer.answer_text === "" ||
      (answer.id === answer.id); // render every answer round
    if (!showQuestion) {
      return "";
    }
    var html =
      '<div class="chat-message question" data-question-id="' +
      escapeHtml(answer.question_id) +
      '" data-round="' +
      escapeHtml(answer.round) +
      '" data-answer-id="' +
      escapeHtml(answer.id) +
      '">' +
      '<div class="chat-bubble question-bubble">' +
      '<div class="question-bubble-header">' +
      '<span class="question-bubble-label"><strong>Q' +
      escapeHtml(answer.order) +
      ":</strong>";
    if (answer.round > 0) {
      html += " <em>(follow-up)</em>";
    }
    html += "</span>";
    if (questionVoiceEnabled) {
      html +=
        '<button type="button" class="btn btn-sm btn-outline btn-question-play"' +
        ' data-answer-id="' +
        escapeHtml(answer.id) +
        '" aria-label="Play question" title="Play question" aria-pressed="false">Play</button>';
    }
    if (interviewStatus === "active" && answer.round === 0) {
      html +=
        '<button type="button" class="btn btn-sm btn-outline known-question-toggle known-question-toggle--interview"' +
        ' data-branch="theory" data-item-id="' +
        escapeHtml(answer.question_id) +
        '">I know this</button>';
    }
    html +=
      '</div><div class="question-bubble-body">' + escapeHtml(answer.question_text);
    if (answer.question_code) {
      html +=
        '<pre class="code-block"><code>' +
        escapeHtml(answer.question_code) +
        "</code></pre>";
    }
    html += "</div></div></div>";

    if (answer.answer_text !== null) {
      html +=
        '<div class="chat-message answer" data-question-id="' +
        escapeHtml(answer.question_id) +
        '" data-round="' +
        escapeHtml(answer.round) +
        '">' +
        '<div class="chat-bubble answer-bubble"><strong>You:</strong> ' +
        escapeHtml(answer.answer_text) +
        "</div></div>";
    }
    return html;
  }

  function interviewMetaDl(data) {
    var codingProgress =
      data.coding && data.coding.complete
        ? "All coding tasks submitted"
        : data.coding && data.coding.current_task
          ? "Task " +
            (data.coding.completed_tasks + 1) +
            " of " +
            data.coding.task_count
          : data.coding
            ? "Task " + data.coding.completed_tasks + " of " + data.coding.task_count
            : "";
    var theoryProgress =
      data.theory && data.theory.complete
        ? "All questions answered"
        : data.theory && data.theory.current_question
          ? "Question " +
            data.theory.current_question.order +
            " of " +
            data.interview.question_count
          : data.theory
            ? "All questions answered"
            : "";
    var timerHidden = data.question_timer_enabled ? "" : " hidden";
    return (
      '<dl class="meta-list">' +
      "<dt>Sources</dt>" +
      "<dd><ul class=\"selection-sources-list\">" +
      (data.selection_lines || [])
        .map(function (line) {
          return "<li>" + escapeHtml(line) + "</li>";
        })
        .join("") +
      "</ul></dd>" +
      "<dt>AI language</dt><dd>" +
      escapeHtml(data.locale_label) +
      "</dd>" +
      (data.session_mode
        ? '<dt>Session</dt><dd><span class="session-mode-badge">' +
          escapeHtml(data.session_mode_label) +
          "</span></dd>"
        : "") +
      (data.theory
        ? '<dt>Theory</dt><dd id="interview-progress">' +
          escapeHtml(theoryProgress) +
          "</dd>"
        : "") +
      (data.coding
        ? '<dt>Coding</dt><dd id="coding-progress">' +
          escapeHtml(codingProgress) +
          "</dd>"
        : "") +
      "<dt>Status</dt><dd>" +
      interviewStatusBadge(data.interview.status) +
      "</dd>" +
      '<dd id="interview-timer-row" class="interview-timer"' +
      timerHidden +
      ">" +
      '<span class="interview-timer-label">Timer</span>' +
      '<span id="interview-timer" class="interview-timer-display">—</span>' +
      "</dd>" +
      "</dl>"
    );
  }

  function interviewAlertsHtml(data) {
    var html = "";
    if (data.tts_voice_banner && data.tts_voice_status) {
      html += voiceBannerHtml(data);
    }
    if (data.speech_model_banner && data.speech_model_status) {
      html += speechBannerHtml(data);
    } else if (
      data.interview.status === "active" &&
      data.speech_model_status &&
      data.speech_model_status.state === "ready" &&
      !data.speech_model_status.loaded_in_memory
    ) {
      html +=
        '<div class="alert alert-warning">' +
        escapeHtml(data.speech_model_status.message) +
        ' <a href="/#/config">Open Configuration</a> to retry loading the speech model.</div>';
    }
    return html;
  }

  function interviewTheoryPanel(data) {
    var dictationEnabled =
      data.interview.status === "active" &&
      data.current_question &&
      data.speech_model_status &&
      data.speech_model_status.state === "ready";
    var audioAnswerEnabled = dictationEnabled && data.interview_model_accepts_audio;
    var showTheoryPanel = data.theory !== null && data.active_phase === "theory";
    var showCodingPanel = data.coding !== null && data.active_phase === "coding";

    var body =
      '<div class="interview-page">' +
      '<aside class="interview-sidebar">' +
      '<div id="interview-alerts">' +
      interviewAlertsHtml(data) +
      "</div>" +
      '<div class="interview-meta">' +
      '<h1 class="interview-title">' +
      escapeHtml(data.interview_title) +
      "</h1>" +
      interviewMetaDl(data) +
      "</div>" +
      '<div class="interview-actions" id="sidebar-actions">' +
      '<a href="/" class="btn btn-outline">Back to Dashboard</a>' +
      (data.interview.status === "active"
        ? '<button type="button" id="end-btn" class="btn btn-danger">End Interview</button>'
        : "") +
      "</div>" +
      "</aside>";

    body +=
      '<section class="interview-chat-panel" id="theory-panel"' +
      (showTheoryPanel ? "" : " hidden") +
      ' data-interview-id="' +
      escapeHtml(data.interview.id) +
      '"' +
      (data.question_voice_enabled
        ? ' data-question-voice-enabled="true"'
        : "") +
      ">" +
      '<div class="interview-chat" id="chat-container">';
    (data.answers || []).forEach(function (answer) {
      body += interviewAnswerHtml(answer, data.interview.status, data.question_voice_enabled);
    });
    body += "</div>";

    var phaseHandoff =
      data.interview.status === "active" &&
      data.theory &&
      data.theory.complete &&
      data.session_mode === "theory_then_coding" &&
      data.coding &&
      !data.coding.complete;
    if (phaseHandoff) {
      body +=
        '<div class="interview-composer interview-phase-handoff" id="answer-section">' +
        '<p class="composer-done text-muted">Theory section complete. Continue to the coding practice.</p>' +
        '<button type="button" class="btn btn-primary" id="theory-to-coding-btn">Continue to Coding</button>' +
        "</div>";
    } else if (data.interview.status === "active" && data.current_question) {
      var cq = data.current_question;
      body +=
        '<div class="interview-composer" id="answer-section"' +
        ' data-interview-id="' +
        escapeHtml(data.interview.id) +
        '"' +
        (data.question_voice_enabled ? ' data-question-voice-enabled="true"' : "") +
        (data.current_answer_id
          ? ' data-current-answer-id="' + escapeHtml(data.current_answer_id) + '"'
          : "") +
        (dictationEnabled ? ' data-dictation-enabled="true"' : "") +
        (audioAnswerEnabled ? ' data-audio-answer-enabled="true"' : "") +
        (data.question_timer_enabled ? ' data-question-timer-enabled="true"' : "") +
        ' data-current-round="' +
        escapeHtml(data.current_round) +
        '">' +
        '<textarea name="answer_text" id="answer_text" class="form-control composer-input" rows="4" required placeholder="Type your answer here..."></textarea>' +
        '<div class="composer-footer">';
      if (dictationEnabled) {
        body +=
          '<button type="button" id="dictation-mic-btn" class="btn btn-secondary btn-dictation" aria-label="Voice input" aria-pressed="false" title="Start voice input">Voice</button>' +
          '<span id="dictation-hint" class="dictation-hint" hidden>Listening… speak your answer</span>';
      }
      if (audioAnswerEnabled) {
        body +=
          '<button type="button" id="audio-record-btn" class="btn btn-secondary btn-audio-record" aria-label="Record audio answer" title="Record an audio answer">Record</button>' +
          '<button type="button" id="audio-cancel-btn" class="btn btn-secondary btn-audio-cancel" hidden aria-label="Cancel audio recording" title="Cancel recording">Cancel</button>' +
          '<button type="button" id="audio-send-btn" class="btn btn-secondary btn-audio-send" hidden aria-label="Send audio answer" title="Send recorded audio">Send audio</button>' +
          '<span id="audio-record-hint" class="audio-record-hint" hidden>Recording… click Cancel or Send audio</span>';
      }
      body +=
        '<button type="button" id="submit-btn" class="btn btn-primary">Submit Answer</button>' +
        "</div>" +
        '<div id="evaluating-indicator" class="evaluating-indicator" style="display:none;"><div class="spinner"></div><span>AI is evaluating your answer...</span></div>' +
        "</div>";
    }

    body += "</section></div>";
    return { body: body, dictationEnabled: dictationEnabled, audioAnswerEnabled: audioAnswerEnabled };
  }

  /* Voice / speech banner fragments (rendered inline for the SPA). */
  function voiceBannerHtml(data) {
    var st = data.tts_voice_status;
    var reason = data.tts_voice_banner.reason || "";
    var text =
      reason === "downloading"
        ? "Preparing question voice…"
        : reason === "missing_voice"
          ? "Question voice model is needed for playback."
          : st && st.state === "ready"
            ? "Question voice ready."
            : "Question voice unavailable.";
    return (
      '<div class="alert alert-info question-voice-banner"><span>' +
      escapeHtml(text) +
      '</span> <a href="/#/config">Open Configuration</a></div>'
    );
  }

  function speechBannerHtml(data) {
    var st = data.speech_model_status;
    var text =
      st && st.state === "downloading"
        ? "Downloading speech model…"
        : st && st.state === "ready" && st.loaded_in_memory
          ? "Speech model ready."
          : st && st.message
            ? st.message
            : "Speech model loading.";
    return (
      '<div class="alert alert-info speech-model-banner"><span>' +
      escapeHtml(text) +
      '</span> <a href="/#/config">Open Configuration</a></div>'
    );
  }

  function interviewCodingPanel(data) {
    var coding = data.coding || {};
    var currentTask = coding.current_task;
    var active = data.interview.status === "active";
    var body =
      '<div class="coding-session" id="coding-panel"' +
      ' data-interview-id="' +
      escapeHtml(data.interview.id) +
      '"' +
      (currentTask ? ' data-task-id="' + escapeHtml(currentTask.task_id) + '"' : "") +
      (coding.current_task_row_id
        ? ' data-task-row-id="' + escapeHtml(coding.current_task_row_id) + '"'
        : "") +
      ' data-round="' +
      escapeHtml(coding.current_round || 0) +
      '" data-task-timer-enabled="' +
      (coding.task_timer_enabled ? "true" : "false") +
      '" data-task-time-limit="' +
      (coding.task_time_limit_seconds != null ? coding.task_time_limit_seconds : "") +
      '" data-timer-remaining="' +
      (coding.timer_remaining_seconds != null ? coding.timer_remaining_seconds : "") +
      '" data-llm-timeout="' +
      escapeHtml(data.llm_request_timeout_seconds) +
      '" data-complete="' +
      (coding.complete ? "true" : "false") +
      '" data-task-count="' +
      escapeHtml(coding.task_count) +
      '" data-completed-tasks="' +
      escapeHtml(coding.completed_tasks) +
      '">' +
      '<header class="coding-session__header">' +
      '<div class="coding-session__heading">' +
      '<p class="coding-session__eyebrow">' +
      escapeHtml(data.session_mode_label) +
      " session</p>" +
      '<h1 class="coding-session__title">' +
      escapeHtml(data.interview_title) +
      "</h1>" +
      '<p class="coding-session__meta">' +
      '<span id="coding-progress">' +
      (coding.complete
        ? "All tasks submitted"
        : "Task " + (coding.completed_tasks + 1) + " of " + coding.task_count) +
      "</span>" +
      (data.selection_lines && data.selection_lines.length
        ? '<span class="coding-session__dot" aria-hidden="true">·</span><span>' +
          escapeHtml(data.selection_lines.join(" · ")) +
          "</span>"
        : "") +
      "</p></div>" +
      '<div class="coding-session__toolbar">' +
      '<div class="coding-session__timer" id="interview-timer-row"' +
      (coding.task_timer_enabled ? "" : " hidden") +
      ">" +
      '<span class="coding-session__timer-label">Time left</span>' +
      '<span id="interview-timer" class="coding-session__timer-value">—</span>' +
      "</div>" +
      '<a href="/" class="btn btn-outline btn-sm">Dashboard</a>' +
      (active
        ? '<button type="button" id="coding-end-btn" class="btn btn-danger btn-sm">End Interview</button>'
        : "") +
      "</div></header>";

    if (active && currentTask && !coding.complete) {
      var spec = currentTask.task_spec || {};
      body +=
        '<div class="coding-session__body">' +
        '<aside class="coding-session__brief">' +
        '<div class="coding-session__brief-card">' +
        '<div class="coding-session__brief-header">' +
        '<h2 class="coding-session__task-label" id="coding-task-title">Task ' +
        escapeHtml(currentTask.order) +
        (coding.current_round > 0 ? " · follow-up" : "") +
        "</h2>" +
        '<button type="button" id="coding-known-item-btn" class="btn btn-outline btn-sm known-question-toggle known-question-toggle--interview" data-branch="coding" data-item-id="' +
        escapeHtml(currentTask.task_id) +
        '"' +
        (coding.current_round > 0 ? " hidden" : "") +
        ">I know this</button>" +
        "</div>" +
        '<div class="coding-session__assignment" id="coding-task-prompt">' +
        escapeHtml(currentTask.prompt_text) +
        "</div></div></aside>" +
        '<div class="coding-session__workspace" id="coding-workspace">' +
        '<div class="coding-session__editor-shell" id="coding-editor-wrap">' +
        '<div class="coding-session__editor-bar">' +
        '<span class="coding-session__editor-label">Solution</span>' +
        '<span class="coding-session__language">' +
        escapeHtml(spec.language || "python") +
        "</span></div>" +
        '<div id="coding-editor" class="coding-editor" aria-label="Code editor"></div>' +
        '<textarea id="coding-explanation-input" class="form-control coding-explanation-input" rows="3" hidden placeholder="Explain your approach or changes..."></textarea>' +
        "</div></div></div>" +
        '<section class="coding-session__runs" id="coding-runs-panel" hidden aria-live="polite">' +
        '<div class="coding-session__runs-header"><span>Run results</span>' +
        '<button type="button" id="coding-runs-toggle" class="coding-session__runs-toggle" aria-expanded="false">Show</button></div>' +
        '<div class="coding-session__output" id="coding-output"></div></section>' +
        '<footer class="coding-session__footer">' +
        '<div id="coding-evaluating-indicator" class="evaluating-indicator coding-session__evaluating" hidden><div class="spinner"></div><span>AI is reviewing your solution…</span></div>' +
        '<div class="coding-session__footer-actions">' +
        '<button type="button" id="coding-run-btn" class="btn btn-secondary">Run tests</button>' +
        '<button type="button" id="coding-submit-btn" class="btn btn-primary">Submit solution</button>' +
        "</div></footer>";
    } else if (coding.complete) {
      body +=
        '<section class="coding-session__done"><h2>All coding tasks submitted</h2>' +
        '<p class="text-muted">Use <strong>End Interview</strong> when you are ready for the final evaluation.</p></section>';
    }
    body += "</div>";
    return body;
  }

  function interviewSetBootstrap(data) {
    window.grillkitInterviewBootstrap = {
      interviewId: data.interview.id,
      status: data.interview.status,
      locale: data.interview.locale,
      questionCount: data.interview.question_count,
      questionTimerEnabled: !!data.question_timer_enabled,
      timeoutChatLabel: data.timeout_chat_label,
      questionTimeLimitSeconds:
        data.question_time_limit_seconds != null ? data.question_time_limit_seconds : null,
      llmRequestTimeoutSeconds: data.llm_request_timeout_seconds,
      currentRound: data.current_round || 0,
      currentQuestionId: data.current_question ? data.current_question.question_id : "",
      timerRemainingSeconds:
        data.timer_remaining_seconds != null ? data.timer_remaining_seconds : null,
      phase: data.active_phase,
    };
    window.grillkitSessionPhases = {
      sessionMode: data.session_mode,
      activePhase: data.active_phase,
      phaseOrder: data.phase_order || [],
      hasTheory: !!data.theory,
      hasCoding: !!data.coding,
      codingComplete: data.coding ? data.coding.complete : true,
      theoryComplete: data.theory ? data.theory.complete : true,
    };
    window.grillkitCodingBootstrap = {
      currentTask: data.coding && data.coding.current_task ? data.coding.current_task : null,
    };
  }

  function interviewLoadTheoryModules(data) {
    var sources = interviewModules.theory.slice();
    if (data.question_voice_enabled && data.interview.status === "active") {
      sources.push("/static/js/interview_voice.js");
    }
    if (data.interview_model_accepts_audio && data.interview.status === "active") {
      sources.push("/static/js/interview_audio_answer.js");
    }
    return loadScripts(sources);
  }

  function interviewLoadCodingModules(data) {
    var coding = data.coding || {};
    var sources = interviewModules.codingBase.slice();
    if (coding.task_timer_enabled && data.interview.status === "active") {
      sources.push("/static/js/interview_timer.js");
    }
    if (data.interview.status === "active") {
      sources.push("/static/js/coding_complete.js");
    }
    if (data.interview.status === "active" && coding.current_task && !coding.complete) {
      sources.push("/static/js/coding_session.js");
    }
    return loadScripts(sources);
  }

  function interviewCleanup() {
    delete window.grillkitInterviewBootstrap;
    delete window.grillkitSessionPhases;
    delete window.grillkitCodingBootstrap;
    delete window.grillkitOnTimerExpired;
    delete window.grillkitHandleInterviewEvent;
    delete window.grillkitGetSubmissionContext;
    delete window.grillkitSetSubmitting;
    delete window.grillkitShowAnswerBubble;
    delete window.grillkitSubmitInterviewAnswer;
    delete window.grillkitEndInterview;
    delete window.grillkitCodingSession;
    delete window.showError;
    window.isSubmitting = false;
  }

  function interviewRenderer(container, data) {
    if (data.redirect) {
      // Results and section reviews are SPA-migrated now; navigate to the hash route.
      navigateTo(data.redirect);
      return;
    }

    interviewSetBootstrap(data);
    if (data.active_phase === "coding") {
      container.innerHTML = interviewCodingPanel(data);
      interviewLoadCodingModules(data)
        .then(function () {
          if (window.KnownQuestions && window.KnownQuestions.initInterviewCoding) {
            window.KnownQuestions.initInterviewCoding();
          }
        })
        .catch(function (err) {
          container.insertAdjacentHTML(
            "beforeend",
            errorCard(errMessage(err, "Could not load the coding session."))
          );
        });
    } else {
      container.innerHTML = interviewTheoryPanel(data).body;
      interviewLoadTheoryModules(data).catch(function (err) {
        container.insertAdjacentHTML(
          "beforeend",
          errorCard(errMessage(err, "Could not load the interview session."))
        );
      });
    }
  }

  pages.interview = function (container, params) {
    interviewCleanup();
    if (!params || !params.id) {
      container.innerHTML = errorCard("Missing interview id.");
      return;
    }
    container.innerHTML =
      '<div class="card"><div class="card-header"><h1 class="card-title">Interview</h1></div>' +
      '<p class="muted">Loading…</p></div>';
    fetchJSON("/api/interview/" + encodeURIComponent(params.id))
      .then(function (data) {
        interviewRenderer(container, data);
      })
      .catch(function (err) {
        container.innerHTML = errorCard(errMessage(err, "Could not load the interview."));
      });
  };

  /* ------------------------------------------------------------------ *
   * Completed session pages: results hub + theory/coding section reviews.
   * ------------------------------------------------------------------ */

  /* Strip HTML from a value that would otherwise be escaped into markup. */
  function reviewListHtml(lines) {
    return (lines || [])
      .map(function (line) {
        return "<li>" + escapeHtml(line) + "</li>";
      })
      .join("");
  }

  function reviewSourcesMetaHtml(selectionLines) {
    return (
      '<dl class="meta-list">' +
      "<dt>Sources</dt>" +
      '<dd><ul class="selection-sources-list">' +
      reviewListHtml(selectionLines) +
      "</ul></dd>" +
      "</dl>"
    );
  }

  function sectionFeedbackHtml(feedback) {
    if (!feedback) {
      return "";
    }
    var html = '<section class="section-feedback">';
    if (feedback.section_feedback) {
      html +=
        '<div class="feedback-section"><h3>Section Feedback</h3><p>' +
        escapeHtml(feedback.section_feedback) +
        "</p></div>";
    }
    if (feedback.strengths_summary && feedback.strengths_summary.length) {
      html +=
        '<div class="feedback-section"><h3>Strengths</h3><ul>' +
        reviewListHtml(feedback.strengths_summary) +
        "</ul></div>";
    }
    if (feedback.topics_to_review && feedback.topics_to_review.length) {
      html +=
        '<div class="feedback-section"><h3>Topics to Review</h3><ul>' +
        reviewListHtml(feedback.topics_to_review) +
        "</ul></div>";
    }
    return html + "</section>";
  }

  function reviewSidebarHtml(data, feedback) {
    return (
      '<aside class="section-review__sidebar">' +
      reviewSourcesMetaHtml(data.selection_lines) +
      sectionFeedbackHtml(feedback) +
      "</aside>"
    );
  }

  function resultsScoreText(card) {
    if (card.skipped && card.max_score === 0) {
      return "Skipped";
    }
    if (card.skipped) {
      return card.score + " / " + card.max_score + " (incomplete)";
    }
    return card.score + " / " + card.max_score;
  }

  function resultsRenderer(container, data) {
    if (data.redirect) {
      navigateTo(data.redirect);
      return;
    }
    var fb = data.overall_feedback || {};
    var overall = "";
    if (fb.overall_feedback) {
      overall +=
        '<div class="feedback-section"><h3>Summary</h3><p>' +
        escapeHtml(fb.overall_feedback) +
        "</p></div>";
    }
    if (fb.strengths_summary && fb.strengths_summary.length) {
      overall +=
        '<div class="feedback-section"><h3>Strengths</h3><ul>' +
        reviewListHtml(fb.strengths_summary) +
        "</ul></div>";
    }
    if (fb.topics_to_review && fb.topics_to_review.length) {
      overall +=
        '<div class="feedback-section"><h3>Topics to Review</h3><ul>' +
        reviewListHtml(fb.topics_to_review) +
        "</ul></div>";
    }

    var cards = (data.section_cards || [])
      .map(function (card) {
        return (
          '<article class="section-result-card section-result-card--' +
          escapeHtml(card.section) +
          '">' +
          '<div class="section-result-card__head">' +
          "<h3>" + escapeHtml(card.label) + "</h3>" +
          '<p class="section-result-card__score">' +
          escapeHtml(resultsScoreText(card)) +
          "</p></div>" +
          '<p class="section-result-card__summary">' + escapeHtml(card.summary) + "</p>" +
          '<a href="' + escapeHtml(toHashPath(card.detail_url)) + '" class="btn btn-secondary btn-sm">View details</a>' +
          "</article>"
        );
      })
      .join("");
    var cardsSection =
      cards.length
        ? '<section class="session-results__sections"><h2>Sections</h2>' +
          '<div class="section-result-cards">' +
          cards +
          "</div></section>"
        : "";

    container.innerHTML =
      '<div class="card session-results">' +
      '<div class="card-header session-results__header">' +
      "<div>" +
      '<p class="session-results__eyebrow">' +
      escapeHtml(data.session_mode_label) +
      " session</p>" +
      '<h1 class="card-title">' +
      escapeHtml(data.interview_title) +
      "</h1>" +
      '<p class="card-subtitle">Completed · Score ' +
      escapeHtml(data.interview ? data.interview.score : "") +
      " / " +
      escapeHtml(data.max_score) +
      " · " +
      escapeHtml(data.locale_label) +
      "</p></div>" +
      '<a href="#/dashboard" class="btn btn-outline">Dashboard</a>' +
      "</div>" +
      '<div class="session-results__meta">' +
      reviewSourcesMetaHtml(data.selection_lines) +
      "</div>" +
      '<section class="session-results__overall"><h2>Overall Evaluation</h2>' +
      overall +
      "</section>" +
      cardsSection +
      "</div>";
  }

  pages.interviewResults = function (container, params) {
    if (!params || !params.id) {
      container.innerHTML = errorCard("Missing interview id.");
      return;
    }
    container.innerHTML =
      '<div class="card"><div class="card-header"><h1 class="card-title">Results</h1></div>' +
      '<p class="muted">Loading…</p></div>';
    fetchJSON("/api/interview/" + encodeURIComponent(params.id) + "/results")
      .then(function (data) {
        resultsRenderer(container, data);
      })
      .catch(function (err) {
        container.innerHTML = errorCard(errMessage(err, "Could not load the session results."));
      });
  };

  pages.interviewTheoryReview = function (container, params) {
    if (!params || !params.id) {
      container.innerHTML = errorCard("Missing interview id.");
      return;
    }
    container.innerHTML =
      '<div class="card"><div class="card-header"><h1 class="card-title">Theory Review</h1></div>' +
      '<p class="muted">Loading…</p></div>';
    fetchJSON("/api/interview/" + encodeURIComponent(params.id) + "/theory")
      .then(function (data) {
        theoryReviewRenderer(container, data);
      })
      .catch(function (err) {
        container.innerHTML = errorCard(errMessage(err, "Could not load the theory review."));
      });
  };

  pages.interviewCodingReview = function (container, params) {
    if (!params || !params.id) {
      container.innerHTML = errorCard("Missing interview id.");
      return;
    }
    container.innerHTML =
      '<div class="card"><div class="card-header"><h1 class="card-title">Coding Review</h1></div>' +
      '<p class="muted">Loading…</p></div>';
    fetchJSON("/api/interview/" + encodeURIComponent(params.id) + "/coding")
      .then(function (data) {
        codingReviewRenderer(container, data);
      })
      .catch(function (err) {
        container.innerHTML = errorCard(errMessage(err, "Could not load the coding review."));
      });
  };

  function theoryAnswerHtml(answer) {
    var html =
      '<div class="chat-message question" data-question-id="' +
      escapeHtml(answer.question_id) +
      '" data-round="' +
      escapeHtml(answer.round) +
      '">' +
      '<div class="chat-bubble question-bubble">' +
      '<div class="question-bubble-header">' +
      '<span class="question-bubble-label"><strong>Q' +
      escapeHtml(answer.order) +
      ":</strong>";
    if (answer.round > 0) {
      html += " <em>(follow-up)</em>";
    }
    html += "</span>";
    if (answer.round === 0) {
      html +=
        '<button type="button" class="btn btn-outline btn-sm known-question-toggle" ' +
        'data-branch="theory" data-item-id="' +
        escapeHtml(answer.question_id) +
        '">Mark as known</button>';
    }
    html += "</div>" + escapeHtml(answer.question_text);
    if (answer.question_code) {
      html +=
        '<pre class="code-block"><code>' +
        escapeHtml(answer.question_code) +
        "</code></pre>";
    }
    html += "</div></div>";

    html +=
      '<div class="chat-message answer" data-question-id="' +
      escapeHtml(answer.question_id) +
      '" data-round="' +
      escapeHtml(answer.round) +
      '">' +
      '<div class="chat-bubble answer-bubble"><strong>You:</strong> ' +
      escapeHtml(answer.answer_text) +
      "</div></div>";

    if (answer.score !== null || answer.feedback) {
      html += '<div class="chat-message feedback"><div class="chat-bubble feedback-bubble">';
      if (answer.score !== null) {
        html += "<strong>Score:</strong> " + escapeHtml(answer.score) + " / 5";
      }
      if (answer.feedback) {
        html += "<p>" + escapeHtml(answer.feedback) + "</p>";
      }
      html += "</div></div>";
    }
    return html;
  }

  function theoryReviewRenderer(container, data) {
    if (data.redirect) {
      navigateTo(data.redirect);
      return;
    }
    var chat = (data.answers || []).map(theoryAnswerHtml).join("");
    container.innerHTML =
      '<div class="section-review">' +
      '<header class="section-review__header">' +
      "<div>" +
      '<p class="section-review__eyebrow">Theory section</p>' +
      '<h1 class="section-review__title">' +
      escapeHtml(data.interview_title) +
      "</h1>" +
      '<p class="section-review__meta">Score ' +
      escapeHtml(data.section_score) +
      " / " +
      escapeHtml(data.section_max_score) +
      " · " +
      escapeHtml(data.locale_label) +
      "</p></div>" +
      '<div class="section-review__actions">' +
      '<a href="#/interview/' +
      encodeURIComponent(data.interview_id) +
      '/results" class="btn btn-outline">Back to Results</a>' +
      '<a href="#/dashboard" class="btn btn-outline">Dashboard</a>' +
      "</div></header>" +
      '<div class="section-review__layout">' +
      reviewSidebarHtml(data, data.section_feedback) +
      '<section class="section-review__main"><h2>Conversation History</h2>' +
      '<div class="interview-chat theory-review-chat">' +
      chat +
      "</div></section></div></div>";
    loadScript("/static/js/known_questions.js")
      .then(function () {
        if (window.KnownQuestions && window.KnownQuestions.initReviewButtons) {
          window.KnownQuestions.initReviewButtons("theory");
        }
      })
      .catch(function () {
        /* Known-question toggling is a progressive enhancement; ignore failures. */
      });
  }

  function codingRoundHtml(round, order) {
    var html =
      '<article class="coding-task-round">' +
      '<header class="coding-task-round__header"><h4>' +
      (round.round === 0
        ? "Initial submission"
        : "Follow-up round " + escapeHtml(round.round)) +
      "</h4>";
    if (round.score !== null) {
      html += '<span class="coding-task-round__score">' + escapeHtml(round.score) + " / 5</span>";
    }
    html += "</header>";
    if (round.round > 0 && round.prompt_text) {
      html +=
        '<div class="coding-task-round__prompt"><strong>Prompt:</strong> ' +
        escapeHtml(round.prompt_text) +
        "</div>";
    }
    html +=
      '<div class="coding-task-round__code"><h5>Submission</h5>' +
      '<pre class="code-block"><code>' +
      escapeHtml(round.submitted_code) +
      "</code></pre></div>";
    if (round.round === 0 && round.submit_test_summary) {
      html +=
        '<div class="coding-task-round__tests"><h5>Test results</h5>' +
        '<pre class="code-block code-block--compact"><code>' +
        escapeHtml(JSON.stringify(round.submit_test_summary, null, 2)) +
        "</code></pre></div>";
    }
    if (round.feedback) {
      html +=
        '<div class="coding-task-round__feedback"><h5>Feedback</h5><p>' +
        escapeHtml(round.feedback) +
        "</p></div>";
    }
    html += "</article>";
    void order;
    return html;
  }

  function codingTaskHtml(task) {
    var rounds = (task.rounds || []).map(codingRoundHtml).join("");
    return (
      '<details class="coding-task-panel">' +
      '<summary class="coding-task-panel__summary">' +
      '<span class="coding-task-panel__title">Task ' +
      escapeHtml(task.order) +
      " · " +
      escapeHtml(task.task_id) +
      "</span>" +
      '<span class="coding-task-panel__score">' +
      escapeHtml(task.total_score) +
      " / " +
      escapeHtml(task.max_score) +
      "</span></summary>" +
      '<div class="coding-task-panel__body">' +
      '<div class="coding-task-panel__actions">' +
      '<button type="button" class="btn btn-outline btn-sm known-question-toggle" ' +
      'data-branch="coding" data-item-id="' +
      escapeHtml(task.task_id) +
      '">Mark as known</button></div>' +
      '<div class="coding-task-panel__prompt"><h3>Assignment</h3><p>' +
      escapeHtml(task.initial_prompt) +
      "</p></div>" +
      rounds +
      "</div></details>"
    );
  }

  function codingReviewRenderer(container, data) {
    if (data.redirect) {
      navigateTo(data.redirect);
      return;
    }
    var tasks = (data.tasks || []).map(codingTaskHtml).join("");
    container.innerHTML =
      '<div class="section-review">' +
      '<header class="section-review__header">' +
      "<div>" +
      '<p class="section-review__eyebrow">Coding section</p>' +
      '<h1 class="section-review__title">' +
      escapeHtml(data.interview_title) +
      "</h1>" +
      '<p class="section-review__meta">Score ' +
      escapeHtml(data.section_score) +
      " / " +
      escapeHtml(data.section_max_score) +
      " · " +
      escapeHtml(data.locale_label) +
      "</p></div>" +
      '<div class="section-review__actions">' +
      '<a href="#/interview/' +
      encodeURIComponent(data.interview_id) +
      '/results" class="btn btn-outline">Back to Results</a>' +
      '<a href="#/dashboard" class="btn btn-outline">Dashboard</a>' +
      "</div></header>" +
      '<div class="section-review__layout section-review__layout--coding">' +
      reviewSidebarHtml(data, data.section_feedback) +
      '<section class="section-review__main"><h2>Coding Tasks</h2>' +
      '<div class="coding-task-accordion">' +
      tasks +
      "</div></section></div></div>";
    loadScript("/static/js/known_questions.js")
      .then(function () {
        if (window.KnownQuestions && window.KnownQuestions.initReviewButtons) {
          window.KnownQuestions.initReviewButtons("coding");
        }
      })
      .catch(function () {
        /* Known-question toggling is a progressive enhancement; ignore failures. */
      });
  }

  function unknownPage(container, params) {
    void params;
    container.innerHTML = "<p>Page not found.</p>";
  }

  /* ------------------------------------------------------------------ *
   * Router
   * ------------------------------------------------------------------ */

  /* Navigate to a server-provided app path, mapping it to the SPA hash route.
   * Server redirects use the same path structure as the SPA routes (e.g.
   * "/interview/{id}/results"), so we only need to prepend "#". */
  function navigateTo(path) {
    if (!path) {
      return;
    }
    if (path.indexOf("/#/") === 0) {
      // Already an SPA hash-form path (root + hash), e.g. "/#/config".
      window.location.hash = path.slice(1);
      return;
    }
    if (path.charAt(0) !== "/" || path.indexOf("/api/") === 0) {
      window.location.href = path;
      return;
    }
    // Map the server app-path (e.g. "/interview/{id}") to the SPA hash route so
    // we don't hit a 404 on the old server-rendered URL.
    window.location.hash = "#" + path;
  }

  /* Convert a server app-path (e.g. "/interview/{id}/results") into a SPA hash
   * route for use in href attributes. Non-app paths are returned unchanged. */
  function toHashPath(path) {
    if (typeof path !== "string" || path.charAt(0) !== "/") {
      return path;
    }
    return "#" + path;
  }

  function currentRoute() {
    var hash = window.location.hash || "#/dashboard";
    if (hash.charAt(0) === "#") {
      hash = hash.slice(1);
    }
    hash = hash.replace(/^\/+/, "");
    var parts = hash.split("/").filter(Boolean);
    var name = parts[0] || "dashboard";
    return { name: name, parts: parts, action: parts[2] || null };
  }

  /* The active interview session (theory/coding) renders full-screen; every other
   * page (dashboard, setup, config, reviews, results) uses the normal 1200px layout.
   * Toggle the container classes so navigation never leaves them stuck on and ends
   * up shrinking the content. */
  var interviewClass = "main-content--interview";
  var interviewContainerClass = "app-container--interview";

  function setInterviewLayout(enabled) {
    var container = view.parentElement;
    if (enabled) {
      view.classList.add(interviewClass);
      if (container) {
        container.classList.add(interviewContainerClass);
      }
    } else {
      view.classList.remove(interviewClass);
      if (container) {
        container.classList.remove(interviewContainerClass);
      }
    }
  }

  function render() {
    var route = currentRoute();

    var params = {};
    if (route.parts.length >= 2) {
      params.id = route.parts[1];
    }

    var handler;
    var fullScreen = false;
    if (route.name === "interview") {
      // Interview session page plus its completed sub-pages.
      if (route.action === "results") {
        handler = pages.interviewResults;
      } else if (route.action === "theory") {
        handler = pages.interviewTheoryReview;
      } else if (route.action === "coding") {
        handler = pages.interviewCodingReview;
      } else {
        // Active theory/coding session -> full screen.
        handler = pages.interview;
        fullScreen = true;
      }
    } else {
      handler = pages[route.name] || unknownPage;
    }

    setInterviewLayout(fullScreen);
    view.innerHTML = ""; // clear previous page

    Promise.resolve(handler(view, params)).catch(function (err) {
      view.innerHTML = errorCard(errMessage(err));
    });
  }

  /* ------------------------------------------------------------------ *
   * Theme toggle (shared with the legacy shells).
   * ------------------------------------------------------------------ */

  function initTheme() {
    var toggle = document.querySelector("[data-theme-toggle]");
    if (!toggle) {
      return;
    }
    toggle.addEventListener("click", function () {
      var root = document.documentElement;
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem("grillkit-theme", next);
      } catch (e) {}
    });
  }

  window.addEventListener("hashchange", render);
  window.addEventListener("DOMContentLoaded", function () {
    initTheme();
    render();
  });

  /* Exposed for page modules and tests. */
  window.GrillKit = {
    fetchJSON: fetchJSON,
    postJSON: postJSON,
    escapeHtml: escapeHtml,
    render: render,
  };
})();
