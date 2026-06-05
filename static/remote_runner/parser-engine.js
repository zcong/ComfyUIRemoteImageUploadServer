export function parsePlaceholders(workflow) {
  const placeholders = [];

  function walk(current, nodeId = null, path = []) {
    if (Array.isArray(current)) {
      current.forEach((value, index) => walk(value, nodeId, [...path, String(index)]));
      return;
    }

    if (current && typeof current === "object") {
      if (path.length === 0 && nodeId === null) {
        Object.entries(current).forEach(([key, value]) => walk(value, key, []));
        return;
      }

      Object.entries(current).forEach(([key, value]) => walk(value, nodeId, [...path, key]));
      return;
    }

    if (current === "{input}") {
      placeholders.push({ nodeId, fieldPath: path.join("."), type: "input" });
    }

    if (current === "{image}") {
      placeholders.push({ nodeId, fieldPath: path.join("."), type: "image" });
    }
  }

  walk(workflow);
  return placeholders;
}
