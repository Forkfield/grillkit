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
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
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
      var params =
        "branch=" + encodeURIComponent(branch) +
        "&item_id=" + encodeURIComponent(itemId);
      button.disabled = true;
      fetchJSON("/api/known-questions?" + params, {
        method: "DELETE",
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

  function buildPresetGroups(data) {
    var providers = data.llm_providers || [];
    var groups = providers
      .map(function (provider) {
        return {
          label: provider.display_name,
          models: (provider.models || []).map(function (entry) {
            return {
              id: entry.id,
              display_name: entry.display_name,
              model: entry.model,
              accepts_audio_input: entry.accepts_audio_input,
            };
          }),
        };
      })
      .filter(function (group) {
        return group.models.length > 0;
      });
    if (!groups.length && data.llm_presets && data.llm_presets.length) {
      groups = [
        {
          label: "Catalog",
          models: data.llm_presets.map(function (entry) {
            return {
              id: entry.id,
              display_name: entry.display_name,
              model: entry.model || entry.description || "",
              accepts_audio_input: entry.accepts_audio_input,
            };
          }),
        },
      ];
    }
    return groups;
  }

  function buildPresetOptionsHTML(groups, selectedId, query) {
    var needle = (query || "").trim().toLowerCase();
    var html = "";
    groups.forEach(function (group) {
      var options = group.models.filter(function (entry) {
        if (!needle) {
          return true;
        }
        var haystack = (
          entry.display_name + " " + entry.model + " " + group.label
        ).toLowerCase();
        return haystack.indexOf(needle) !== -1;
      });
      if (!options.length) {
        return;
      }
      html += '<optgroup label="' + escapeHtml(group.label) + '">';
      options.forEach(function (entry) {
        html +=
          '<option value="' + escapeHtml(entry.id) + '"' +
          (entry.id === selectedId ? " selected" : "") +
          ' data-description="' + escapeHtml(entry.model || "") + '"' +
          ' data-accepts-audio-input="' +
          (entry.accepts_audio_input ? "true" : "false") + '">' +
          escapeHtml(entry.display_name) +
          (entry.accepts_audio_input ? " (audio)" : "") +
          "</option>";
      });
      html += "</optgroup>";
    });
    if (!html) {
      return '<option value="">No models match this filter</option>';
    }
    return html;
  }

  function modelFormFieldsHTML(entry) {
    entry = entry || {};
    return (
      '<div class="form-row">' +
      '<label class="form-field"><span class="form-label">Display name</span>' +
      '<input type="text" name="display_name" class="form-control" required value="' +
      escapeHtml(entry.display_name || "") + '" placeholder="Work GPT-4o"></label>' +
      '<label class="form-field"><span class="form-label">Model name</span>' +
      '<input type="text" name="model" class="form-control" required value="' +
      escapeHtml(entry.model || "") + '" placeholder="gpt-4o"></label>' +
      "</div>" +
      '<label class="form-check"><input type="checkbox" name="accepts_audio_input"' +
      (entry.accepts_audio_input ? " checked" : "") +
      "> Accepts audio input</label>" +
      '<p class="form-hint">Use "Load models" on the provider to import the whole list at once; add a single model here when it is missing from the endpoint.</p>' +
      '<div class="inline-form-actions">' +
      '<button type="submit" class="btn btn-sm btn-primary">Save model</button>' +
      '<button type="button" class="btn btn-sm btn-secondary" data-form-cancel>Cancel</button>' +
      "</div>"
    );
  }

  function buildModelRowHTML(provider, entry) {
    return (
      '<div class="provider-model-row" data-model-id="' + escapeHtml(entry.id) + '">' +
      '<div class="provider-model-info">' +
      '<span class="provider-model-name">' + escapeHtml(entry.display_name) + "</span>" +
      '<span class="provider-model-meta">' + escapeHtml(entry.model) + "</span>" +
      "</div>" +
      '<div class="provider-model-actions">' +
      '<label class="provider-model-audio" title="Whether the model accepts audio answers">' +
      '<input type="checkbox" data-model-audio data-provider-id="' +
      escapeHtml(provider.id) + '" data-model-id="' + escapeHtml(entry.id) + '"' +
      (entry.accepts_audio_input ? " checked" : "") + "> audio</label>" +
      '<button type="button" class="btn btn-sm btn-secondary" data-model-edit="' +
      escapeHtml(entry.id) + '">Edit</button>' +
      '<button type="button" class="btn btn-sm btn-danger" data-model-delete="' +
      escapeHtml(entry.id) + '" data-provider-id="' + escapeHtml(provider.id) +
      '">Delete</button>' +
      "</div>" +
      '<form class="form provider-model-form" data-model-form="' + escapeHtml(entry.id) +
      '" data-provider-id="' + escapeHtml(provider.id) + '" hidden>' +
      modelFormFieldsHTML(entry) +
      "</form>" +
      "</div>"
    );
  }

  function buildProviderCardHTML(provider) {
    var models = provider.models || [];
    var rows = models.length
      ? models
          .map(function (entry) {
            return buildModelRowHTML(provider, entry);
          })
          .join("")
      : '<p class="provider-empty">No models yet — use "Load models" or add one below.</p>';
    return (
      '<div class="provider-card" data-provider-card="' + escapeHtml(provider.id) + '">' +
      '<div class="provider-card-header">' +
      '<div class="provider-card-info">' +
      '<h3 class="provider-card-title">' + escapeHtml(provider.display_name) + "</h3>" +
      '<p class="provider-card-url">' + escapeHtml(provider.base_url) + "</p>" +
      '<div class="provider-card-badges">' +
      (provider.has_api_key
        ? '<span class="badge badge-success">API key stored</span>'
        : '<span class="badge badge-muted">No API key</span>') +
      '<span class="badge badge-muted">' + models.length +
      (models.length === 1 ? " model" : " models") + "</span>" +
      (provider.discovery_error
        ? '<span class="badge badge-warning" title="' +
          escapeHtml(provider.discovery_error) + '">Discovery failed</span>'
        : "") +
      "</div></div>" +
      '<div class="provider-card-actions">' +
      '<button type="button" class="btn btn-sm btn-secondary" data-import-models="' +
      escapeHtml(provider.id) +
      '" title="Load the model list from the provider endpoint and add every new model">Load models</button>' +
      '<button type="button" class="btn btn-sm btn-secondary" data-provider-edit="' +
      escapeHtml(provider.id) + '">Edit</button>' +
      '<button type="button" class="btn btn-sm btn-danger" data-provider-delete="' +
      escapeHtml(provider.id) + '">Delete</button>' +
      "</div></div>" +
      (provider.discovery_error
        ? '<p class="provider-discovery-error">' +
          escapeHtml(provider.discovery_error) + "</p>"
        : "") +
      '<form class="form provider-edit-form" data-provider-edit-form="' +
      escapeHtml(provider.id) + '" hidden>' +
      '<div class="form-row">' +
      '<label class="form-field"><span class="form-label">Display name</span>' +
      '<input type="text" name="display_name" class="form-control" required value="' +
      escapeHtml(provider.display_name) + '"></label>' +
      '<label class="form-field"><span class="form-label">Base URL</span>' +
      '<input type="url" name="base_url" class="form-control" required value="' +
      escapeHtml(provider.base_url) + '"></label>' +
      "</div>" +
      '<label class="form-field"><span class="form-label">API key</span>' +
      '<input type="password" name="api_key" class="form-control" autocomplete="off" placeholder="' +
      (provider.has_api_key
        ? "Leave blank to keep the stored key"
        : "sk-… (leave blank for local servers)") +
      '"></label>' +
      (provider.has_api_key
        ? '<label class="form-check"><input type="checkbox" name="clear_api_key"> Remove stored API key</label>'
        : "") +
      '<div class="inline-form-actions">' +
      '<button type="submit" class="btn btn-sm btn-primary">Save provider</button>' +
      '<button type="button" class="btn btn-sm btn-secondary" data-form-cancel>Cancel</button>' +
      "</div></form>" +
      '<div class="provider-models">' + rows + "</div>" +
      '<div class="provider-card-footer">' +
      '<button type="button" class="btn btn-sm btn-secondary" data-model-add="' +
      escapeHtml(provider.id) + '">Add model</button></div>' +
      '<form class="form provider-model-form" data-model-form="" data-provider-id="' +
      escapeHtml(provider.id) + '" hidden>' +
      modelFormFieldsHTML(null) +
      "</form></div>"
    );
  }

  function buildConfigFormHTML(data, activeTab) {
    var config = data.config || {};
    var selectedPreset = data.selected_llm_preset_id;
    var showProvidersTab = activeTab === "providers";
    var presetGroups = buildPresetGroups(data);

    var presetOptions;
    if (presetGroups.length) {
      presetOptions =
        '<input type="search" id="llm-model-filter" class="form-control model-filter" ' +
        'placeholder="Filter models by name, model, or provider" autocomplete="off">' +
        '<select name="llm_preset_id" id="llm_preset_id" class="form-control" required>' +
        buildPresetOptionsHTML(presetGroups, selectedPreset, "") +
        '</select><p class="form-hint" id="llm-preset-description"></p>';
    } else {
      presetOptions =
        '<div class="alert alert-info">' +
        "No models in the catalog yet. Add a provider and a model on the " +
        '<a href="#/config/providers">Providers &amp; models</a> tab, ' +
        "then select it here." +
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
          '<div class="speech-model-size-option">' +
          '<label class="speech-model-size-option-main">' +
          '<input type="radio" name="speech_model_size" value="' + escapeHtml(size) + '"' +
          (checked ? " checked" : "") + ">" +
          '<span class="speech-model-size-option-title">' + escapeHtml(spec.display_name) + "</span>" +
          '<span class="speech-model-size-option-meta">~' + escapeHtml(spec.approx_download_mb) +
          " MB download &middot; " + escapeHtml(spec.ram_hint) + " RAM &middot; " +
          escapeHtml(spec.speed_hint) + " &middot; " + escapeHtml(spec.quality_hint) + "</span>" +
          "</label>" +
          '<div class="speech-size-artifact inline-artifact" data-size="' + escapeHtml(size) + '">' +
          '<span class="inline-artifact-state">Checking&hellip;</span>' +
          "</div>" +
          "</div>"
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

    var configCard =
      '<div class="card">' +
      '<div class="card-header">' +
      '<h1 class="card-title">AI Provider Configuration</h1>' +
      '<p class="card-subtitle">Configure your AI provider for interview feedback and evaluation</p>' +
      "</div>" +
      '<form id="config-form" class="form">' +
      '<div class="form-group" id="llm-preset-group">' +
      '<label for="llm_preset_id" class="form-label form-label-required">Interview model</label>' +
      presetOptions +
      '<p class="form-hint">Providers and their API keys are managed on the ' +
      '<a href="#/config/providers">Providers &amp; models</a> tab.</p>' +
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
      '<p class="form-hint">When enabled, the interview page reads each question aloud using an offline Silero voice.</p>' +
      '<div class="inline-artifact" id="question-voice-status">' +
      '<span class="inline-artifact-state">Checking&hellip;</span>' +
      "</div>" +
      "</div>" +
      '<div class="form-group">' +
      '<span class="form-label form-label-required">Speech model size</span>' +
      '<p class="form-hint">Offline Whisper model for voice input. Larger models are more accurate but slower and use more disk and RAM. One model downloads at a time.</p>' +
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
      (presetGroups.length ? "" : " disabled") + ">Save Configuration</button>" +
      '<button type="button" id="config-test-btn" class="btn btn-secondary"' +
      (presetGroups.length ? "" : " disabled") + ">Test Connection</button>" +
      "</div>" +
      removeButton +
      "</form>" +
      "</div>";

    var providerCards = (data.llm_providers || []).map(buildProviderCardHTML).join("");
    var providersCard =
      '<div class="card" id="providers-panel">' +
      '<div class="card-header">' +
      '<h1 class="card-title">Providers &amp; models</h1>' +
      '<p class="card-subtitle">Each provider stores one endpoint and its API key. Add every model the endpoint offers; the interview model picker groups them by provider.</p>' +
      "</div>" +
      '<div class="provider-list">' +
      (providerCards || '<div class="alert alert-info">No providers yet. Add the first one below.</div>') +
      "</div>" +
      '<div class="divider"></div>' +
      '<h2 class="section-title">Add provider</h2>' +
      '<form id="add-provider-form" class="form">' +
      '<div class="form-row">' +
      '<label class="form-field"><span class="form-label form-label-required">Display name</span>' +
      '<input type="text" name="display_name" class="form-control" required placeholder="Work OpenAI"></label>' +
      '<label class="form-field"><span class="form-label form-label-required">Base URL</span>' +
      '<input type="url" name="base_url" class="form-control" required placeholder="https://api.openai.com/v1"></label>' +
      "</div>" +
      '<label class="form-field"><span class="form-label">API key</span>' +
      '<input type="password" name="api_key" class="form-control" autocomplete="off" placeholder="sk-… (leave blank for local servers)"></label>' +
      '<p class="form-hint">The key is stored once for the provider and shared by all of its models.</p>' +
      '<div class="inline-form-actions">' +
      '<button type="submit" class="btn btn-secondary">Add provider</button>' +
      "</div>" +
      "</form>" +
      "</div>";

    return (
      (data.error ? alertError(data.error) : "") +
      (data.message ? alertSuccess(data.message) : "") +
      '<div class="settings-layout">' +
      '<nav class="settings-nav" aria-label="Configuration sections">' +
      '<button type="button" class="settings-nav-item' +
      (showProvidersTab ? "" : " is-active") +
      '" data-config-tab="config">' +
      '<span class="settings-nav-icon" aria-hidden="true">&#9881;&#65039;</span>' +
      '<span class="settings-nav-text">' +
      '<span class="settings-nav-label">Configuration</span>' +
      '<span class="settings-nav-desc">Interview model, language, voice</span>' +
      "</span></button>" +
      '<button type="button" class="settings-nav-item' +
      (showProvidersTab ? " is-active" : "") +
      '" data-config-tab="providers">' +
      '<span class="settings-nav-icon" aria-hidden="true">&#128268;</span>' +
      '<span class="settings-nav-text">' +
      '<span class="settings-nav-label">Providers &amp; models</span>' +
      '<span class="settings-nav-desc">Endpoints, API keys, model list</span>' +
      "</span></button>" +
      "</nav>" +
      '<div class="settings-content">' +
      '<div class="settings-pane" data-config-pane="config"' +
      (showProvidersTab ? " hidden" : "") +
      ">" +
      configCard +
      "</div>" +
      '<div class="settings-pane" data-config-pane="providers"' +
      (showProvidersTab ? "" : " hidden") +
      ">" +
      providersCard +
      "</div>" +
      "</div>" +
      "</div>"
    );
  }

  function inlineArtifactStatus(status, downloadUrl, retryLabel) {
    /* status: {state, percent, message, ...} */
    var label;
    var button = "";
    if (status.state === "downloading") {
      label = "Downloading\u2026 " + status.percent + "%";
    } else if (status.state === "ready") {
      label = status.message || "Ready";
    } else if (status.state === "error") {
      label = status.message || "Download failed";
      button =
        '<button type="button" class="btn btn-sm btn-secondary speech-download-btn" ' +
        'data-url="' + escapeHtml(downloadUrl) + '">' + (retryLabel || "Retry") + "</button>";
    } else {
      label = status.message || "Not installed";
      button =
        '<button type="button" class="btn btn-sm btn-secondary speech-download-btn" ' +
        'data-url="' + escapeHtml(downloadUrl) + '">Download</button>';
    }
    return (
      '<span class="inline-artifact-state inline-artifact-state--' + escapeHtml(status.state) + '">' +
      escapeHtml(label) + "</span>" +
      (button ? " " + button : "")
    );
  }

  function renderSpeechSizeArtifacts(container) {
    var locale = selectedFormLocale(container);
    var hosts = Array.prototype.slice.call(
      container.querySelectorAll(".speech-size-artifact[data-size]")
    );
    if (!hosts.length) {
      return Promise.resolve();
    }
    return Promise.all(
      hosts.map(function (host) {
        var size = host.dataset.size;
        return fetchJSON(
          "/speech/model/status?size=" + encodeURIComponent(size) +
            "&locale=" + encodeURIComponent(locale)
        )
          .then(function (status) {
            return { host: host, size: size, status: status };
          })
          .catch(function () {
            return null;
          });
      })
    ).then(function (results) {
      var active = null;
      results.forEach(function (row) {
        if (row && row.status.state === "downloading") {
          active = row.size;
        }
      });
      results.forEach(function (row) {
        if (!row || !row.host.isConnected) {
          return;
        }
        row.host.dataset.state = row.status.state;
        row.host.innerHTML = inlineArtifactStatus(
          row.status,
          "/speech/model/download?size=" + encodeURIComponent(row.size) +
            "&locale=" + encodeURIComponent(locale)
        );
        /* One Whisper download can run at a time: keep other buttons locked. */
        var btn = row.host.querySelector(".speech-download-btn");
        if (btn && active && row.size !== active) {
          btn.disabled = true;
          btn.title = "Another speech model is downloading";
        }
      });
      scheduleConfigPoll(container, "speech", active !== null);
    });
  }

  function renderQuestionVoiceArtifact(container) {
    var locale = selectedFormLocale(container);
    var host = container.querySelector("#question-voice-status");
    if (!host) {
      return Promise.resolve();
    }
    return fetchJSON("/speech/tts/status?locale=" + encodeURIComponent(locale))
      .then(function (status) {
        host.dataset.state = status.state;
        host.innerHTML = inlineArtifactStatus(
          status,
          "/speech/tts/voice/download?locale=" + encodeURIComponent(locale)
        );
        scheduleConfigPoll(container, "voice", status.state === "downloading");
      })
      .catch(function () {
        /* transient */
      });
  }

  var configPollTimers = { speech: null, voice: null };

  function scheduleConfigPoll(container, kind, downloading) {
    if (configPollTimers[kind]) {
      clearInterval(configPollTimers[kind]);
      configPollTimers[kind] = null;
    }
    if (!downloading) {
      return;
    }
    configPollTimers[kind] = setInterval(function () {
      if (!container.isConnected) {
        clearInterval(configPollTimers[kind]);
        configPollTimers[kind] = null;
        return;
      }
      if (kind === "speech") {
        renderSpeechSizeArtifacts(container);
      } else {
        renderQuestionVoiceArtifact(container);
      }
    }, 1500);
  }

  function applyPresetMode(container) {
    var presetSelect = container.querySelector("#llm_preset_id");
    var description = container.querySelector("#llm-preset-description");
    if (!presetSelect) {
      return;
    }
    var option = presetSelect.options[presetSelect.selectedIndex];
    if (!option) {
      return;
    }
    var acceptsAudio = option.dataset.acceptsAudioInput === "true";
    var audioHint =
      "This model accepts audio answers. Whisper must be installed for the selected speech model size.";
    if (description) {
      var base = option.dataset.description || "";
      description.textContent = acceptsAudio
        ? (base ? base + " — " : "") + audioHint
        : base;
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
      api_key: "",
      timeout: timeout ? parseFloat(timeout.value) || 60 : 60,
      locale: locale ? locale.value : "en",
      speech_model_size: size ? size.value : "small",
      question_voice_enabled: voice ? voice.checked : false,
    };
  }

  function collectProviderForm(form) {
    var clearBox = form.querySelector('[name="clear_api_key"]');
    return {
      display_name: form.querySelector('[name="display_name"]').value,
      base_url: form.querySelector('[name="base_url"]').value,
      api_key: form.querySelector('[name="api_key"]')
        ? form.querySelector('[name="api_key"]').value
        : "",
      clear_api_key: !!(clearBox && clearBox.checked),
    };
  }

  function collectProviderModelForm(form) {
    return {
      display_name: form.querySelector('[name="display_name"]').value,
      model: form.querySelector('[name="model"]').value,
      accepts_audio_input: !!form.querySelector('[name="accepts_audio_input"]').checked,
    };
  }

  function updateConfigSaveState(container) {
    var select = container.querySelector("#llm_preset_id");
    var ready = !!(select && select.value);
    ["#config-save-btn", "#config-test-btn"].forEach(function (selector) {
      var btn = container.querySelector(selector);
      if (btn) {
        btn.disabled = !ready;
      }
    });
  }

  function renderPresetOptions(container, query) {
    var select = container.querySelector("#llm_preset_id");
    if (!select) {
      return;
    }
    var current = select.value;
    select.innerHTML = buildPresetOptionsHTML(
      container._llmGroups || [],
      current,
      query
    );
    var emptyHint = container.querySelector("#llm-preset-empty");
    if (emptyHint) {
      emptyHint.hidden = !!select.value;
    }
    applyPresetMode(container);
    updateConfigSaveState(container);
  }

  function setConfigTab(container, tab) {
    container.querySelectorAll("[data-config-pane]").forEach(function (pane) {
      pane.hidden = pane.dataset.configPane !== tab;
    });
    container.querySelectorAll("[data-config-tab]").forEach(function (btn) {
      btn.classList.toggle("is-active", btn.dataset.configTab === tab);
    });
    if (window.history && window.history.replaceState) {
      window.history.replaceState(
        null,
        "",
        tab === "providers" ? "#/config/providers" : "#/config"
      );
    }
  }

  function renderConfigPage(container, data, activeTab) {
    activeTab = activeTab === "providers" ? "providers" : "config";
    container._llmGroups = buildPresetGroups(data);
    container.innerHTML = buildConfigFormHTML(data, activeTab);
    applyPresetMode(container);
    updateConfigSaveState(container);
    renderSpeechSizeArtifacts(container);
    renderQuestionVoiceArtifact(container);

    container.querySelectorAll("[data-config-tab]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        setConfigTab(container, btn.dataset.configTab);
      });
    });

    var presetSelect = container.querySelector("#llm_preset_id");
    if (presetSelect) {
      presetSelect.addEventListener("change", function () {
        applyPresetMode(container);
      });
    }
    var modelFilter = container.querySelector("#llm-model-filter");
    if (modelFilter) {
      modelFilter.addEventListener("input", function () {
        renderPresetOptions(container, modelFilter.value);
      });
    }
    container.querySelector("#locale").addEventListener("change", function () {
      renderSpeechSizeArtifacts(container);
      renderQuestionVoiceArtifact(container);
    });

    container.querySelector("#config-save-btn").addEventListener("click", function (event) {
      event.preventDefault();
      var btn = event.target;
      btn.disabled = true;
      postJSON("/api/config", collectConfigForm(container))
        .then(function (result) {
          renderConfigPage(container, result.page, activeTab);
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
            renderConfigPage(container, result.page, activeTab);
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

    if (container._configChangeHandler) {
      container.removeEventListener("change", container._configChangeHandler);
    }
    container._configChangeHandler = function (event) {
      var audio = event.target.closest ? event.target.closest("[data-model-audio]") : null;
      if (audio) {
        toggleModelAudio(container, audio);
      }
    };
    container.addEventListener("change", container._configChangeHandler);

    if (container._configClickHandler) {
      container.removeEventListener("click", container._configClickHandler);
    }
    container._configClickHandler = function (event) {
      handleConfigClick(container, event, activeTab);
    };
    container.addEventListener("click", container._configClickHandler);

    if (container._configSubmitHandler) {
      container.removeEventListener("submit", container._configSubmitHandler);
    }
    container._configSubmitHandler = function (event) {
      handleConfigSubmit(container, event, activeTab);
    };
    container.addEventListener("submit", container._configSubmitHandler);
  }

  function handleConfigAction(container, result, activeTab, fallback) {
    if (result && result.page) {
      renderConfigPage(container, result.page, activeTab);
      return;
    }
    container.insertAdjacentHTML("beforeend", errorCard(fallback));
  }

  function handleConfigClick(container, event, activeTab) {
    var target = event.target;
    if (!target || typeof target.closest !== "function") {
      return;
    }

    var download = target.closest(".speech-download-btn");
    if (download) {
      download.disabled = true;
      var downloadUrl = download.dataset.url || "";
      fetchJSON(downloadUrl, { method: "POST" })
        .then(function () {
          if (downloadUrl.indexOf("/speech/tts/") === 0) {
            renderQuestionVoiceArtifact(container);
          } else {
            renderSpeechSizeArtifacts(container);
          }
        })
        .catch(function () {
          download.disabled = false;
        });
      return;
    }

    var editProvider = target.closest("[data-provider-edit]");
    if (editProvider) {
      var editForm = editProvider
        .closest(".provider-card")
        .querySelector("[data-provider-edit-form]");
      editForm.hidden = !editForm.hidden;
      return;
    }

    var deleteProviderBtn = target.closest("[data-provider-delete]");
    if (deleteProviderBtn) {
      if (!window.confirm("Delete this provider and all of its models?")) {
        return;
      }
      deleteProviderBtn.disabled = true;
      fetchJSON(
        "/api/config/providers/" + encodeURIComponent(deleteProviderBtn.dataset.providerDelete),
        { method: "DELETE" }
      )
        .then(function (result) {
          handleConfigAction(
            container, result, activeTab, "Could not delete provider."
          );
        })
        .catch(function (err) {
          deleteProviderBtn.disabled = false;
          container.insertAdjacentHTML(
            "beforeend",
            errorCard(errMessage(err, "Could not delete provider."))
          );
        });
      return;
    }

    var addModelBtn = target.closest("[data-model-add]");
    if (addModelBtn) {
      var addForm = addModelBtn
        .closest(".provider-card")
        .querySelector('[data-model-form=""]');
      addForm.hidden = !addForm.hidden;
      return;
    }

    var editModelBtn = target.closest("[data-model-edit]");
    if (editModelBtn) {
      var row = editModelBtn.closest(".provider-model-row");
      var modelForm = row.querySelector("[data-model-form]");
      modelForm.hidden = !modelForm.hidden;
      return;
    }

    var deleteModelBtn = target.closest("[data-model-delete]");
    if (deleteModelBtn) {
      if (!window.confirm("Delete this model?")) {
        return;
      }
      deleteModelBtn.disabled = true;
      fetchJSON(
        "/api/config/providers/" + encodeURIComponent(deleteModelBtn.dataset.providerId) +
          "/models/" + encodeURIComponent(deleteModelBtn.dataset.modelDelete),
        { method: "DELETE" }
      )
        .then(function (result) {
          handleConfigAction(
            container, result, activeTab, "Could not delete model."
          );
        })
        .catch(function (err) {
          deleteModelBtn.disabled = false;
          container.insertAdjacentHTML(
            "beforeend",
            errorCard(errMessage(err, "Could not delete model."))
          );
        });
      return;
    }

    var importBtn = target.closest("[data-import-models]");
    if (importBtn) {
      importProviderModels(container, importBtn, activeTab);
      return;
    }

    var cancelBtn = target.closest("[data-form-cancel]");
    if (cancelBtn) {
      var form = cancelBtn.closest("form");
      form.hidden = true;
      form.reset();
    }
  }

  function importProviderModels(container, importBtn, activeTab) {
    importBtn.disabled = true;
    fetchJSON(
      "/api/config/providers/" + encodeURIComponent(importBtn.dataset.importModels) +
        "/import-models",
      { method: "POST" }
    )
      .then(function (result) {
        handleConfigAction(container, result, activeTab, "Could not import models.");
      })
      .catch(function (err) {
        importBtn.disabled = false;
        container.insertAdjacentHTML(
          "beforeend",
          errorCard(errMessage(err, "Could not import models."))
        );
      });
  }

  function toggleModelAudio(container, checkbox) {
    var desired = checkbox.checked;
    checkbox.disabled = true;
    fetchJSON(
      "/api/config/providers/" + encodeURIComponent(checkbox.dataset.providerId) +
        "/models/" + encodeURIComponent(checkbox.dataset.modelId),
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accepts_audio_input: desired }),
      }
    )
      .then(function (result) {
        checkbox.disabled = false;
        if (result.error) {
          checkbox.checked = !desired;
          container.insertAdjacentHTML("beforeend", errorCard(result.error));
          return;
        }
        syncAudioFlag(container, checkbox.dataset.modelId, desired);
      })
      .catch(function (err) {
        checkbox.disabled = false;
        checkbox.checked = !desired;
        container.insertAdjacentHTML(
          "beforeend",
          errorCard(errMessage(err, "Could not update model."))
        );
      });
  }

  function syncAudioFlag(container, modelId, value) {
    (container._llmGroups || []).forEach(function (group) {
      group.models.forEach(function (entry) {
        if (entry.id === modelId) {
          entry.accepts_audio_input = value;
        }
      });
    });
    /* The hidden Configuration pane still shows the old "(audio)" suffix and
       hint; rebuild its picker options from the updated groups. */
    var filter = container.querySelector("#llm-model-filter");
    renderPresetOptions(container, filter ? filter.value : "");
  }

  function handleConfigSubmit(container, event, activeTab) {
    var form = event.target;
    if (!form || !form.matches || typeof form.matches !== "function") {
      return;
    }
    var action = null;
    var url = null;
    var payload = null;
    var fallback = "Could not save.";

    if (form.id === "add-provider-form") {
      event.preventDefault();
      action = "post";
      url = "/api/config/providers";
      payload = collectProviderForm(form);
      fallback = "Could not add provider.";
    } else if (form.matches("[data-provider-edit-form]")) {
      event.preventDefault();
      action = "put";
      url = "/api/config/providers/" + encodeURIComponent(form.dataset.providerEditForm);
      payload = collectProviderForm(form);
      fallback = "Could not save provider.";
    } else if (form.matches("[data-model-form]")) {
      event.preventDefault();
      payload = collectProviderModelForm(form);
      if (form.dataset.modelForm) {
        action = "put";
        url =
          "/api/config/providers/" + encodeURIComponent(form.dataset.providerId) +
          "/models/" + encodeURIComponent(form.dataset.modelForm);
        fallback = "Could not save model.";
      } else {
        action = "post";
        url = "/api/config/providers/" + encodeURIComponent(form.dataset.providerId) + "/models";
        fallback = "Could not add model.";
      }
    } else {
      return;
    }

    var submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) {
      submitBtn.disabled = true;
    }
    var request =
      action === "put"
        ? fetchJSON(url, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          })
        : postJSON(url, payload);
    request
      .then(function (result) {
        handleConfigAction(container, result, activeTab, fallback);
      })
      .catch(function (err) {
        if (submitBtn) {
          submitBtn.disabled = false;
        }
        container.insertAdjacentHTML("beforeend", errorCard(errMessage(err, fallback)));
      });
  }

  pages.config = function (container, params) {
    var activeTab = params && params.id === "providers" ? "providers" : "config";
    fetchJSON("/api/config")
      .then(function (data) {
        renderConfigPage(container, data, activeTab);
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
      fetchJSON("/api/known-questions")
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

  function interviewAnswerHtml(
    answer,
    interviewStatus,
    questionVoiceEnabled,
    currentAnswerId,
  ) {
    /* A question bubble appears once it is answered or becomes the active one. */
    var showQuestion = answer.answer_text !== null || answer.id === currentAnswerId;
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
      body += interviewAnswerHtml(
        answer,
        data.interview.status,
        data.question_voice_enabled,
        data.current_answer_id,
      );
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
      '" data-llm-budget="' +
      escapeHtml(data.llm_evaluation_budget_seconds) +
      '" data-llm-completion-budget="' +
      escapeHtml(data.llm_completion_budget_seconds) +
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
      llmEvaluationBudgetSeconds: data.llm_evaluation_budget_seconds,
      llmCompletionBudgetSeconds: data.llm_completion_budget_seconds,
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
