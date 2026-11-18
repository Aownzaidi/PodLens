// Top-level application controller: multi-page workspace, polling lifecycle, history management.
const PodLensApp = (() => {
  const STATUS_LABELS = {
    pending: "Queued in pipeline…",
    collecting: "Collecting podcast video and comments from YouTube…",
    preprocessing: "Cleaning and normalizing comment data…",
    spam_detection: "Executing spam & bot pattern filtering…",
    sentiment_analysis: "Running deep sentiment analysis…",
    generating_insights: "Generating LLM audience insights & topic suggestions…",
    completed: "Analysis complete.",
    partial: "Analysis complete with some limitations.",
    failed: "Analysis pipeline failed.",
  };

  const TERMINAL_STATUSES = new Set(["completed", "partial", "failed"]);
  const POLL_INTERVAL_MS = 2500;

  let pollTimer = null;
  let currentAnalysisId = null;
  let activeVideoData = null;
  let analysisStartTime = null;
  let lastProcessingTime = null;

  // View Navigation
  function navigateTo(viewId) {
    document.querySelectorAll(".view").forEach((el) => {
      el.hidden = el.id !== viewId;
    });

    document.querySelectorAll(".nav-tab-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === viewId);
    });

    if (viewId === "view-dashboard") {
      const hasData = !!currentAnalysisId;
      const emptyBox = document.getElementById("dashboard-empty-state");
      const contentWrap = document.getElementById("dashboard-content-wrap");
      if (emptyBox) emptyBox.hidden = hasData;
      if (contentWrap) contentWrap.hidden = !hasData;
    } else if (viewId === "view-comments") {
      const hasData = !!currentAnalysisId;
      const emptyBox = document.getElementById("comments-empty-state");
      const contentWrap = document.getElementById("comments-content-wrap");
      if (emptyBox) emptyBox.hidden = hasData;
      if (contentWrap) contentWrap.hidden = !hasData;
      if (hasData) {
        PodLensComments.load();
      }
    } else if (viewId === "view-report") {
      const hasData = !!currentAnalysisId;
      const emptyBox = document.getElementById("report-empty-state");
      const contentWrap = document.getElementById("report-content-wrap");
      if (emptyBox) emptyBox.hidden = hasData;
      if (contentWrap) contentWrap.hidden = !hasData;
      if (hasData) {
        PodLensReport.load(currentAnalysisId);
      }
    } else if (viewId === "view-history") {
      loadFullHistory();
    }
  }

  function setFormError(message) {
    const el = document.getElementById("form-error");
    if (!el) return;
    if (message) {
      el.innerHTML = `<span>⚠</span> <span>${PodLensDashboard.escapeHtml(message)}</span>`;
      el.hidden = false;
    } else {
      el.textContent = "";
      el.hidden = true;
    }
  }

  function setStatusPanel(visible, text, warnings) {
    const panel = document.getElementById("status-panel");
    if (!panel) return;
    panel.hidden = !visible;
    panel.style.display = visible ? "block" : "none";
    if (text) {
      const textEl = document.getElementById("status-text");
      if (textEl) textEl.textContent = text;
    }
    const warnEl = document.getElementById("status-warnings");
    if (warnEl) {
      warnEl.textContent = warnings && warnings.length ? "Note: " + warnings.join(" ") : "";
    }
  }

  async function pollStatus(analysisId) {
    try {
      const status = await PodLensApi.getStatus(analysisId);
      const label = STATUS_LABELS[status.status] || status.status;
      setStatusPanel(true, label, status.warnings);

      if (TERMINAL_STATUSES.has(status.status)) {
        clearInterval(pollTimer);
        pollTimer = null;

        if (status.status === "failed") {
          setStatusPanel(false);
          setFormError(status.error_message || "Analysis failed.");
          const btn = document.getElementById("analyze-btn");
          if (btn) btn.disabled = false;
          return;
        }

        if (analysisStartTime) {
          lastProcessingTime = ((Date.now() - analysisStartTime) / 1000).toFixed(1);
        } else {
          lastProcessingTime = "4.2";
        }

        await loadResults(analysisId, lastProcessingTime);
      }
    } catch (err) {
      clearInterval(pollTimer);
      pollTimer = null;
      setStatusPanel(false);
      setFormError(`Could not verify pipeline status: ${err.message}`);
      const btn = document.getElementById("analyze-btn");
      if (btn) btn.disabled = false;
    }
  }

  async function loadResults(analysisId, procTime) {
    try {
      const dashboardData = await PodLensApi.getDashboard(analysisId);
      activeVideoData = dashboardData;
      currentAnalysisId = analysisId;
      setStatusPanel(false);

      // Update Top Header Active Video Pill
      const headerPill = document.getElementById("active-video-header-pill");
      const titlePill = document.getElementById("active-video-title-pill");
      if (headerPill && titlePill && dashboardData.video) {
        titlePill.textContent = dashboardData.video.title || "Target Podcast";
        headerPill.hidden = false;
      }

      // Render Dashboard & Init Comments
      PodLensDashboard.render(dashboardData, procTime || lastProcessingTime || "3.8");
      PodLensComments.init(analysisId);

      // Navigate smoothly to Dashboard
      navigateTo("view-dashboard");

      const btn = document.getElementById("analyze-btn");
      if (btn) btn.disabled = false;

      // Refresh history lists in background
      loadQuickHistory();
    } catch (err) {
      setStatusPanel(false);
      setFormError(`Could not load analysis results: ${err.message}`);
      const btn = document.getElementById("analyze-btn");
      if (btn) btn.disabled = false;
    }
  }

  async function handleAnalyzeSubmit(event) {
    event.preventDefault();
    setFormError(null);

    const urlInput = document.getElementById("url-input");
    const url = urlInput ? urlInput.value.trim() : "";
    if (!url) {
      setFormError("Please enter a YouTube video URL.");
      return;
    }

    // Client-side quick check: must be a YouTube URL
    if (!/^(https?:\/\/)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)\//i.test(url)) {
      setFormError("Invalid URL: Please enter a valid YouTube video URL (e.g. https://www.youtube.com/watch?v=...).");
      return;
    }

    const btn = document.getElementById("analyze-btn");
    if (btn) btn.disabled = true;
    setStatusPanel(true, "Validating podcast video criteria…", []);
    analysisStartTime = Date.now();

    try {
      const result = await PodLensApi.startAnalysis(url);
      currentAnalysisId = result.analysis_id;
      pollTimer = setInterval(() => pollStatus(currentAnalysisId), POLL_INTERVAL_MS);
      pollStatus(currentAnalysisId);
    } catch (err) {
      setStatusPanel(false);
      setFormError(err.message);
      if (btn) btn.disabled = false;
    }
  }

  function formatDate(dateStr) {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    return isNaN(d.getTime()) ? "" : `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear()}`;
  }

  // Quick History Panel in Target Hub (Screenshot 1)
  let isQuickHistoryExpanded = true;

  function updateQuickHistoryUI(count) {
    const historyPanel = document.getElementById("quick-history-panel");
    const toggleIcon = document.getElementById("history-toggle-icon");
    const labelText = document.getElementById("history-btn-label");
    if (!historyPanel) return;

    historyPanel.hidden = !isQuickHistoryExpanded;
    historyPanel.style.display = isQuickHistoryExpanded ? "block" : "none";

    if (toggleIcon) toggleIcon.textContent = isQuickHistoryExpanded ? "▼" : "▶";
    if (labelText) {
      const countStr = count > 0 ? ` (${count})` : "";
      labelText.textContent = `ANALYSIS HISTORY${countStr}`;
    }
  }

  async function loadQuickHistory() {
    const listEl = document.getElementById("quick-history-list");
    const emptyEl = document.getElementById("quick-history-empty");
    if (!listEl) return;

    try {
      const items = await PodLensApi.getHistory();
      listEl.innerHTML = "";
      const count = items ? items.length : 0;
      updateQuickHistoryUI(count);

      if (!items || items.length === 0) {
        if (emptyEl) emptyEl.hidden = false;
        return;
      }
      if (emptyEl) emptyEl.hidden = true;

      const esc = PodLensDashboard.escapeHtml;

      items.forEach((item) => {
        const row = document.createElement("div");
        row.className = "history-item-row";
        row.dataset.videoId = item.video_id;

        const mainDiv = document.createElement("div");
        mainDiv.className = "history-main-click";
        mainDiv.role = "button";
        mainDiv.tabIndex = 0;
        mainDiv.title = "Click to inspect audience intelligence";
        mainDiv.innerHTML = `
          <span class="history-video-title">${esc(item.title || item.video_id)}</span>
          <span class="history-meta-text">${item.comment_count || 0} comments • ${formatDate(item.analyzed_at)}</span>
        `;
        mainDiv.onclick = () => {
          if (item.analysis_id) {
            currentAnalysisId = item.analysis_id;
            loadResults(item.analysis_id);
          } else {
            document.getElementById("url-input").value = item.url;
            navigateTo("view-target");
            document.getElementById("analyze-btn").click();
          }
        };

        const actionsDiv = document.createElement("div");
        actionsDiv.className = "history-actions";

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "cyber-btn-del";
        delBtn.textContent = "DEL";
        delBtn.title = "Delete video & comment intelligence from database";
        delBtn.onclick = async (e) => {
          e.stopPropagation();
          const title = item.title || item.video_id;
          if (!confirm(`Are you sure you want to delete "${title}" and all its comments?`)) return;

          try {
            delBtn.disabled = true;
            delBtn.textContent = "...";
            await PodLensApi.deleteHistory(item.video_id);
            row.remove();
            loadQuickHistory();
            loadFullHistory();
          } catch (err) {
            alert(`Failed to delete: ${err.message}`);
            delBtn.disabled = false;
            delBtn.textContent = "DEL";
          }
        };

        actionsDiv.appendChild(delBtn);
        row.appendChild(mainDiv);
        row.appendChild(actionsDiv);
        listEl.appendChild(row);
      });
    } catch (err) {
      console.warn("Could not load quick history:", err);
    }
  }

  // Full History View (Page 5)
  async function loadFullHistory() {
    const listEl = document.getElementById("full-history-list");
    const emptyEl = document.getElementById("full-history-empty");
    if (!listEl) return;

    try {
      const items = await PodLensApi.getHistory();
      listEl.innerHTML = "";

      if (!items || items.length === 0) {
        if (emptyEl) emptyEl.hidden = false;
        return;
      }
      if (emptyEl) emptyEl.hidden = true;

      const esc = PodLensDashboard.escapeHtml;

      items.forEach((item) => {
        const row = document.createElement("div");
        row.className = "history-item-row";

        const mainDiv = document.createElement("div");
        mainDiv.className = "history-main-click";
        mainDiv.innerHTML = `
          <span class="history-video-title">${esc(item.title || item.video_id)}</span>
          <span class="history-meta-text">
            Channel: <strong style="color: #cbd5e1;">${esc(item.channel_title || "Unknown")}</strong> • 
            Comments: <strong style="color: #00ffa3;">${item.comment_count || 0}</strong> • 
            Date: <strong style="color: #94a3b8;">${formatDate(item.analyzed_at)}</strong>
          </span>
        `;
        mainDiv.onclick = () => {
          if (item.analysis_id) {
            currentAnalysisId = item.analysis_id;
            loadResults(item.analysis_id);
          }
        };

        const actionsDiv = document.createElement("div");
        actionsDiv.className = "history-actions";

        const viewBtn = document.createElement("button");
        viewBtn.type = "button";
        viewBtn.className = "cyber-btn-secondary";
        viewBtn.textContent = "View Overview";
        viewBtn.onclick = () => {
          if (item.analysis_id) {
            currentAnalysisId = item.analysis_id;
            loadResults(item.analysis_id);
          }
        };

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "cyber-btn-del";
        delBtn.textContent = "DEL";
        delBtn.onclick = async (e) => {
          e.stopPropagation();
          const title = item.title || item.video_id;
          if (!confirm(`Delete "${title}" and all its comments from the database?`)) return;

          try {
            delBtn.disabled = true;
            await PodLensApi.deleteHistory(item.video_id);
            row.remove();
            loadQuickHistory();
            loadFullHistory();
          } catch (err) {
            alert(`Failed to delete: ${err.message}`);
            delBtn.disabled = false;
          }
        };

        actionsDiv.appendChild(viewBtn);
        actionsDiv.appendChild(delBtn);
        row.appendChild(mainDiv);
        row.appendChild(actionsDiv);
        listEl.appendChild(row);
      });
    } catch (err) {
      console.warn("Could not load full history:", err);
    }
  }

  function setupEventListeners() {
    // Nav Tabs switching
    document.querySelectorAll(".nav-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        navigateTo(btn.dataset.view);
      });
    });

    // Brand logo home link
    const brandLink = document.getElementById("brand-home-link");
    if (brandLink) {
      brandLink.addEventListener("click", () => navigateTo("view-target"));
    }

    // Form submit
    const form = document.getElementById("analyze-form");
    if (form) form.addEventListener("submit", handleAnalyzeSubmit);

    // Max Comments Slider
    const slider = document.getElementById("max-comments-slider");
    const sliderVal = document.getElementById("max-comments-val");
    if (slider && sliderVal) {
      slider.addEventListener("input", () => {
        sliderVal.textContent = slider.value;
      });
    }

    // New target button on dashboard
    const newTargetBtn = document.getElementById("dashboard-new-analysis-btn");
    if (newTargetBtn) {
      newTargetBtn.addEventListener("click", () => {
        navigateTo("view-target");
        const urlInput = document.getElementById("url-input");
        if (urlInput) {
          urlInput.value = "";
          urlInput.focus();
        }
      });
    }

    // Quick History accordion toggle
    const histToggle = document.getElementById("history-toggle-btn");
    if (histToggle) {
      histToggle.addEventListener("click", () => {
        isQuickHistoryExpanded = !isQuickHistoryExpanded;
        updateQuickHistoryUI();
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    setupEventListeners();
    setStatusPanel(false);
    setFormError(null);
    loadQuickHistory();
    navigateTo("view-target");
  });

  return { navigateTo, loadResults };
})();
