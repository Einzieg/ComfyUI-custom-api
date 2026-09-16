export const ROOT = "/custom-model-api";

export function makeClient(api) {
  let token;
  let pending;
  const connect = async (pairing_code) => {
    const response = await api.fetchApi(ROOT + "/session", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pairing_code }) });
    const result = await response.json();
    if (!response.ok) throw result.error || new Error(`HTTP ${response.status}`);
    token = result.token;
  };
  const request = async (path, method = "GET", body) => {
    if (!token) {
      pending ||= connect().finally(() => { pending = null; });
      await pending;
    }
    const response = await api.fetchApi(ROOT + path, {
      method,
      headers: { "X-Custom-API-Session": token, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const result = await response.json();
    if (!response.ok) {
      if (response.status === 401) token = undefined;
      throw result.error || new Error(`HTTP ${response.status}`);
    }
    return result;
  };
  request.pair = connect;
  return request;
}

export function supportedOperations(config, model, allowed) {
  return allowed.filter(op => config.templates.some(template => template.id === model?.bindings?.[op] && template.kind === (["text", "vision"].includes(op) ? "text" : "image")));
}

export function selectableModels(config, allowed, providerId = "", query = "") {
  const enabled = new Set(config.providers.filter(p => p.enabled !== false).map(p => p.id));
  const search = query.trim().toLowerCase();
  return config.models.filter(model => model.enabled !== false && enabled.has(model.provider_id) &&
    (!providerId || model.provider_id === providerId) && supportedOperations(config, model, allowed).length &&
    `${model.name} ${model.model_id} ${model.group || ""} ${config.providers.find(p => p.id === model.provider_id)?.name || ""}`.toLowerCase().includes(search));
}

export function selectionValues(config, modelId, allowed, currentOperation) {
  const model = selectableModels(config, allowed).find(m => m.id === modelId);
  if (!model) return null;
  const operations = supportedOperations(config, model, allowed);
  return { provider_id: model.provider_id, model_id: model.id, operation: operations.includes(currentOperation) ? currentOperation : operations[0] };
}

export function parameterSchema(config, modelId, operation) {
  const model = config.models.find(m => m.id === modelId);
  const template = config.templates.find(t => t.id === model?.bindings?.[operation]);
  return (template?.parameters || []).map(field => ({ ...field,
    ...((model?.defaults && Object.hasOwn(model.defaults, field.name)) ? { default: model.defaults[field.name] } : {}),
  }));
}

export function parseObject(value) {
  const parsed = JSON.parse(value || "{}");
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw { code: "invalid_parameters" };
  return parsed;
}

export function downloadJSON(value, filename) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
