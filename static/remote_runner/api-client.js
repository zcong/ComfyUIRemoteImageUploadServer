async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    ...options,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

export const apiClient = {
  async getConfig() {
    return requestJson("/api/remote-runner/config");
  },
  async getMedia() {
    return requestJson("/api/remote-runner/media");
  },
  async loadWorkflow(workflowFile) {
    const formData = new FormData();
    formData.append("workflowFile", workflowFile);

    const response = await fetch("/api/remote-runner/workflows/load", {
      method: "POST",
      body: formData,
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || `Request failed: ${response.status}`);
    }
    return payload;
  },
  async submitPrompt({ baseUrl, template, formState }) {
    return requestJson("/api/remote-runner/prompts/submit", {
      method: "POST",
      body: JSON.stringify({ baseUrl, template, formState }),
    });
  },
  async getHistory(baseUrl, promptId) {
    const params = new URLSearchParams({ baseUrl });
    return requestJson(`/api/remote-runner/prompts/${encodeURIComponent(promptId)}/history?${params.toString()}`);
  },
};
