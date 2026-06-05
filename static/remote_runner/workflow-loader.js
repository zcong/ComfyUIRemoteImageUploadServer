import { apiClient } from "./api-client.js";
import { parsePlaceholders } from "./parser-engine.js";

export async function loadWorkflow(workflowFile) {
  const response = await apiClient.loadWorkflow(workflowFile);
  return {
    workflow: response.workflow,
    placeholders: response.placeholders ?? parsePlaceholders(response.workflow),
    workflowName: response.workflowName ?? workflowFile?.name ?? "uploaded-api-workflow",
  };
}
