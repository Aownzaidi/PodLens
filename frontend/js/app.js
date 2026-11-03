// Top-level application controller: view switching, analysis lifecycle, polling.
(() => {
  const STATUS_LABELS = {
    pending: "Queued…",
    collecting: "Collecting video and comments from YouTube…",
    preprocessing: "Cleaning and deduplicating comments…",
    spam_detection: "Running spam detection…",
    sentiment_analysis: "Running sentiment analysis…",
    generating_insights: "Generating audience insights…",
    completed: "Analysis complete.",
    partial: "Analysis complete with some limitations.",
    failed: "Analysis failed.",
  };

  const TERMINAL_STATUSES = new Set(["completed", "partial", "failed"]);
  const POLL_INTERVAL_MS = 2500;

  let pollTimer = null;
  let currentAnalysisId = null;

  function showView(viewId) {
    document.querySelectorAll(".view").forEach((el) => (el.hidden = el.id !== viewId));
  }

  function setFormError(message) {
    const el = document.getElementById("form-error");
    if (message) {
      el.textContent = message;
      el.hidden = false;
    } else {
      el.textContent = "";
      el.hidden = true;
    }
  }

  function setStatusPanel(visible, text, warnings) {
    const panel = document.getElementById("status-panel");
    panel.hidden = !visible;
    panel.style.display = visible ? "flex" : "none";
    if (text) document.getElementById("status-text").textContent = text;
    document.getElementById("status-warnings").textContent =
      warnings && warnings.length ? "Note: " + warnings.join(" ") : "";
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
          document.getElementById("analyze-btn").disabled = false;
          return;
        }

        await loadResults(analysisId);
      }
    } catch (err) {
      clearInterval(pollTimer);
      pollTimer = null;
      setStatusPanel(false);
      setFormError(`Could not check analysis status: ${err.message}`);
      document.getElementById("analyze-btn").disabled = false;
    }
  }

  async function loadResults(analysisId) {
    try {
      const dashboardData = await PodLensApi.getDashboard(analysisId);
      setStatusPanel(false);
      showView("view-dashboard");
      PodLensDashboard.render(dashboardData);
      PodLensComments.init(analysisId);
      switchTab("comments");
      document.getElementById("analyze-btn").disabled = false;
    } catch (err) {
      setStatusPanel(false);
      setFormError(`Could not load analysis results: ${err.message}`);
      document.getElementById("analyze-btn").disabled = false;
    }
  }

  function switchTab(tabName) {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === tabName);
    });
    document.getElementById("tab-comments").hidden = tabName !== "comments";
    document.getElementById("tab-report").hidden = tabName !== "report";

    if (tabName === "report" && currentAnalysisId) {
      PodLensReport.load(currentAnalysisId);
    }
  }

  async function handleAnalyzeSubmit(event) {
    event.preventDefault();
    setFormError(null);

    const url = document.getElementById("url-input").value.trim();
    if (!url) {
      setFormError("Please enter a YouTube video URL.");
      return;
    }

    const btn = document.getElementById("analyze-btn");
    btn.disabled = true;
    setStatusPanel(true, "Starting analysis…", []);

    try {
      const result = await PodLensApi.startAnalysis(url);
      currentAnalysisId = result.analysis_id;
      pollTimer = setInterval(() => pollStatus(currentAnalysisId), POLL_INTERVAL_MS);
      pollStatus(currentAnalysisId);
    } catch (err) {
      setStatusPanel(false);
      setFormError(err.message);
      btn.disabled = false;
    }
  }

  function formatDate(dateStr) {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    return isNaN(d.getTime()) ? "" : `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear()}`;
  }

  async function loadHistory() {
    const listEl = document.getElementById("history-list");
    const emptyEl = document.getElementById("history-empty");
    if (!listEl) return;

    try {
      const items = await PodLensApi.getHistory();
      listEl.innerHTML = "";
      if (!items || items.length === 0) {
        if (emptyEl) emptyEl.hidden = false;
        return;
      }
      if (emptyEl) emptyEl.hidden = true;

      const esc = (s) => (window.PodLensDashboard ? PodLensDashboard.escapeHtml(s) : (s || ""));

      items.forEach((item) => {
        const row = document.createElement("div");
        row.className = "history-row";
        row.dataset.videoId = item.video_id;

        const mainDiv = document.createElement("div");
        mainDiv.className = "history-row-main";
        mainDiv.role = "button";
        mainDiv.tabIndex = 0;
        mainDiv.title = "Click to view analysis";
        mainDiv.innerHTML = `<span class="history-title">${esc(item.title || item.video_id)}</span>`;
        mainDiv.addEventListener("click", () => {
          if (item.analysis_id) {
            currentAnalysisId = item.analysis_id;
            loadResults(item.analysis_id);
          } else {
            document.getElementById("url-input").value = item.url;
            document.getElementById("analyze-btn").click();
          }
        });

        const metaDiv = document.createElement("div");
        metaDiv.className = "history-row-meta";
        metaDiv.innerHTML = `<span class="history-info">${item.comment_count} comments · ${formatDate(item.analyzed_at)}</span>`;

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "history-del-btn";
        delBtn.textContent = "DEL";
        delBtn.title = "Delete video and comments from database";
        delBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const title = item.title || item.video_id;
          if (!confirm(`Are you sure you want to delete "${title}" and all its comments from the database?`)) {
            return;
          }
          try {
            delBtn.disabled = true;
            delBtn.textContent = "...";
            await PodLensApi.deleteHistory(item.video_id);
            row.remove();
            const remaining = listEl.querySelectorAll(".history-row");
            if (remaining.length === 0 && emptyEl) {
              emptyEl.hidden = false;
            }
          } catch (err) {
            alert(`Failed to delete: ${err.message}`);
            delBtn.disabled = false;
            delBtn.textContent = "DEL";
          }
        });

        metaDiv.appendChild(delBtn);
        row.appendChild(mainDiv);
        row.appendChild(metaDiv);
        listEl.appendChild(row);
      });
    } catch (err) {
      console.warn("Could not load history:", err);
    }
  }

  function setupHistoryToggle() {
    const toggleBtn = document.getElementById("history-toggle-btn");
    const historyPanel = document.getElementById("history-panel");
    const toggleIcon = document.getElementById("history-toggle-icon");
    if (!toggleBtn || !historyPanel) return;

    let isExpanded = true;
    toggleBtn.addEventListener("click", () => {
      isExpanded = !isExpanded;
      historyPanel.hidden = !isExpanded;
      historyPanel.style.display = isExpanded ? "block" : "none";
      if (toggleIcon) toggleIcon.textContent = isExpanded ? "▼" : "▶";
      toggleBtn.setAttribute("aria-expanded", isExpanded);
    });
  }

  function handleNewAnalysis() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    currentAnalysisId = null;
    document.getElementById("url-input").value = "";
    setFormError(null);
    setStatusPanel(false);
    loadHistory();
    showView("view-home");
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("analyze-form").addEventListener("submit", handleAnalyzeSubmit);
    document.getElementById("new-analysis-btn").addEventListener("click", handleNewAnalysis);

    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });

    setStatusPanel(false);
    setFormError(null);
    setupHistoryToggle();
    loadHistory();
    showView("view-home");
  });
})();
