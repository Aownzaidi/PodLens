// Renders the executive audience intelligence briefing report
const PodLensReport = (() => {
  async function load(analysisId) {
    const container = document.getElementById("report-content");
    if (!container) return;
    container.innerHTML = '<p class="text-dim" style="padding: 2rem 0; text-align: center;">Generating executive audience intelligence report…</p>';

    try {
      const data = await PodLensApi.getReport(analysisId);
      render(data);
    } catch (err) {
      container.innerHTML = `<p class="text-dim" style="padding: 2rem 0; text-align: center;">Failed to load report: ${PodLensDashboard.escapeHtml(err.message)}</p>`;
    }
  }

  function render(data) {
    const container = document.getElementById("report-content");
    if (!container) return;
    const esc = PodLensDashboard.escapeHtml;

    // Notice & Warnings
    const warningsHtml = data.warnings && data.warnings.length
      ? `<div class="report-alert-banner report-alert-warning">
          <strong>⚠ Processing Notice:</strong> ${esc(data.warnings.join(" "))}
        </div>`
      : "";

    const partialNotice = data.is_partial
      ? `<div class="report-alert-banner report-alert-info">
          <strong>ℹ Incomplete Pipeline:</strong> Analysis finished with status "${esc(data.status)}". Some sections may be preliminary.
        </div>`
      : "";

    // Sentiment Calculations (guarantees no "undefined%" ever)
    const pos = (data.sentiment && typeof data.sentiment.positive === "number") ? data.sentiment.positive : 0;
    const neg = (data.sentiment && typeof data.sentiment.negative === "number") ? data.sentiment.negative : 0;
    const neu = (data.sentiment && typeof data.sentiment.neutral === "number") ? data.sentiment.neutral : 0;
    const sTotal = (data.sentiment && data.sentiment.total_analyzed)
      ? data.sentiment.total_analyzed
      : ((pos + neg + neu) || (data.total_comments_analyzed || 1));

    const posPct = ((pos / sTotal) * 100).toFixed(1);
    const negPct = ((neg / sTotal) * 100).toFixed(1);
    const neuPct = ((neu / sTotal) * 100).toFixed(1);
    const avgScore = sTotal > 0 ? ((pos * 1.0 + neu * 0.5) / sTotal).toFixed(3) : "0.000";

    // Clean Author Names (prevents "@@" double-at bug)
    const importantHtml = data.important_comments && data.important_comments.length
      ? data.important_comments
          .map((c) => {
            const rawAuthor = c.author_display_name
              ? c.author_display_name.trim().replace(/^@+/, "")
              : "audience_member";

            const badgeClass = PodLensDashboard.sentimentBadgeClass(c.sentiment_label);
            const badgeLabel = c.sentiment_label ? c.sentiment_label.toUpperCase() : "NEUTRAL";

            return `
              <div class="report-comment-card">
                <p class="report-comment-quote">"${esc(c.original_text)}"</p>
                <div class="report-comment-footer">
                  <span class="report-comment-author">@${esc(rawAuthor)}</span>
                  <span class="report-comment-meta">${c.like_count || 0} likes</span>
                  <span class="report-badge report-badge-${badgeClass.replace('badge-', '')}">${badgeLabel}</span>
                </div>
              </div>
            `;
          })
          .join("")
      : '<p class="text-dim">No high-impact comments detected.</p>';

    // Themes
    const themesHtml = data.insights && data.insights.discussion_themes && data.insights.discussion_themes.length
      ? data.insights.discussion_themes
          .map((t) => `<div class="report-theme-pill"># ${esc(t)}</div>`)
          .join("")
      : '<span class="text-dim">No specific themes identified.</span>';

    // Future Topics (numbered 01 to 05)
    const futureTopics = data.insights && data.insights.future_topics ? data.insights.future_topics.slice(0, 5) : [];
    const topicsHtml = futureTopics.length
      ? futureTopics
          .map((t, i) => `
            <div class="report-topic-row">
              <span class="report-topic-idx">[0${i + 1}]</span>
              <span class="report-topic-text">${esc(t)}</span>
            </div>
          `)
          .join("")
      : '<p class="text-dim">No future topic suggestions available.</p>';

    // Audience Summary
    const summaryHtml = data.insights && data.insights.status === "available" && data.insights.audience_summary
      ? `<p class="report-summary-text">${esc(data.insights.audience_summary)}</p>`
      : `<p class="text-dim">${esc((data.insights && data.insights.error) || "Audience summary unavailable.")}</p>`;

    // Format Dates nicely
    const generatedDateStr = data.generated_at ? new Date(data.generated_at).toLocaleString() : new Date().toLocaleString();

    container.innerHTML = `
      <div class="report-doc">
        <!-- Print & Screen Header Block -->
        <div class="report-header-block">
          <div class="report-title-area">
            <h1 class="report-main-title">PODLENS AUDIENCE INTELLIGENCE REPORT</h1>
            <p class="report-sub-title">EXECUTIVE BRIEFING • YOUTUBE COMMENT PIPELINE</p>
          </div>
          <div class="report-meta-box">
            <div><strong>Report Date:</strong> ${esc(generatedDateStr)}</div>
            <div><strong>Analysis ID:</strong> #${data.analysis_id}</div>
            <div><strong>Status:</strong> <span class="report-status-tag">${esc(data.status.toUpperCase())}</span></div>
          </div>
        </div>

        ${partialNotice}
        ${warningsHtml}

        <!-- 01 // Target Metadata -->
        <div class="report-target-meta-card">
          <div class="report-meta-tag">TARGET PODCAST VIDEO</div>
          <h2 class="report-video-title">${esc(data.video.title || "(Title Unavailable)")}</h2>
          <div class="report-target-details-row">
            <span><strong>Channel:</strong> ${esc(data.video.channel_title || "Unknown")}</span>
            <span><strong>Views:</strong> ${data.video.view_count ? data.video.view_count.toLocaleString() : "N/A"}</span>
            <span><strong>Video ID:</strong> ${esc(data.video.video_id || "-")}</span>
          </div>
        </div>

        <!-- 02 // Key Collection & Audience Metrics Grid -->
        <div class="report-section-header">
          <span>01 // KEY AUDIENCE METRICS</span>
        </div>
        <div class="report-kpi-grid">
          <div class="report-kpi-card">
            <span class="report-kpi-label">TOTAL COMMENTS</span>
            <span class="report-kpi-val">${data.total_comments_collected}</span>
            <span class="report-kpi-note">Retrieved from video</span>
          </div>
          <div class="report-kpi-card">
            <span class="report-kpi-label">ANALYZED COMMENTS</span>
            <span class="report-kpi-val">${data.total_comments_analyzed}</span>
            <span class="report-kpi-note">Processed for sentiment</span>
          </div>
          <div class="report-kpi-card">
            <span class="report-kpi-label">SPAM DETECTED</span>
            <span class="report-kpi-val">${data.spam_count}</span>
            <span class="report-kpi-note">${data.spam_percentage}% of total</span>
          </div>
          <div class="report-kpi-card">
            <span class="report-kpi-label">AVG SENTIMENT</span>
            <span class="report-kpi-val">${avgScore}</span>
            <span class="report-kpi-note">Scale 0.0 to 1.0</span>
          </div>
        </div>

        <!-- 03 // Sentiment Breakdown with Visual Bars -->
        <div class="report-section-header">
          <span>02 // SENTIMENT BREAKDOWN</span>
        </div>
        <div class="report-sentiment-container">
          <div class="report-sentiment-bars-wrap">
            <div class="report-sentiment-row">
              <span class="report-bar-label">Positive</span>
              <div class="report-bar-track">
                <div class="report-bar-fill report-fill-positive" style="width: ${posPct}%;"></div>
              </div>
              <span class="report-bar-stat">${pos} (${posPct}%)</span>
            </div>
            <div class="report-sentiment-row">
              <span class="report-bar-label">Negative</span>
              <div class="report-bar-track">
                <div class="report-bar-fill report-fill-negative" style="width: ${negPct}%;"></div>
              </div>
              <span class="report-bar-stat">${neg} (${negPct}%)</span>
            </div>
            <div class="report-sentiment-row">
              <span class="report-bar-label">Neutral</span>
              <div class="report-bar-track">
                <div class="report-bar-fill report-fill-neutral" style="width: ${neuPct}%;"></div>
              </div>
              <span class="report-bar-stat">${neu} (${neuPct}%)</span>
            </div>
          </div>
        </div>

        <!-- 04 // Audience Reaction Summary -->
        <div class="report-section-header">
          <span>03 // AUDIENCE REACTION SUMMARY</span>
        </div>
        <div class="report-content-box">
          ${summaryHtml}
        </div>

        <!-- 05 // Key Discussion Themes -->
        <div class="report-section-header">
          <span>04 // KEY AUDIENCE THEMES</span>
        </div>
        <div class="report-themes-wrap">
          ${themesHtml}
        </div>

        <!-- 06 // Suggested Future Topics -->
        <div class="report-section-header">
          <span>05 // RECOMMENDED FUTURE TOPICS</span>
        </div>
        <div class="report-topics-grid">
          ${topicsHtml}
        </div>

        <!-- 07 // High-Impact Audience Comments -->
        <div class="report-section-header">
          <span>06 // HIGH-IMPACT AUDIENCE COMMENTS</span>
        </div>
        <div class="report-comments-wrap">
          ${importantHtml}
        </div>

        <!-- Document Footer -->
        <div class="report-document-footer">
          <span>PodLens Comment Intelligence Pipeline • Generated for FYP Audience Research</span>
          <span>Confidential &amp; Proprietary Analysis</span>
        </div>
      </div>
    `;

    // Wire up direct PDF download button
    const downloadBtn = document.getElementById("download-pdf-btn");
    if (downloadBtn) {
      downloadBtn.onclick = downloadPdf;
    }
  }

  async function downloadPdf() {
    const reportDoc = document.querySelector(".report-doc");
    if (!reportDoc) return;

    const downloadBtn = document.getElementById("download-pdf-btn");
    const origHtml = downloadBtn ? downloadBtn.innerHTML : "";
    if (downloadBtn) {
      downloadBtn.disabled = true;
      downloadBtn.innerHTML = `<span>⏳</span> <span>Generating PDF…</span>`;
    }

    let wrapper = null;
    const prevScrollX = window.scrollX;
    const prevScrollY = window.scrollY;

    try {
      // Dynamic load fallback if html2pdf is not ready
      if (typeof html2pdf === "undefined") {
        await new Promise((resolve, reject) => {
          const s = document.createElement("script");
          s.src = "https://cdn.jsdelivr.net/npm/html2pdf.js@0.10.1/dist/html2pdf.bundle.min.js";
          s.onload = resolve;
          s.onerror = () => {
            const s2 = document.createElement("script");
            s2.src = "https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js";
            s2.onload = resolve;
            s2.onerror = reject;
            document.head.appendChild(s2);
          };
          document.head.appendChild(s);
        });
      }

      const titleEl = document.querySelector(".report-video-title");
      const rawTitle = titleEl ? titleEl.textContent.trim() : "Briefing";
      const cleanTitle = rawTitle.replace(/[^a-zA-Z0-9_-]/g, "_").replace(/_+/g, "_").slice(0, 50);
      const filename = `PodLens_Report_${cleanTitle || "Audit"}.pdf`;

      // 1. Reset scroll position to top-left to avoid coordinate offsets
      window.scrollTo(0, 0);

      // 2. Clone report into a dedicated isolated top-left container
      const clone = reportDoc.cloneNode(true);
      clone.classList.add("pdf-export-mode");

      wrapper = document.createElement("div");
      wrapper.id = "podlens-pdf-export-wrapper";
      wrapper.style.position = "absolute";
      wrapper.style.top = "0";
      wrapper.style.left = "0";
      wrapper.style.width = "750px";
      wrapper.style.margin = "0";
      wrapper.style.padding = "0";
      wrapper.style.background = "#ffffff";
      wrapper.style.zIndex = "999999";
      wrapper.appendChild(clone);
      document.body.appendChild(wrapper);

      const opt = {
        margin: [10, 10, 10, 10], // 10mm margins on all sides
        filename: filename,
        image: { type: "jpeg", quality: 0.98 },
        html2canvas: {
          scale: 2,
          useCORS: true,
          logging: false,
          x: 0,
          y: 0,
          width: 750,
          windowWidth: 750,
          scrollX: 0,
          scrollY: 0,
        },
        pagebreak: {
          mode: ["avoid-all", "css", "legacy"],
          avoid: [
            ".report-target-meta-card",
            ".report-kpi-card",
            ".report-sentiment-container",
            ".report-content-box",
            ".report-topic-row",
            ".report-comment-card",
            ".report-section-header",
            ".report-header-block",
            ".report-document-footer",
          ],
        },
        jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
      };

      // Generate PDF and trigger native browser download
      await html2pdf().set(opt).from(clone).save();
    } catch (err) {
      console.warn("Direct PDF generation error, falling back to window.print():", err);
      window.print();
    } finally {
      if (wrapper && wrapper.parentNode) {
        wrapper.parentNode.removeChild(wrapper);
      }
      window.scrollTo(prevScrollX, prevScrollY);
      if (downloadBtn) {
        downloadBtn.disabled = false;
        downloadBtn.innerHTML = origHtml;
      }
    }
  }

  return { load, downloadPdf };
})();
