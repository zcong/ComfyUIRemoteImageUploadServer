import { parsePlaceholders } from "./parser-engine.js";

function deepClone(value) {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function readPath(node, fieldPath) {
  return fieldPath.split(".").reduce((current, segment) => current[segment], node);
}

function writePath(node, fieldPath, value) {
  const segments = fieldPath.split(".");
  let current = node;
  for (const segment of segments.slice(0, -1)) {
    current = current[segment];
  }
  current[segments.at(-1)] = value;
}

export function applyParams(workflow, formState) {
  const cloned = deepClone(workflow);
  const placeholders = parsePlaceholders(cloned);

  placeholders.forEach((item) => {
    const fieldKey = `${item.nodeId}::${item.fieldPath}`;
    const replacement = formState[fieldKey] ?? "";
    const currentValue = readPath(cloned[item.nodeId], item.fieldPath);

    if (currentValue === "{input}") {
      writePath(cloned[item.nodeId], item.fieldPath, replacement);
    }

    if (currentValue === "{image}") {
      const imageValue = String(replacement ?? "").trim();
      writePath(cloned[item.nodeId], item.fieldPath, imageValue);
    }
  });

  return cloned;
}

export function buildWorkflow(template, formState) {
  return applyParams(template, formState);
}
