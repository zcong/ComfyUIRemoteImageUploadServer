import { apiClient } from "./api-client.js";
import { parsePlaceholders } from "./parser-engine.js";

export async function loadWorkflow(baseUrl, workflowName) {
  const response = await apiClient.loadWorkflow(baseUrl, workflowName);
  return {
    workflow: response.workflow,
    placeholders: response.placeholders ?? parsePlaceholders(response.workflow),
    workflowName: response.workflowName ?? workflowName,
  };
}

