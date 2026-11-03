// Handles the searchable/filterable comments table.
const PodLensComments = (() => {
  let analysisId = null;
  let currentPage = 1;
  const pageSize = 25;
  let totalItems = 0;
  let debounceTimer = null;

  function spamBadge(isSpam) {
    if (isSpam === true) return '<span class="badge badge-spam">Spam</span>';
    if (isSpam === false) return '<span class="badge badge-not-spam">Not spam</span>';
    return '<span class="badge badge-unknown">Unknown</span>';
  }

  function sentimentBadge(label) {
    if (!label) return '<span class="badge badge-unknown">N/A</span>';
    return `<span class="badge ${PodLensDashboard.sentimentBadgeClass(label)}">${label}</span>`;
  }

  async function load() {
    const spam = document.getElementById("filter-spam").value;
    const sentiment = document.getElementById("filter-sentiment").value;
    const search = document.getElementById("comment-search").value;

    try {
      const data = await PodLensApi.getComments(analysisId, {
        spam,
        sentiment,
        search,
        page: currentPage,
        pageSize,
      });
      totalItems = data.total;
      renderTable(data.items);
      renderPagination();
    } catch (err) {
      const tbody = document.getElementById("comments-tbody");
      tbody.innerHTML = `<tr><td colspan="4" class="muted">Failed to load comments: ${PodLensDashboard.escapeHtml(err.message)}</td></tr>`;
    }
  }

  function renderTable(items) {
    const tbody = document.getElementById("comments-tbody");
    tbody.innerHTML = "";

    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="muted">No comments match the current filters.</td></tr>';
      return;
    }

    items.forEach((comment) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${PodLensDashboard.escapeHtml(comment.original_text)}</td>
        <td>${comment.like_count}</td>
        <td>${spamBadge(comment.is_spam)}</td>
        <td>${sentimentBadge(comment.sentiment_label)}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  function renderPagination() {
    const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
    document.getElementById("page-indicator").textContent = `Page ${currentPage} of ${totalPages}`;
    document.getElementById("prev-page-btn").disabled = currentPage <= 1;
    document.getElementById("next-page-btn").disabled = currentPage >= totalPages;
  }

  function init(id) {
    analysisId = id;
    currentPage = 1;

    document.getElementById("filter-spam").onchange = () => {
      currentPage = 1;
      load();
    };
    document.getElementById("filter-sentiment").onchange = () => {
      currentPage = 1;
      load();
    };
    document.getElementById("comment-search").oninput = () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        currentPage = 1;
        load();
      }, 300);
    };
    document.getElementById("prev-page-btn").onclick = () => {
      if (currentPage > 1) {
        currentPage -= 1;
        load();
      }
    };
    document.getElementById("next-page-btn").onclick = () => {
      currentPage += 1;
      load();
    };

    load();
  }

  return { init };
})();
