import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { initializeI18n, parameterLabel, refreshLanguage, resolveLanguage, t } from "../web/i18n.js";
import { makeClient, parameterSchema, parseObject, selectableModels, selectionValues } from "../web/client.js";
import { iconId } from "../web/icons.js";
import { NodeInterface } from "../web/node_ui.js";

test("management client shares local bootstrap and never sends an unauthenticated mutation", async () => {
  const calls = [];
  const request = makeClient({ async fetchApi(url, options) {
    calls.push({ url, options });
    return { ok: true, async json() { return url.endsWith("/session") ? { token: "session-only" } : {}; } };
  } });
  await Promise.all([request("/config"), request("/network-policy")]);
  assert.equal(calls.filter(c => c.url.endsWith("/session")).length, 1);
  await request("/config", "PUT", { config: {} });
  assert.equal(calls.at(-1).options.headers["X-Custom-API-Session"], "session-only");
  assert.equal(calls.at(-1).options.headers["Content-Type"], "application/json");
  assert.equal(calls.at(-1).options.body, JSON.stringify({ config: {} }));
});

test("remote pairing is explicit and expired mutations are not automatically replayed", async () => {
  let unlocked = false;
  const calls = [];
  const request = makeClient({ async fetchApi(url, options) {
    calls.push({ url, options });
    if (url.endsWith("/session")) {
      unlocked = JSON.parse(options.body).pairing_code === "pair-code";
      return { ok: unlocked, status: unlocked ? 200 : 401, async json() {
        return unlocked ? { token: "session-only" } : { error: { code: "management_auth_required" } };
      } };
    }
    return { ok: false, status: 401, async json() { return { error: { code: "management_auth_required" } }; } };
  } });
  await assert.rejects(request("/config", "PUT", {}), { code: "management_auth_required" });
  assert.equal(calls.length, 1);
  await request.pair("pair-code");
  await assert.rejects(request("/test", "POST", {}), { code: "management_auth_required" });
  assert.equal(calls.filter(c => c.url.endsWith("/test")).length, 1);
  assert.equal(calls.at(-1).options.headers["X-Custom-API-Session"], "session-only");
  assert.ok(!calls.at(-1).options.body.includes("pair-code"));
});

test("only the ComfyUI locale selects translations, with English fallback", () => {
  assert.equal(resolveLanguage("zh-CN"), "zh");
  assert.equal(resolveLanguage("en"), "en");
  assert.equal(resolveLanguage("fr"), "en");
  assert.equal(resolveLanguage(undefined, "zh-TW"), "en");
});

test("all Chinese translations match the English key set", () => {
  const en = JSON.parse(readFileSync(new URL("../locales/en/main.json", import.meta.url), "utf8")).customAPI;
  const zh = JSON.parse(readFileSync(new URL("../locales/zh/main.json", import.meta.url), "utf8")).customAPI;
  assert.deepEqual(Object.keys(zh).sort(), Object.keys(en).sort());
  for (const [key, value] of Object.entries(en)) {
    assert.ok(zh[key].trim(), key);
    assert.deepEqual([...value.matchAll(/(?<!\{)\{(\w+)\}(?!\})/g)].map(m => m[1]).sort(), [...zh[key].matchAll(/(?<!\{)\{(\w+)\}(?!\})/g)].map(m => m[1]).sort(), key);
  }
});

test("custom UI translations use the official i18n endpoint and preserve custom parameter labels", async () => {
  let locale = "en";
  const urls = [];
  const translations = Object.fromEntries(["en", "zh"].map(code => [code,
    JSON.parse(readFileSync(new URL(`../locales/${code}/main.json`, import.meta.url), "utf8"))]));
  await initializeI18n({ extensionManager: { setting: { get(id) {
    assert.equal(id, "Comfy.Locale"); return locale;
  } } } }, { async fetchApi(url) { urls.push(url); return { ok: true, async json() { return translations; } }; } });
  assert.deepEqual(urls, ["/i18n"]);
  assert.equal(t("save"), "Save");
  locale = "zh"; refreshLanguage();
  assert.equal(t("save"), translations.zh.customAPI.save);
  assert.equal(parameterLabel({ name: "temperature", label: "Temperature" }), "温度");
  assert.equal(parameterLabel({ name: "temperature", label: { en: "Temperature", zh: "legacy" } }), "温度");
  assert.equal(parameterLabel({ name: "temperature", label: "Custom temperature label" }), "Custom temperature label");
  locale = "en"; refreshLanguage();
  assert.equal(parameterLabel({ name: "temperature", label: "Temperature" }), "Temperature");
});

test("model pickers filter provider, state and operation using stable IDs", () => {
  const config = { providers: [{ id: "a" }, { id: "b", enabled: false }], templates: [{ id: "t", kind: "text" }, { id: "i", kind: "image" }], models: [
    { id: "m1", provider_id: "a", bindings: { text: "t" } },
    { id: "m2", provider_id: "a", bindings: { image: "i" } },
    { id: "m3", provider_id: "b", bindings: { text: "t" } },
  ] };
  assert.deepEqual(selectableModels(config, ["text"], "a").map(m => m.id), ["m1"]);
  assert.deepEqual(selectableModels(config, ["text"], "b"), []);
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

function nodeInterfaceFixture(image = false) {
  const names = ["provider_id", "model_id", "operation", "prompt", "parameters", "cache_mode", "request_nonce", ...(image ? [] : ["system"])];
  const widgets = names.map(name => ({ name, value: `${name}-value`, hidden: true }));
  const node = {
    widgets, properties: {},
    inputs: [{ name: "image", type: "IMAGE", link: null }, ...(image ? [{ name: "mask", type: "MASK", link: null }] : []),
      ...names.map(name => ({ name, type: "STRING", link: null, widget: { name }, pos: [10, 10] }))],
    addInput(name, type) { this.inputs.push({ name, type, link: null }); },
    removeInput(index) { assert.equal(this.inputs[index].link, null, "never remove a connected input"); this.inputs.splice(index, 1); },
  };
  const ui = Object.assign(Object.create(NodeInterface.prototype), { node, widgets: Object.fromEntries(widgets.map(w => [w.name, w])) });
  return { node, ui };
}

test("hidden canonical controls leave no input sockets on text and image nodes", () => {
  for (const image of [false, true]) {
    const { node, ui } = nodeInterfaceFixture(image);
    const values = node.widgets.map(w => [w.name, w.value]);
    ui.syncInputs();
    assert.deepEqual(node.inputs.map(input => input.name), image ? ["image", "mask"] : ["image"]);
    assert.deepEqual(node.widgets.map(w => [w.name, w.value]), values, "preserve workflow widget order and values");
  }
});

test("restored workflows keep connected and explicitly exposed inputs", () => {
  const { node, ui } = nodeInterfaceFixture();
  node.properties.custom_api_inputs = ["system"];
  node.inputs.find(input => input.name === "parameters").link = 42;
  delete node.inputs.find(input => input.name === "provider_id").widget;
  ui.syncInputs();
  assert.deepEqual(node.inputs.map(input => input.name), ["image", "parameters", "system"]);
  const parameters = node.inputs.find(input => input.name === "parameters");
  assert.equal(parameters.link, 42);
  assert.equal(parameters.widget, undefined);
  assert.equal(ui.inputExposed("system"), true);
});

test("switching back to manual input removes its socket instead of hiding it", () => {
  const { node, ui } = nodeInterfaceFixture();
  ui.syncInputs();
  for (let round = 0; round < 3; round++) {
    node.properties.custom_api_inputs = ["prompt", "parameters", "system"];
    ui.syncInputs();
    ui.syncInputs();
    assert.deepEqual(node.inputs.map(input => input.name), ["image", "prompt", "parameters", "system"]);
    assert.ok(node.inputs.slice(1).every(input => input.type === "STRING" && !input.widget));
    node.properties.custom_api_inputs = [];
    ui.syncInputs();
    assert.deepEqual(node.inputs.map(input => input.name), ["image"]);
  }
});
