import { el } from "./dom.js";

export let iconCatalog = [];
const aliases = [
  ["qwen", /qwen|通义|千问/i], ["bailian", /bailian|dashscope|百炼/i],
  ["deepseek", /deepseek|深度求索/i], ["claude", /claude/i], ["anthropic", /anthropic/i],
  ["gemini", /gemini|generativelanguage/i], ["google", /google/i], ["grok", /grok|x\.ai|xai/i],
  ["doubao", /doubao|豆包/i], ["volcengine", /volcengine|volces|火山/i],
  ["siliconcloud", /siliconflow|siliconcloud|硅基/i], ["minimax", /minimax|mini-max/i],
  ["kimi", /kimi/i], ["moonshot", /moonshot|月之暗面/i], ["zhipu", /zhipu|bigmodel|智谱/i],
  ["chatglm", /chatglm|\bglm[-\d]/i], ["ollama", /ollama/i], ["lmstudio", /lm.?studio/i],
  ["openrouter", /openrouter/i], ["openai", /openai|chatgpt|\bgpt[-\d]|\bdall-e/i],
  ["flux", /\bflux/i], ["stability", /stability|stable.diffusion/i], ["kling", /kling|可灵/i],
  ["jimeng", /jimeng|即梦/i], ["hunyuan", /hunyuan|混元/i], ["stepfun", /stepfun|阶跃/i],
];

export async function initializeIcons() {
  const response = await fetch(new URL("./assets/lobehub/catalog.json", import.meta.url));
  if (!response.ok) throw new Error("LobeHub icon catalog could not be loaded.");
  iconCatalog = (await response.json()).icons;
}

export function inferIcon(value) {
  return aliases.find(([, pattern]) => pattern.test(value || ""))?.[0] || "";
}

export function iconId(provider = {}, model) {
  if (model) {
    const inferred = inferIcon(`${model.model_id} ${model.name}`);
    if (inferred) return inferred;
  }
  if (provider.icon?.startsWith("lobehub:")) return provider.icon.slice(8);
  if (provider.icon && !["◈", "auto"].includes(provider.icon)) return inferIcon(provider.icon);
  return inferIcon(`${provider.name || ""} ${provider.base_url || ""}`);
}

export function brandIcon(provider = {}, model, className = "") {
  const wrapper = el("span", { class: `capi-brand-icon ${className}`, "aria-hidden": "true" });
  const selected = iconCatalog.find(icon => icon.id === iconId(provider, model));
  if (selected) {
    const url = new URL(`./assets/lobehub/${selected.id}.svg`, import.meta.url).href;
    if (selected.mono) {
      const mark = el("span", { class: "capi-icon-mask" });
      mark.style.maskImage = `url("${url}")`;
      wrapper.append(mark);
    } else wrapper.append(el("img", { src: url, alt: "", draggable: false }));
  } else if (/^data:image\/(png|jpeg|webp);base64,/.test(provider.icon || "")) {
    wrapper.append(el("img", { src: provider.icon, alt: "", draggable: false }));
  } else wrapper.textContent = provider.icon && !["◈", "auto"].includes(provider.icon) && !provider.icon.startsWith("lobehub:") ? provider.icon.slice(0, 2) : (provider.name || "API").slice(0, 1).toUpperCase();
  return wrapper;
}
