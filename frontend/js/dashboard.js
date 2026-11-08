// Renders the dashboard view (stat cards, sentiment chart, insights, important comments).
const PodLensDashboard = (() => {
  let chartInstance = null;

  function sentimentBadgeClass(label) {
    if (label === "positive") return "badge-positive";
    if (label === "negative") return "badge-negative";
    if (label === "neutral") return "badge-neutral";
    return "badge-unknown";
  }

  function renderStatCards(data) {
    document.getElementById("stat-total-comments").textContent = data.total_comments_collected;
    document.getElementById("stat-spam-count").textContent = data.spam_count;
    document.getElementById("stat-spam-label").textContent =
      `Spam comments (${data.spam_percentage}%)`;
    document.getElementById("stat-analyzed-count").textContent = data.total_comments_analyzed;
  }

  function renderSentimentChart(sentiment) {
    const canvas = document.getElementById("sentiment-chart");
    const ctx = canvas.getContext("2d");

    if (chartInstance) {
      chartInstance.destroy();
    }

    if (!sentiment || sentiment.total_analyzed === 0) {
      chartInstance = null;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }

    chartInstance = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: ["Positive", "Negative", "Neutral"],
        datasets: [
          {
            data: [sentiment.positive, sentiment.negative, sentiment.neutral],
            backgroundColor: ["#2ecc71", "#e74c3c", "#95a5a6"],
            borderWidth: 0,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: "bottom", labels: { color: "#e7e9ee" } },
        },
      },
    });
  }

  function renderInsights(insights) {
    const summaryEl = document.getElementById("audience-summary");
    const topicsEl = document.getElementById("future-topics");

    if (insights.status === "available" && insights.audience_summary) {
      summaryEl.innerHTML = `<p>${escapeHtml(insights.audience_summary)}</p>`;
      if (insights.discussion_themes && insights.discussion_themes.length) {
        const themes = insights.discussion_themes.map((t) => escapeHtml(t)).join(", ");
        summaryEl.innerHTML += `<p class="muted">Main themes: ${themes}</p>`;
      }
    } else {
      const reason = insights.error || "Audience insights are unavailable.";
      summaryEl.innerHTML = `<p class="muted">${escapeHtml(reason)}</p>`;
    }

    topicsEl.innerHTML = "";
    const futureTopics = (insights.future_topics || []).slice(0, 5);
    if (futureTopics.length) {
      futureTopics.forEach((topic) => {
        const li = document.createElement("li");
        li.textContent = topic;
        topicsEl.appendChild(li);
      });
    } else {
      const li = document.createElement("li");
      li.className = "muted";
      li.textContent = "No topic suggestions available.";
      topicsEl.appendChild(li);
    }
  }

  function renderImportantComments(comments) {
    const listEl = document.getElementById("important-comments");
    listEl.innerHTML = "";

    if (!comments || comments.length === 0) {
      const li = document.createElement("li");
      li.className = "muted";
      li.textContent = "No important comments identified.";
      listEl.appendChild(li);
      return;
    }

    comments.forEach((comment) => {
      const li = document.createElement("li");
      const sentimentBadge = comment.sentiment_label
        ? `<span class="badge ${sentimentBadgeClass(comment.sentiment_label)}">${comment.sentiment_label}</span>`
        : "";
      li.innerHTML = `
        <p class="comment-text">${escapeHtml(comment.original_text)}</p>
        <div class="comment-meta">
          <span>${comment.author_display_name ? escapeHtml(comment.author_display_name) : "Anonymous"}</span>
          <span>${comment.like_count} likes</span>
          ${sentimentBadge}
        </div>
      `;
      listEl.appendChild(li);
    });
  }

  function renderWarnings(warnings) {
    const el = document.getElementById("dashboard-warnings");
    if (warnings && warnings.length) {
      el.textContent = "Note: " + warnings.join(" ");
      el.hidden = false;
    } else {
      el.textContent = "";
      el.hidden = true;
    }
  }

  function render(data) {
    document.getElementById("video-title").textContent = data.video.title || "(title unavailable)";
    const metaParts = [];
    if (data.video.channel_title) metaParts.push(data.video.channel_title);
    if (typeof data.video.view_count === "number") metaParts.push(`${data.video.view_count.toLocaleString()} views`);
    document.getElementById("video-meta").textContent = metaParts.join(" • ");

    renderStatCards(data);
    renderSentimentChart(data.sentiment);
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
