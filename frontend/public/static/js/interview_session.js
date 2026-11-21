/*
 * Copyright 2026 GrillKit Contributors
 * SPDX-License-Identifier: Apache-2.0
 * Interview (theory phase) session controller for the SPA.
 *
 * Reproduces the inline script that previously lived in templates/interview.html.
 * It reads its bootstrap state from `window.grillkitInterviewBootstrap`, which the
 * SPA page handler sets before loading this module. This module owns the theory
 * WebSocket, answer submission, timers, follow-up rendering, and coordinates the
 * dictation / audio-answer / question-voice modules.
 */
(function () {
    "use strict";

    var boot = window.grillkitInterviewBootstrap || {};
    if (!boot.interviewId || boot.phase !== "theory") {
        return;
    }

    var interviewId = boot.interviewId;
    var initialInterviewStatus = boot.status;
    var wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    var wsUrl =
        wsProtocol +
        "//" +
        window.location.host +
        "/interview/" +
        encodeURIComponent(interviewId) +
        "/theory/ws";
    var ws = null;
    var reconnectTimer = null;
    var currentQuestionId = boot.currentQuestionId || "";
    var questionCount = boot.questionCount;
    var questionTimerEnabled = boot.questionTimerEnabled;
    var interviewLocale = boot.locale;
    var timeoutChatLabel = boot.timeoutChatLabel;
    var questionTimeLimitSeconds = boot.questionTimeLimitSeconds;
    var llmRequestTimeoutSeconds = boot.llmRequestTimeoutSeconds;
    var currentRound = boot.currentRound || 0;
    var isSubmitting = false;
    var interviewFinished = false;
    window.isSubmitting = false;
    var evaluationWatchdogTimer = null;

    function stopQuestionTimer() {
        if (window.grillkitQuestionTimer) {
            window.grillkitQuestionTimer.stop();
        }
        var timerRow = document.getElementById("interview-timer-row");
        if (timerRow) {
            timerRow.hidden = true;
        }
    }

    window.grillkitOnTimerExpired = function () {
        if (isSubmitting) {
            return;
        }
        isSubmitting = true;
        window.isSubmitting = true;
        enableForm(false);
        stopQuestionTimer();
    };

    function restartQuestionTimer(remainingSeconds) {
        if (interviewFinished || !questionTimerEnabled || !window.grillkitQuestionTimer) {
            return;
        }
        var seconds =
            remainingSeconds != null ? remainingSeconds : questionTimeLimitSeconds;
        window.grillkitQuestionTimer.start({
            enabled: true,
            remainingSeconds: seconds,
            questionId: currentQuestionId,
            round: currentRound,
            getWs: function () {
                return ws;
            },
        });
    }

    function showTimeoutBubble(feedbackText) {
        var chatContainer = document.getElementById("chat-container");
        if (!chatContainer) {
            return;
        }
        var label = feedbackText || timeoutChatLabel;
        var div = document.createElement("div");
        div.className = "chat-message system";
        div.innerHTML =
            '<div class="chat-bubble system-bubble"><em>' +
            escapeHtml(label) +
            "</em></div>";
        chatContainer.appendChild(div);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function updateProgressDisplay(order) {
        var progressEl = document.getElementById("interview-progress");
        if (!progressEl) {
            return;
        }
        if (order == null) {
            progressEl.textContent = "All questions answered";
        } else {
            progressEl.textContent = "Question " + order + " of " + questionCount;
        }
    }

    function connectWebSocket() {
        ws = new WebSocket(wsUrl);

        ws.onopen = function () {
            console.log("WebSocket connected");
            clearEvaluationWatchdog();
            showEvaluating(false);
            isSubmitting = false;
            window.isSubmitting = false;
            if (reconnectTimer) {
                clearTimeout(reconnectTimer);
                reconnectTimer = null;
            }
            enableForm(true);
            ws.send(JSON.stringify({ type: "ping" }));
        };

        ws.onmessage = function (event) {
            var data = JSON.parse(event.data);
            handleWsMessage(data);
        };

        ws.onclose = function () {
            var indicator = document.getElementById("evaluating-indicator");
            var wasEvaluating = indicator && indicator.style.display !== "none";
            if (wasEvaluating || isSubmitting) {
                clearEvaluationWatchdog();
                showEvaluating(false);
                isSubmitting = false;
                window.isSubmitting = false;
                enableForm(true);
                showError(
                    "Connection lost during evaluation. Your answer may have been saved — refresh the page."
                );
            }
            console.log("WebSocket disconnected, reconnecting in 3s...");
            reconnectTimer = setTimeout(function () {
                connectWebSocket();
            }, 3000);
        };

        ws.onerror = function (err) {
            console.error("WebSocket error:", err);
        };
    }

    function handleWsMessage(data) {
        console.log("[WS] handleWsMessage type:", data.type, "data:", data);
        switch (data.type) {
            case "saved":
                break;

            case "evaluating":
                showEvaluating(true);
                startEvaluationWatchdog();
                break;

            case "transcript":
                if (!data.text) {
                    showError(
                        "Speech not recognized. Please try again or type your answer."
                    );
                    if (typeof window.grillkitUpdateAudioAnswerBubble === "function") {
                        window.grillkitUpdateAudioAnswerBubble("[Not recognized]");
                    } else {
                        showAnswerBubbleWithText("[Not recognized]");
                    }
                } else {
                    if (typeof window.grillkitUpdateAudioAnswerBubble === "function") {
                        window.grillkitUpdateAudioAnswerBubble(data.text);
                    } else {
                        showAnswerBubbleWithText(data.text);
                    }
                }
                break;

            case "feedback":
                clearEvaluationWatchdog();
                showEvaluating(false);
                if (data.timed_out) {
                    showTimeoutBubble(data.feedback);
                }
                stopQuestionTimer();
                showNextAfterFeedback(data);
                break;

            case "interview_completed":
                clearEvaluationWatchdog();
                showEvaluating(false);
                interviewFinished = true;
                stopQuestionTimer();
                handleSessionCompleted(data);
                break;

            case "pong":
                if (data.status === "completed" && initialInterviewStatus === "active") {
                    window.location.reload();
                } else if (data.status === "not_found") {
                    window.location.href = "/";
                } else if (data.status === "error") {
                    showError("Session error. Please reload the page.");
                }
                break;

            case "error":
                clearEvaluationWatchdog();
                showEvaluating(false);
                isSubmitting = false;
                window.isSubmitting = false;
                enableForm(true);
                showError(data.message);
                break;
        }
    }

    function clearEvaluationWatchdog() {
        if (evaluationWatchdogTimer) {
            clearTimeout(evaluationWatchdogTimer);
            evaluationWatchdogTimer = null;
        }
    }

    function startEvaluationWatchdog() {
        clearEvaluationWatchdog();
        var graceMs = 15000;
        var timeoutMs = llmRequestTimeoutSeconds * 1000 + graceMs;
        evaluationWatchdogTimer = setTimeout(function () {
            evaluationWatchdogTimer = null;
            if (!isSubmitting) {
                return;
            }
            showEvaluating(false);
            isSubmitting = false;
            window.isSubmitting = false;
            enableForm(true);
            showError(
                "AI evaluation is taking too long. Check /config (model running and timeout), then try again."
            );
        }, timeoutMs);
    }

    function submitAnswer() {
        if (typeof window.grillkitAbortDictation === "function") {
            window.grillkitAbortDictation();
        }
        if (typeof window.grillkitAbortAudioRecording === "function") {
            window.grillkitAbortAudioRecording();
        }

        var textarea = document.getElementById("answer_text");
        var answerText = textarea.value.trim();

        if (!answerText) {
            alert("Please enter your answer.");
            return;
        }

        if (isSubmitting) {
            return;
        }
        isSubmitting = true;
        window.isSubmitting = true;

        enableForm(false);
        showAnswerBubble();

        stopQuestionTimer();

        ws.send(
            JSON.stringify({
                type: "answer",
                question_id: currentQuestionId,
                answer_text: answerText,
            })
        );
    }

    function endInterview() {
        if (!confirm("Are you sure you want to end this interview?")) {
            return;
        }

        if (isSubmitting) {
            return;
        }
        isSubmitting = true;
        window.isSubmitting = true;
        interviewFinished = true;
        stopQuestionTimer();

        var endBtn = document.getElementById("end-btn");
        if (endBtn) {
            endBtn.disabled = true;
        }
        showEvaluating(true);
        startEvaluationWatchdog();

        ws.send(JSON.stringify({ type: "complete" }));
    }

    function showAnswerBubbleWithText(answerText) {
        var chatContainer = document.getElementById("chat-container");
        var answerDiv = document.createElement("div");
        answerDiv.className = "chat-message answer";
        answerDiv.innerHTML =
            '<div class="chat-bubble answer-bubble"><strong>You:</strong> ' +
            escapeHtml(answerText) +
            "</div>";
        chatContainer.appendChild(answerDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function showAnswerBubble() {
        var textarea = document.getElementById("answer_text");
        var answerText = textarea.value.trim();

        showAnswerBubbleWithText(answerText);

        textarea.value = "";
        textarea.focus();
    }

    function showEvaluating(visible) {
        var indicator = document.getElementById("evaluating-indicator");
        if (indicator) {
            indicator.style.display = visible ? "flex" : "none";
        }
    }

    function buildQuestionBubbleHtml(options) {
        var order = options.order;
        var round = options.round != null ? Number(options.round) : 0;
        var questionText = options.question_text || "";
        var questionCode = options.question_code;
        var answerId = options.id;
        var html = '<div class="chat-bubble question-bubble">';
        html += '<div class="question-bubble-header">';
        html += '<span class="question-bubble-label"><strong>Q' + order + ":</strong>";
        if (round > 0) {
            html += " <em>(follow-up)</em>";
        }
        html += "</span>";
        if (window.grillkitQuestionPlayButtonHtml && answerId) {
            html += window.grillkitQuestionPlayButtonHtml(answerId);
        }
        if (round === 0 && window.KnownQuestions && window.KnownQuestions.knownToggleButtonHtml) {
            html += window.KnownQuestions.knownToggleButtonHtml(
                "theory",
                options.question_id,
                true
            );
        }
        html += '</div><div class="question-bubble-body">';
        html += escapeHtml(questionText);
        if (questionCode) {
            html +=
                '<pre class="code-block"><code>' +
                escapeHtml(questionCode) +
                "</code></pre>";
        }
        html += "</div></div>";
        return html;
    }

    function appendQuestionMessage(options) {
        var chatContainer = document.getElementById("chat-container");
        if (!chatContainer) {
            return null;
        }
        var messageDiv = document.createElement("div");
        messageDiv.className = "chat-message question";
        messageDiv.setAttribute("data-question-id", options.question_id);
        messageDiv.setAttribute(
            "data-round",
            String(options.round != null ? options.round : 0)
        );
        if (options.id) {
            messageDiv.setAttribute("data-answer-id", String(options.id));
        }
        messageDiv.innerHTML = buildQuestionBubbleHtml(options);
        chatContainer.appendChild(messageDiv);
        if (window.grillkitBindQuestionPlayButtons) {
            window.grillkitBindQuestionPlayButtons(messageDiv);
        }
        if (window.KnownQuestions && window.KnownQuestions.bindKnownToggleIn) {
            window.KnownQuestions.bindKnownToggleIn(messageDiv);
        }
        return messageDiv;
    }

    function showNextAfterFeedback(data) {
        var chatContainer = document.getElementById("chat-container");

        if (data.follow_up_question) {
            appendQuestionMessage({
                question_id: data.question_id,
                order: data.order,
                round: data.round + 1,
                question_text: data.follow_up_question,
                id: data.follow_up_answer_id,
            });

            currentQuestionId = data.question_id;
            currentRound = data.round + 1;
            isSubmitting = false;
            window.isSubmitting = false;
            enableForm(true);
            restartQuestionTimer(data.timer_remaining_seconds);
            if (window.grillkitPlayQuestionAudio && data.follow_up_answer_id) {
                window.grillkitPlayQuestionAudio(data.follow_up_answer_id);
            }
        } else if (data.next_question) {
            var nq = data.next_question;
            appendQuestionMessage(nq);

            currentQuestionId = nq.question_id;
            currentRound = nq.round != null ? nq.round : 0;
            updateProgressDisplay(nq.order);
            isSubmitting = false;
            window.isSubmitting = false;
            enableForm(true);
            restartQuestionTimer(data.timer_remaining_seconds);
            if (window.grillkitPlayQuestionAudio && nq.id) {
                window.grillkitPlayQuestionAudio(nq.id);
            }
        } else {
            updateProgressDisplay(null);
            stopQuestionTimer();
            isSubmitting = false;
            window.isSubmitting = false;
            if (
                window.grillkitSessionPhaseNav &&
                window.grillkitSessionPhaseNav.hasPendingCodingPhase()
            ) {
                var answerSection = document.getElementById("answer-section");
                if (answerSection) {
                    answerSection.innerHTML =
                        '<p class="composer-done text-muted">Theory section complete. Loading coding practice…</p>';
                }
                window.grillkitSessionPhaseNav.continueToNextPhase();
                return;
            }
            var afterSection = document.getElementById("answer-section");
            if (afterSection) {
                afterSection.innerHTML =
                    '<p class="composer-done text-muted">All questions answered. Click <strong>End Interview</strong> to get your final evaluation.</p>';
            }
        }

        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function handleSessionCompleted() {
        // Results is an SPA hash route; the server no longer serves this path.
        window.location.href = "#/interview/" + interviewId + "/results";
    }

    function enableForm(enabled) {
        var textarea = document.getElementById("answer_text");
        var submitBtn = document.getElementById("submit-btn");
        var endBtn = document.getElementById("end-btn");
        var dictationBtn = document.getElementById("dictation-mic-btn");
        var audioRecordBtn = document.getElementById("audio-record-btn");
        var audioCancelBtn = document.getElementById("audio-cancel-btn");
        var audioSendBtn = document.getElementById("audio-send-btn");
        if (textarea) {
            textarea.disabled = !enabled;
            if (enabled) {
                textarea.readOnly = false;
            }
        }
        if (submitBtn) {
            submitBtn.disabled = !enabled;
        }
        if (dictationBtn) {
            dictationBtn.disabled = !enabled;
        }
        var audioCaptureActive =
            audioCancelBtn &&
            !audioCancelBtn.hidden &&
            typeof window.grillkitIsAudioRecording === "function" &&
            window.grillkitIsAudioRecording();
        if (audioRecordBtn) {
            audioRecordBtn.disabled = !enabled;
        }
        if (audioCancelBtn) {
            audioCancelBtn.disabled = audioCaptureActive ? false : true;
        }
        if (audioSendBtn) {
            audioSendBtn.disabled = audioCaptureActive ? false : true;
        }
        if (endBtn && enabled) {
            endBtn.disabled = false;
        }
    }

    window.grillkitHandleInterviewEvent = handleWsMessage;
    window.grillkitGetSubmissionContext = function () {
        return { questionId: currentQuestionId, round: currentRound };
    };
    window.grillkitSetSubmitting = function (value) {
        isSubmitting = value;
        window.isSubmitting = value;
    };
    window.grillkitShowAnswerBubble = showAnswerBubbleWithText;
    window.grillkitSubmitInterviewAnswer = submitAnswer;
    window.grillkitEndInterview = endInterview;

    window.showError = showError;

    function showError(message) {
        var alerts = document.getElementById("interview-alerts");
        if (alerts) {
            var alertDiv = document.createElement("div");
            alertDiv.className = "alert alert-warning";
            alertDiv.textContent = message;
            alerts.appendChild(alertDiv);
        }
        var chatContainer = document.getElementById("chat-container");
        if (chatContainer) {
            var errorDiv = document.createElement("div");
            errorDiv.className = "chat-message error";
            errorDiv.innerHTML =
                '<div class="chat-bubble error-bubble"><strong>Error:</strong> ' +
                escapeHtml(message) +
                "</div>";
            chatContainer.appendChild(errorDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        if (!alerts && !chatContainer) {
            alert(message);
        }
    }

    function escapeHtml(text) {
        if (!text) {
            return "";
        }
        var div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    function init() {
        var submitBtn = document.getElementById("submit-btn");
        if (submitBtn) {
            submitBtn.addEventListener("click", submitAnswer);
        }
        var endBtn = document.getElementById("end-btn");
        if (endBtn) {
            endBtn.addEventListener("click", endInterview);
        }
        var phaseBtn = document.getElementById("theory-to-coding-btn");
        if (phaseBtn) {
            phaseBtn.addEventListener("click", function () {
                window.location.reload();
            });
        }
        var chatContainer = document.getElementById("chat-container");
        if (chatContainer) {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        if (initialInterviewStatus === "active") {
            connectWebSocket();
            var theoryPanel = document.getElementById("theory-panel");
            if (theoryPanel && !theoryPanel.hidden) {
                restartQuestionTimer(boot.timerRemainingSeconds);
                if (window.KnownQuestions && window.KnownQuestions.initInterviewTheory) {
                    window.KnownQuestions.initInterviewTheory();
                }
            }
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
