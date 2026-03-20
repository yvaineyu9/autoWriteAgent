const API_BASE = "http://127.0.0.1:8765/api";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.status === 204 ? null : response.json();
}

export const api = {
  listInspirations: () => request("/inspirations"),
  listContents: (status) => request(`/contents${status ? `?status=${encodeURIComponent(status)}` : ""}`),
  getContent: (contentId) => request(`/contents/${contentId}`),
  saveContent: (contentId, payload) =>
    request(`/contents/${contentId}`, { method: "PUT", body: JSON.stringify(payload) }),
  createInspiration: (payload) =>
    request("/inspirations", { method: "POST", body: JSON.stringify(payload) }),
  updateInspiration: (path, payload) =>
    request(`/inspirations/${encodeURI(path)}`, { method: "PUT", body: JSON.stringify(payload) }),
  activateInspiration: (path) =>
    request("/inspiration-actions/activate", { method: "POST", body: JSON.stringify({ path }) }),
  createDraft: (contentId, payload) =>
    request(`/contents/${contentId}/draft`, { method: "POST", body: JSON.stringify(payload) }),
  finalizeContent: (contentId) =>
    request(`/contents/${contentId}/finalize`, { method: "POST" }),
  recommendSelection: (payload) =>
    request("/selection/recommend", { method: "POST", body: JSON.stringify(payload) }),
  confirmSelection: (payload) =>
    request("/selection/confirm", { method: "POST", body: JSON.stringify(payload) }),
  listPublications: () => request("/publications"),
  publishPublication: (publicationId, payload = {}) =>
    request(`/publications/${publicationId}/publish`, { method: "POST", body: JSON.stringify(payload) }),
  createPublicationMetric: (publicationId, payload) =>
    request(`/publications/${publicationId}/metrics`, { method: "POST", body: JSON.stringify(payload) }),
};

export function subscribeTask(taskId, onMessage) {
  const stream = new EventSource(`${API_BASE}/tasks/${taskId}/events`);
  stream.onmessage = (event) => {
    onMessage(JSON.parse(event.data));
  };
  return () => stream.close();
}
