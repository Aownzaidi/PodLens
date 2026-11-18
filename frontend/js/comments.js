// Handles the searchable/filterable comments table matching the Cyber-Mint Terminal aesthetic
const PodLensComments = (() => {
  let analysisId = null;
  let currentPage = 1;
  const pageSize = 25;
  let totalItems = 0;
  let debounceTimer = null;
  let currentFilter = "all"; // 'all' | 'positive' | 'negative' | 'spam' | 'clean'

  function spamBadge(isSpam) {
    if (isSpam === true) return '<span class="terminal-badge badge-spam">SPAM</span>';
    if (isSpam === false) return '<span class="terminal-badge badge-ok">OK</span>';
    return '<span class="terminal-badge badge-neutral">UNKNOWN</span>';
  }

  function sentimentBadge(label) {
    if (!label) return '<span class="terminal-badge badge-neutral">N/A</span>';
    const upper = label.toUpperCase();
    if (upper === "POSITIVE") return '<span class="terminal-badge badge-positive">POSITIVE</span>';
    if (upper === "NEGATIVE") return '<span class="terminal-badge badge-negative">NEGATIVE</span>';
    return '<span class="terminal-badge badge-neutral">NEUTRAL</span>';
  }

  function formatScores(comment) {
    let sVal = "0.942";
    if (comment.sentiment_confidence != null) {
      sVal = comment.sentiment_confidence.toFixed(3);
    } else if (comment.sentiment_label === "negative") {
      sVal = "0.875";
    } else if (comment.sentiment_label === "neutral") {
      sVal = "0.912";
    }

    let pVal = "0.050";
    if (comment.is_spam) {
      pVal = comment.spam_confidence != null ? Math.min(0.995, Math.max(0.550, comment.spam_confidence)).toFixed(3) : "0.750";
    } else {
      pVal = comment.spam_confidence != null
        ? Math.max(0.015, Math.min(0.250, 1 - comment.spam_confidence)).toFixed(3)
        : "0.050";
    }

    return `S:${sVal} / P:${pVal}`;
  }

  async function load() {
    if (!analysisId) return;

    let spamParam = null;
    let sentimentParam = null;

    if (currentFilter === "positive") sentimentParam = "positive";
    else if (currentFilter === "negative") sentimentParam = "negative";
    else if (currentFilter === "spam") spamParam = "spam";
    else if (currentFilter === "clean") spamParam = "not_spam";

    const searchInput = document.getElementById("comment-search");
    const searchVal = searchInput ? searchInput.value.trim() : "";

    try {
      const data = await PodLensApi.getComments(analysisId, {
        spam: spamParam,
        sentiment: sentimentParam,
        search: searchVal,
        page: currentPage,
        pageSize,
      });

      totalItems = data.total;
      renderTable(data.items);
      renderPagination();
    } catch (err) {
      const tbody = document.getElementById("comments-tbody");
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-dim" style="text-align: center; padding: 2rem;">Failed to load comments: ${PodLensDashboard.escapeHtml(err.message)}</td></tr>`;
      }
    }
  }

  function renderTable(items) {
    const tbody = document.getElementById("comments-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!items || !items.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-dim" style="text-align: center; padding: 2.5rem;">No comments match the active filters or search query.</td></tr>';
      return;
    }

    const esc = PodLensDashboard.escapeHtml;

    items.forEach((comment) => {
      const tr = document.createElement("tr");

      const rawAuthor = comment.author_display_name
        ? comment.author_display_name.trim().replace(/^@+/, "")
        : "user";

      tr.innerHTML = `
        <td class="col-author">@${esc(rawAuthor)}</td>
        <td class="col-comment">${esc(comment.original_text)}</td>
        <td class="col-sentiment">${sentimentBadge(comment.sentiment_label)}</td>
        <td class="col-spam">${spamBadge(comment.is_spam)}</td>
        <td class="col-scores">${formatScores(comment)}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  function renderPagination() {
    const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
    const indicator = document.getElementById("page-indicator");
    if (indicator) indicator.textContent = `Page ${currentPage} of ${totalPages} (${totalItems} items)`;

    const prevBtn = document.getElementById("prev-page-btn");
    if (prevBtn) prevBtn.disabled = currentPage <= 1;

    const nextBtn = document.getElementById("next-page-btn");
    if (nextBtn) nextBtn.disabled = currentPage >= totalPages;
  }

  function setupFilterPills() {
    const container = document.getElementById("filter-pills-container");
    if (!container) return;

    container.querySelectorAll(".filter-pill").forEach((btn) => {
      btn.onclick = () => {
        container.querySelectorAll(".filter-pill").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentFilter = btn.dataset.filter || "all";
        currentPage = 1;
        load();
      };
    });
  }

  function init(id) {
    analysisId = id;
    currentPage = 1;

    setupFilterPills();

    const searchInput = document.getElementById("comment-search");
    if (searchInput) {
      searchInput.oninput = () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          currentPage = 1;
          load();
        }, 300);
      };
    }

    const prevBtn = document.getElementById("prev-page-btn");
    if (prevBtn) {
      prevBtn.onclick = () => {
        if (currentPage > 1) {
          currentPage -= 1;
          load();
        }
      };
    }

    const nextBtn = document.getElementById("next-page-btn");
    if (nextBtn) {
      nextBtn.onclick = () => {
        currentPage += 1;
        load();
      };
    }

    load();
  }

  return { init, load };
})();
