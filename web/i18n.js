export const dictionaries = {};
let activeLanguage = "en";
let application;

export function resolveLanguage(preference, hostLanguage, browserLanguage = "en") {
  const value = preference && preference !== "auto" ? preference : hostLanguage || browserLanguage;
  return /^zh(?:-|$)/i.test(value) ? "zh" : "en";
}

export async function initializeI18n(app) {
  application = app;
  await Promise.all(["en", "zh"].map(async language => {
    const response = await fetch(new URL(`./locales/${language}.json`, import.meta.url));
    if (!response.ok) throw new Error(`Translation load failed: ${language}`);
    dictionaries[language] = await response.json();
  }));
  refreshLanguage();
}

export function refreshLanguage() {
  const setting = application?.extensionManager?.setting;
  const read = id => setting?.get?.(id) ?? application?.ui?.settings?.getSettingValue?.(id);
  activeLanguage = resolveLanguage(read("CustomAPI.Language"), read("Comfy.Locale"), globalThis.navigator?.language);
  return activeLanguage;
}

export function language() { return activeLanguage; }

export function t(key, variables = {}) {
  const text = dictionaries[activeLanguage]?.[key] ?? dictionaries.en?.[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (all, name) => variables[name] ?? all);
}

export function errorText(error) {
  return error?.code ? `${t(`error.${error.code}`)}${error.detail ? `\n${error.detail}` : ""}` : error?.message || String(error);
}
