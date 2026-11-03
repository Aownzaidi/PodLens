// Renders the full analysis report tab from the same stored results as the dashboard.
const PodLensReport = (() => {
  async function load(analysisId) {
    const container = document.getElementById("report-content");
    container.innerHTML = '<p class="muted">Loading report…</p>';

    try {
      const data = await PodLensApi.getReport(analysisId);
      render(data);
    } catch (err) {
      container.innerHTML = `<p class="muted">Failed to load report: ${PodLensDashboard.escapeHtml(err.message)}</p>`;
    }
  }

  function render(data) {
    const container = document.getElementById("report-content");
    const esc = PodLensDashboard.escapeHtml;

    const warningsHtml = data.warnings && data.warnings.length
      ? `<p class="warnings-text">Warnings: ${esc(data.warnings.join(" "))}</p>`
      : "";

    const partialNotice = data.is_partial
      ? `<p class="warnings-text">This analysis is incomplete (status: ${esc(data.status)}). Some sections below may be missing.</p>`
      : "";

    const importantHtml = data.important_comments.length
      ? data.important_comments
          .map(
            (c) => `<li><p class="comment-text">${esc(c.original_text)}</p>
              <div class="comment-meta"><span>${c.like_count} likes</span>${c.sentiment_label ? `<span class="badge ${PodLensDashboard.sentimentBadgeClass(c.sentiment_label)}">${c.sentiment_label}</span>` : ""}</div></li>`
          )
          .join("")
      : '<li class="muted">None identified.</li>';

    const themesHtml = data.insights.discussion_themes && data.insights.discussion_themes.length
      ? data.insights.discussion_themes.map((t) => `<li>${esc(t)}</li>`).join("")
      : '<li class="muted">None available.</li>';

    const topicsHtml = data.insights.future_topics && data.insights.future_topics.length
      ? data.insights.future_topics.map((t) => `<li>${esc(t)}</li>`).join("")
      : '<li class="muted">None available.</li>';

    const summaryHtml = data.insights.status === "available" && data.insights.audience_summary
      ? `<p>${esc(data.insights.audience_summary)}</p>`
      : `<p class="muted">${esc(data.insights.error || "Audience summary unavailable.")}</p>`;

    container.innerHTML = `
      ${partialNotice}
      ${warningsHtml}

      <h3>Video information</h3>
      <p><strong>${esc(data.video.title || "(title unavailable)")}</strong></p>
      <p class="muted">${esc(data.video.channel_title || "")}</p>

      <h3>Collection &amp; analysis statistics</h3>
      <ul class="topic-list">
        <li>Total comments collected: ${data.total_comments_collected}</li>
        <li>Comments analyzed for sentiment: ${data.total_comments_analyzed}</li>
        <li>Spam comments: ${data.spam_count} (${data.spam_percentage}%)</li>
      </ul>

      <h3>Sentiment distribution</h3>
      <ul class="topic-list">
        <li>Positive: ${data.sentiment.positive}</li>
        <li>Negative: ${data.sentiment.negative}</li>
        <li>Neutral: ${data.sentiment.neutral}</li>
      </ul>

      <h3>Important comments</h3>
      <ul class="comment-list">${importantHtml}</ul>

      <h3>Audience reaction summary</h3>
      ${summaryHtml}

      <h3>Discussion themes</h3>
      <ul class="topic-list">${themesHtml}</ul>

      <h3>Future topic suggestions</h3>
      <ul class="topic-list">${topicsHtml}</ul>
    `;
  }

  return { load };
})();
