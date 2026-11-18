// Renders the dashboard view with Obsidian & Cyber-Mint Terminal aesthetics
const PodLensDashboard = (() => {
  let chartInstance = null;

  function sentimentBadgeClass(label) {
    if (label === "positive") return "badge-positive";
    if (label === "negative") return "badge-negative";
    if (label === "neutral") return "badge-neutral";
    return "badge-neutral";
  }

  function renderStatCards(data, processingTime) {
    const totalCollected = data.total_comments_collected || 0;
    const spamCount = data.spam_count || 0;
    const spamPct = data.spam_percentage != null ? data.spam_percentage.toFixed(1) : "0.0";
    const totalAnalyzed = data.total_comments_analyzed || 0;

    const elTotal = document.getElementById("stat-total-comments");
    if (elTotal) elTotal.textContent = totalCollected;

    const elTitleSub = document.getElementById("stat-video-sub");
    if (elTitleSub) {
      elTitleSub.textContent = data.video && data.video.title ? data.video.title : "Target Podcast";
    }

    const elSpam = document.getElementById("stat-spam-count");
    if (elSpam) elSpam.textContent = spamCount;

    const elSpamSub = document.getElementById("stat-spam-sub");
    if (elSpamSub) elSpamSub.textContent = `${spamPct}% of comments`;

    // Calculate Average Sentiment Score (0 = negative, 1 = positive)
    const sentiment = data.sentiment || { positive: 0, negative: 0, neutral: 0, total_analyzed: 0 };
    const pos = sentiment.positive || 0;
    const neu = sentiment.neutral || 0;
    const neg = sentiment.negative || 0;
    const sTotal = sentiment.total_analyzed || totalAnalyzed || (pos + neu + neg);

    let avgScore = "0.000";
    if (sTotal > 0) {
      // Positive weighted 1.0, neutral weighted 0.5, negative weighted 0.0
      avgScore = ((pos * 1.0 + neu * 0.5) / sTotal).toFixed(3);
    }
    const elAvgSentiment = document.getElementById("stat-avg-sentiment");
    if (elAvgSentiment) elAvgSentiment.textContent = avgScore;

    // Processing Time
    const elProcTime = document.getElementById("stat-processing-time");
    if (elProcTime) {
      elProcTime.textContent = processingTime ? `${processingTime}s` : "-";
    }
  }

  function renderSentimentBars(sentiment) {
    const pos = sentiment.positive || 0;
    const neg = sentiment.negative || 0;
    const neu = sentiment.neutral || 0;
    const total = sentiment.total_analyzed || (pos + neg + neu) || 1;

    const posPct = ((pos / total) * 100).toFixed(1);
    const negPct = ((neg / total) * 100).toFixed(1);
    const neuPct = ((neu / total) * 100).toFixed(1);

    const posFill = document.getElementById("bar-pos-fill");
    if (posFill) posFill.style.width = `${posPct}%`;
    const posStat = document.getElementById("bar-pos-stat");
    if (posStat) posStat.textContent = `${pos} (${posPct}%)`;

    const negFill = document.getElementById("bar-neg-fill");
    if (negFill) negFill.style.width = `${negPct}%`;
    const negStat = document.getElementById("bar-neg-stat");
    if (negStat) negStat.textContent = `${neg} (${negPct}%)`;

    const neuFill = document.getElementById("bar-neu-fill");
    if (neuFill) neuFill.style.width = `${neuPct}%`;
    const neuStat = document.getElementById("bar-neu-stat");
    if (neuStat) neuStat.textContent = `${neu} (${neuPct}%)`;
  }

  function renderSpamBreakdown(data) {
    const spamPct = data.spam_percentage != null ? data.spam_percentage.toFixed(1) : "0.0";
    const spamCount = data.spam_count || 0;
    const totalCollected = data.total_comments_collected || 0;
    const cleanCount = Math.max(0, totalCollected - spamCount);
    const cleanPct = totalCollected > 0 ? (((cleanCount) / totalCollected) * 100).toFixed(1) : "100.0";

    const radarPct = document.getElementById("spam-radar-pct");
    if (radarPct) radarPct.textContent = `${spamPct}%`;

    const spamFill = document.getElementById("spam-fill-bar");
    if (spamFill) spamFill.style.width = `${Math.min(100, Math.max(0, spamPct))}%`;

    const spamNum = document.getElementById("spam-stat-num");
    if (spamNum) spamNum.textContent = spamCount;

    const cleanFill = document.getElementById("clean-fill-bar");
    if (cleanFill) cleanFill.style.width = `${Math.min(100, Math.max(0, cleanPct))}%`;

    const cleanNum = document.getElementById("clean-stat-num");
    if (cleanNum) cleanNum.textContent = cleanCount;

    const analyzedNum = document.getElementById("analyzed-stat-num");
    if (analyzedNum) analyzedNum.textContent = data.total_comments_analyzed || totalCollected;
  }

  function renderInsights(insights) {
    const summaryEl = document.getElementById("audience-summary");
    const themesEl = document.getElementById("discussion-themes");
    const topicsEl = document.getElementById("future-topics-list");

    if (summaryEl) {
      if (insights && insights.status === "available" && insights.audience_summary) {
        summaryEl.textContent = insights.audience_summary;
      } else {
        const reason = (insights && insights.error) || "Audience reaction summary is unavailable for this podcast.";
        summaryEl.textContent = reason;
      }
    }

    if (themesEl) {
      themesEl.innerHTML = "";
      if (insights && insights.discussion_themes && insights.discussion_themes.length) {
        insights.discussion_themes.forEach((theme) => {
          const pill = document.createElement("span");
          pill.className = "theme-pill";
          pill.textContent = `# ${theme}`;
          themesEl.appendChild(pill);
        });
      }
    }

    if (topicsEl) {
      topicsEl.innerHTML = "";
      const topics = insights && insights.future_topics ? insights.future_topics.slice(0, 5) : [];
      if (topics.length) {
        topics.forEach((topic, idx) => {
          const item = document.createElement("div");
          item.className = "topic-item";
          item.innerHTML = `
            <span class="topic-idx">0${idx + 1}</span>
            <span class="topic-title">${escapeHtml(topic)}</span>
          `;
          topicsEl.appendChild(item);
        });
      } else {
        topicsEl.innerHTML = '<div class="text-dim" style="padding: 0.5rem 0;">No topic suggestions available.</div>';
      }
    }
  }

  function renderImportantComments(comments) {
    const gridEl = document.getElementById("important-comments-grid");
    if (!gridEl) return;
    gridEl.innerHTML = "";

    if (!comments || comments.length === 0) {
      gridEl.innerHTML = '<p class="text-dim" style="grid-column: 1 / -1;">No high-importance comments detected.</p>';
      return;
    }

    comments.forEach((c) => {
      const card = document.createElement("div");
      card.className = "important-card";

      const badgeHtml = c.sentiment_label
        ? `<span class="terminal-badge ${sentimentBadgeClass(c.sentiment_label)}">${escapeHtml(c.sentiment_label)}</span>`
        : "";

      const rawAuthor = c.author_display_name ? c.author_display_name.trim().replace(/^@+/, "") : "audience_member";

      card.innerHTML = `
        <p class="important-quote">"${escapeHtml(c.original_text)}"</p>
        <div class="important-footer">
          <span class="important-author">@${escapeHtml(rawAuthor)}</span>
          <span>${c.like_count || 0} likes</span>
          ${badgeHtml}
        </div>
      `;
      gridEl.appendChild(card);
    });
  }

  function renderWarnings(warnings) {
    const el = document.getElementById("dashboard-warnings");
    if (!el) return;
    if (warnings && warnings.length) {
      el.textContent = "⚠ Notice: " + warnings.join(" ");
      el.hidden = false;
    } else {
      el.textContent = "";
      el.hidden = true;
    }
  }

  function render(data, processingTime) {
    // 1. Video Meta Header
    const titleEl = document.getElementById("video-title");
    if (titleEl) {
      titleEl.textContent = data.video && data.video.title ? data.video.title : "(Title Unavailable)";
    }

    const metaEl = document.getElementById("video-meta");
    if (metaEl) {
      const parts = [];
      if (data.video && data.video.channel_title) parts.push(data.video.channel_title);
      if (data.video && typeof data.video.view_count === "number") {
        parts.push(`${data.video.view_count.toLocaleString()} views`);
      }
      metaEl.textContent = parts.join(" • ");
    }

    // 2. Render KPIs & Breakdowns
    renderStatCards(data, processingTime);
    renderSentimentBars(data.sentiment || {});
    renderSpamBreakdown(data);
    renderInsights(data.insights);
    renderImportantComments(data.important_comments);
    renderWarnings(data.warnings);
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  return { render, escapeHtml, sentimentBadgeClass };
})();
