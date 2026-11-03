// Thin wrapper around the PodLens REST API. All frontend-backend
// communication goes through this module; no direct database access.
const PodLensApi = (() => {
  const BASE = "/api";

  async function handleResponse(response) {
    if (!response.ok) {
      let detail = `Request failed with status ${response.status}`;
      try {
        const body = await response.json();
        if (body && body.detail) detail = body.detail;
      } catch (_) {
        // ignore JSON parse failure, keep generic message
      }
      throw new Error(detail);
    }
    return response.json();
  }

  async function startAnalysis(url) {
    const response = await fetch(`${BASE}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    return handleResponse(response);
  }

  async function getStatus(analysisId) {
    const response = await fetch(`${BASE}/analysis/${analysisId}/status`);
    return handleResponse(response);
  }

  async function getDashboard(analysisId) {
    const response = await fetch(`${BASE}/analysis/${analysisId}/dashboard`);
    return handleResponse(response);
  }

  async function getComments(analysisId, { spam, sentiment, search, page, pageSize }) {
    const params = new URLSearchParams();
    if (spam) params.set("spam", spam);
    if (sentiment) params.set("sentiment", sentiment);
    if (search) params.set("search", search);
    params.set("page", page || 1);
    params.set("page_size", pageSize || 25);

    const response = await fetch(`${BASE}/analysis/${analysisId}/comments?${params.toString()}`);
    return handleResponse(response);
  }

  async function getReport(analysisId) {
    const response = await fetch(`${BASE}/analysis/${analysisId}/report`);
    return handleResponse(response);
  }

  async function getHistory() {
    const response = await fetch(`${BASE}/history`);
    return handleResponse(response);
  }

  async function deleteHistory(videoId) {
    const response = await fetch(`${BASE}/history/${encodeURIComponent(videoId)}`, {
      method: "DELETE",
    });
    return handleResponse(response);
  }

  return { startAnalysis, getStatus, getDashboard, getComments, getReport, getHistory, deleteHistory };
})();
