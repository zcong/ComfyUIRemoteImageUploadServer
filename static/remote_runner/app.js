import { defaultConfig } from "./config.js";
import { apiClient } from "./api-client.js";
import { loadWorkflow } from "./workflow-loader.js";
import { buildWorkflow } from "./workflow-builder.js";
import { TextareaField, ImagePickerField } from "./form-renderer.js";
import { JobMonitor } from "./job-monitor.js";

const BASE_URL_STORAGE_KEY = "remote-runner.base-url";

const state = {
  config: { ...defaultConfig },
  workflowTemplate: null,
  workflowName: "",
  placeholders: [],
  formState: {},
  promptId: "",
  results: [],
  mediaItems: [],
  uploadDir: "images",
  workflowFile: null,
};

const elements = {
  baseUrl: document.querySelector("#base-url"),
  workflowFile: document.querySelector("#workflow-file"),
  loadWorkflowButton: document.querySelector("#load-workflow-button"),
  runButton: document.querySelector("#run-button"),
  refreshResultsButton: document.querySelector("#refresh-results-button"),
  dynamicForm: document.querySelector("#dynamic-form"),
  formEmpty: document.querySelector("#form-empty"),
  workflowSummary: document.querySelector("#workflow-summary"),
  workflowPreview: document.querySelector("#workflow-preview"),
  statusBadge: document.querySelector(".status-badge"),
  statusMessage: document.querySelector("#status-message"),
  statusPromptId: document.querySelector("#status-prompt-id"),
  statusWorkflowName: document.querySelector("#status-workflow-name"),
  statusFieldCount: document.querySelector("#status-field-count"),
  statusUpdatedAt: document.querySelector("#status-updated-at"),
  resultsGrid: document.querySelector("#results-grid"),
  resultsEmpty: document.querySelector("#results-empty"),
  responseDetail: document.querySelector("#response-detail"),
  responseStatus: document.querySelector("#response-status"),
  responseUrl: document.querySelector("#response-url"),
  responseContentType: document.querySelector("#response-content-type"),
  responseBody: document.querySelector("#response-body"),
};

const monitor = new JobMonitor({
  fetchHistory: (baseUrl, promptId) => apiClient.getHistory(baseUrl, promptId),
  onUpdate: (payload) => {
    renderStatus(payload.status, payload.message, payload.promptId);
    renderRemoteResponse(null);
    state.results = payload.results ?? [];
    renderResults(state.results);
  },
  onError: (error) => {
    renderStatus("failed", error.message || "状态查询失败", state.promptId);
    renderRemoteResponse(error.remoteResponse);
    renderResults(state.results);
  },
});

function syncConfigFromInputs() {
  state.config.baseUrl = elements.baseUrl.value.trim();
  window.localStorage.setItem(BASE_URL_STORAGE_KEY, state.config.baseUrl);
}

async function refreshMediaItems() {
  const mediaPayload = await apiClient.getMedia({ bustCache: true });
  state.mediaItems = mediaPayload.items ?? [];
  return state.mediaItems;
}

function renderSummary() {
  if (!state.workflowTemplate) {
    elements.workflowSummary.classList.add("hidden");
    return;
  }

  elements.workflowSummary.classList.remove("hidden");
  elements.workflowSummary.innerHTML = `
    <strong>${state.workflowName}</strong>
    <p>已加载 ${state.placeholders.length} 个动态字段，支持重复加载和运行时替换。</p>
  `;
}

function renderDynamicForm() {
  elements.dynamicForm.innerHTML = "";
  elements.formEmpty.classList.toggle("hidden", Boolean(state.workflowTemplate) && state.placeholders.length > 0);
  elements.runButton.disabled = !state.workflowTemplate;
  elements.statusFieldCount.textContent = String(state.placeholders.length);

  if (state.workflowTemplate && state.placeholders.length === 0) {
    elements.formEmpty.querySelector("p").textContent = "当前 workflow 没有 `{input}` 或 `{image}` 占位符，可以直接运行。";
  } else {
    elements.formEmpty.querySelector("p").textContent = "先加载 workflow，系统会根据 `{input}` 和 `{image}` 自动生成表单。";
  }

  state.placeholders.forEach((item) => {
    const fieldKey = `${item.nodeId}::${item.fieldPath}`;
    const currentValue = state.formState[fieldKey] ?? "";
    const onChange = (value) => {
      state.formState[fieldKey] = value;
      elements.workflowPreview.textContent = JSON.stringify(
        buildWorkflow(state.workflowTemplate, state.formState),
        null,
        2,
      );
    };

    const node =
      item.type === "image"
        ? ImagePickerField(item, currentValue, onChange, {
            mediaItems: state.mediaItems,
            serverOrigin: window.location.origin,
            uploadDir: state.uploadDir,
            onOpen: refreshMediaItems,
          })
        : TextareaField(item, currentValue, onChange);
    elements.dynamicForm.append(node);
  });

  if (state.workflowTemplate) {
    elements.workflowPreview.textContent = JSON.stringify(
      buildWorkflow(state.workflowTemplate, state.formState),
      null,
      2,
    );
  }
}

function renderStatus(status, message, promptId = "") {
  const badge = elements.statusBadge;
  badge.textContent = status;
  badge.className = `status-badge status-${status}`;
  elements.statusMessage.textContent = message;
  elements.statusPromptId.textContent = promptId || "-";
  elements.statusWorkflowName.textContent = state.workflowName || "-";
  elements.statusUpdatedAt.textContent = new Date().toLocaleString();
  elements.refreshResultsButton.disabled = !promptId;
}

function getHeaderValue(headers = {}, name) {
  const target = name.toLowerCase();
  const entry = Object.entries(headers).find(([key]) => key.toLowerCase() === target);
  return entry?.[1] ?? "-";
}

function formatRemoteResponse(remoteResponse) {
  const sections = [];
  if (remoteResponse.detail) {
    sections.push(`Detail:\n${remoteResponse.detail}`);
  }
  if (remoteResponse.headers && Object.keys(remoteResponse.headers).length > 0) {
    sections.push(`Headers:\n${JSON.stringify(remoteResponse.headers, null, 2)}`);
  }
  sections.push(`Body:\n${remoteResponse.body || "(empty response body)"}`);
  if (remoteResponse.truncated) {
    sections.push("Response body was truncated in the local display.");
  }
  return sections.join("\n\n");
}

function renderRemoteResponse(remoteResponse) {
  const hasResponse = Boolean(remoteResponse);
  elements.responseDetail.classList.toggle("hidden", !hasResponse);
  if (!hasResponse) {
    elements.responseStatus.textContent = "-";
    elements.responseUrl.textContent = "-";
    elements.responseContentType.textContent = "-";
    elements.responseBody.textContent = "";
    return;
  }

  const method = remoteResponse.method || "GET";
  const status = remoteResponse.status ? `HTTP ${remoteResponse.status}` : "No HTTP status";
  elements.responseStatus.textContent = `${method} ${status}`;
  elements.responseUrl.textContent = remoteResponse.url || "-";
  elements.responseContentType.textContent = getHeaderValue(remoteResponse.headers, "content-type");
  elements.responseBody.textContent = formatRemoteResponse(remoteResponse);
}

function renderResults(results) {
  elements.resultsGrid.innerHTML = "";
  const hasResponseDetail = !elements.responseDetail.classList.contains("hidden");
  elements.resultsEmpty.classList.toggle("hidden", results.length > 0 || hasResponseDetail);

  results.forEach((item) => {
    const card = document.createElement("article");
    card.className = "result-card";

    const media = document.createElement(item.kind === "video" ? "video" : "img");
    media.src = item.url;
    if (item.kind === "video") {
      media.controls = true;
    }
    media.alt = item.filename;

    const meta = document.createElement("div");
    meta.className = "result-meta";
    meta.innerHTML = `<strong>Node ${item.nodeId}</strong><span>${item.filename}</span>`;

    card.append(media, meta);
    elements.resultsGrid.append(card);
  });
}

async function bootstrap() {
  const payload = await apiClient.getConfig().catch(() => ({ defaults: defaultConfig }));
  Object.assign(state.config, payload.defaults ?? {});
  state.uploadDir = payload.uploadDir ?? "images";
  const savedBaseUrl = window.localStorage.getItem(BASE_URL_STORAGE_KEY)?.trim();
  if (savedBaseUrl) {
    state.config.baseUrl = savedBaseUrl;
  }
  state.mediaItems = (await apiClient.getMedia().catch(() => ({ items: [] }))).items ?? [];

  elements.baseUrl.value = state.config.baseUrl;
  renderStatus("idle", "等待加载 workflow。");
  renderRemoteResponse(null);
  renderResults([]);
}

async function handleLoadWorkflow() {
  syncConfigFromInputs();
  const [workflowFile] = elements.workflowFile.files ?? [];
  if (!workflowFile) {
    throw new Error("请先选择一个 API workflow JSON 文件");
  }

  state.workflowFile = workflowFile;
  renderStatus("running", "正在解析上传的 API workflow...");

  const payload = await loadWorkflow(workflowFile);
  state.workflowTemplate = payload.workflow;
  state.workflowName = payload.workflowName;
  state.placeholders = payload.placeholders;
  state.formState = {};
  state.promptId = "";
  state.results = [];

  renderSummary();
  renderDynamicForm();
  renderRemoteResponse(null);
  renderResults([]);
  renderStatus("idle", "API workflow 已加载，可以填写表单并运行。");
}

function handleWorkflowFileChange() {
  if (!(elements.workflowFile.files ?? []).length) {
    return;
  }

  handleLoadWorkflow().catch((error) => {
    renderStatus("failed", error.message || "加载 workflow 失败");
    renderRemoteResponse(error.remoteResponse);
    renderResults(state.results);
  });
}

async function handleRunWorkflow() {
  if (!state.workflowTemplate) {
    return;
  }

  syncConfigFromInputs();
  const runtimeWorkflow = buildWorkflow(state.workflowTemplate, state.formState);
  elements.workflowPreview.textContent = JSON.stringify(runtimeWorkflow, null, 2);
  state.results = [];
  renderRemoteResponse(null);
  renderResults([]);
  renderStatus("queued", "正在提交 workflow 到远端 ComfyUI...");

  const payload = await apiClient.submitPrompt({
    baseUrl: state.config.baseUrl,
    template: state.workflowTemplate,
    formState: state.formState,
  });

  state.promptId = payload.promptId;
  renderStatus(payload.status, "Workflow 已提交，开始轮询状态。", payload.promptId);
  await monitor.start({ baseUrl: state.config.baseUrl, promptId: payload.promptId });
}

async function handleRefreshResults() {
  if (!state.promptId) {
    return;
  }
  const payload = await apiClient.getHistory(state.config.baseUrl, state.promptId);
  renderStatus(payload.status, payload.message, payload.promptId);
  renderRemoteResponse(null);
  state.results = payload.results ?? [];
  renderResults(state.results);
}

elements.loadWorkflowButton.addEventListener("click", () => {
  handleLoadWorkflow().catch((error) => {
    renderStatus("failed", error.message || "加载 workflow 失败");
    renderRemoteResponse(error.remoteResponse);
    renderResults(state.results);
  });
});

elements.workflowFile.addEventListener("change", handleWorkflowFileChange);

elements.runButton.addEventListener("click", () => {
  handleRunWorkflow().catch((error) => {
    renderStatus("failed", error.message || "执行 workflow 失败", state.promptId);
    renderRemoteResponse(error.remoteResponse);
    renderResults(state.results);
  });
});

elements.refreshResultsButton.addEventListener("click", () => {
  handleRefreshResults().catch((error) => {
    renderStatus("failed", error.message || "刷新结果失败", state.promptId);
    renderRemoteResponse(error.remoteResponse);
    renderResults(state.results);
  });
});

elements.baseUrl.addEventListener("input", () => {
  syncConfigFromInputs();
});

bootstrap();
