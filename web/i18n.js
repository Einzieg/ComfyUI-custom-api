export const dictionaries = {};
let activeLanguage = "en";
let application;

export function resolveLanguage(hostLanguage) {
  return /^zh(?:-|$)/i.test(hostLanguage || "en") ? "zh" : "en";
}

export async function initializeI18n(app, api) {
  application = app;
  const response = await api.fetchApi("/i18n");
  if (!response.ok) throw new Error("Could not load ComfyUI custom-node translations.");
  const translations = await response.json();
  for (const language of ["en", "zh"]) dictionaries[language] = translations[language]?.customAPI || {};
  if (!dictionaries.en.title) throw new Error("Model API locales are missing. Restart ComfyUI to load its locales directory.");
  refreshLanguage();
}

export function refreshLanguage() {
  const setting = application?.extensionManager?.setting;
  const read = id => setting?.get?.(id) ?? application?.ui?.settings?.getSettingValue?.(id);
  activeLanguage = resolveLanguage(read("Comfy.Locale"));
  return activeLanguage;
}

export function language() { return activeLanguage; }

export function parameterLabel(spec) {
  const label = spec.label && typeof spec.label === "object" ? spec.label.en || spec.name : spec.label || spec.name;
  const key = `parameter.${spec.name}`;
  return label === dictionaries.en?.[key] ? t(key) : label;
}

export function t(key, variables = {}) {
  const text = dictionaries[activeLanguage]?.[key] ?? dictionaries.en?.[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (all, name) => variables[name] ?? all);
}

export function errorText(error) {
  return error?.code ? `${t(`error.${error.code}`)}${error.detail ? `\n${error.detail}` : ""}` : error?.message || String(error);
}
