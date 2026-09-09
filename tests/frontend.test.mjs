import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolveLanguage } from "../web/i18n.js";
import { modelOptions, parameterSchema, parseObject, selectableModels, selectionValues } from "../web/client.js";
import { iconId } from "../web/icons.js";

test("locale preference, host locale and fallback", () => {
  assert.equal(resolveLanguage("auto", "zh-CN"), "zh");
  assert.equal(resolveLanguage("en", "zh"), "en");
  assert.equal(resolveLanguage("auto", "fr"), "en");
  assert.equal(resolveLanguage("auto", null, "zh-TW"), "zh");
});

test("all Chinese translations match the English key set", () => {
  const en = JSON.parse(readFileSync(new URL("../web/locales/en.json", import.meta.url), "utf8"));
  const zh = JSON.parse(readFileSync(new URL("../web/locales/zh.json", import.meta.url), "utf8"));
  assert.deepEqual(Object.keys(zh).sort(), Object.keys(en).sort());
  for (const [key, value] of Object.entries(en)) {
    assert.ok(zh[key].trim(), key);
    assert.deepEqual([...value.matchAll(/(?<!\{)\{(\w+)\}(?!\})/g)].map(m => m[1]).sort(), [...zh[key].matchAll(/(?<!\{)\{(\w+)\}(?!\})/g)].map(m => m[1]).sort(), key);
  }
});

test("model pickers filter provider, state and operation using stable IDs", () => {
  const config = { providers: [{ id: "a" }, { id: "b", enabled: false }], models: [
    { id: "m1", provider_id: "a", bindings: { text: "t" } },
    { id: "m2", provider_id: "a", bindings: { image: "i" } },
    { id: "m3", provider_id: "b", bindings: { text: "t" } },
  ] };
  assert.deepEqual(modelOptions(config, "a", "text").map(m => m.id), ["m1"]);
  assert.deepEqual(modelOptions(config, "b", "text"), []);
});

test("model parameter overrides win over template defaults", () => {
  const config = { models: [{ id: "m", bindings: { text: "t" }, defaults: { temperature: 0.3 } }], templates: [{ id: "t", parameters: [{ name: "temperature", type: "number", default: 0.7 }] }] };
  assert.equal(parameterSchema(config, "m", "text")[0].default, 0.3);
  assert.equal(config.templates[0].parameters[0].default, 0.7);
  assert.throws(() => parseObject("[]"));
});

test("unified model selection filters disabled providers and incompatible templates", () => {
  const config = { providers: [{ id: "q", name: "Qwen" }, { id: "o", name: "OpenAI" }, { id: "off", enabled: false }],
    templates: [{ id: "chat", kind: "text" }, { id: "image", kind: "image" }], models: [
      { id: "vision", provider_id: "q", name: "Vision model", model_id: "qwen-vl", bindings: { vision: "chat" } },
      { id: "text", provider_id: "o", name: "Chat", model_id: "gpt", bindings: { text: "chat" } },
      { id: "picture", provider_id: "q", name: "Image", bindings: { image: "image" } },
      { id: "wrong", provider_id: "q", bindings: { text: "image" } },
      { id: "disabled", provider_id: "off", bindings: { text: "chat" } },
      { id: "unbound", provider_id: "q", bindings: {} },
    ] };
  assert.deepEqual(selectableModels(config, ["text", "vision"]).map(m => m.id), ["vision", "text"]);
  assert.deepEqual(selectableModels(config, ["text", "vision"], "", "qwen").map(m => m.id), ["vision"]);
  assert.deepEqual(selectionValues(config, "vision", ["text", "vision"], "text"), { provider_id: "q", model_id: "vision", operation: "vision" });
  assert.equal(selectionValues(config, "picture", ["text", "vision"], "text"), null);
  assert.equal(selectionValues(config, "wrong", ["text", "vision"], "text"), null);
});

test("LobeHub icons resolve explicit provider choices and recognized model families locally", () => {
  const catalog = JSON.parse(readFileSync(new URL("../web/assets/lobehub/catalog.json", import.meta.url), "utf8"));
  assert.equal(catalog.package, "@lobehub/icons-static-svg");
  assert.equal(new Set(catalog.icons.map(i => i.id)).size, catalog.icons.length);
  for (const icon of catalog.icons) {
    assert.match(icon.id, /^[a-z0-9]+$/);
    assert.match(readFileSync(new URL(`../web/assets/lobehub/${icon.id}.svg`, import.meta.url), "utf8"), /<svg/);
  }
  assert.equal(iconId({ name: "通义千问" }), "qwen");
  assert.equal(iconId({ name: "Custom", icon: "lobehub:deepseek" }), "deepseek");
  assert.equal(iconId({ name: "Qwen", icon: "data:image/png;base64,AAAA" }), "");
  assert.equal(iconId({ name: "OpenRouter" }, { model_id: "anthropic/claude-sonnet" }), "claude");
});
