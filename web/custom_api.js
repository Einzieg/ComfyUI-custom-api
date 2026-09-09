import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { makeClient } from "./client.js";
import { initializeI18n, language, refreshLanguage, t } from "./i18n.js";
import { initializeIcons } from "./icons.js";
import { el } from "./dom.js";
import { ManagerPanel } from "./panel.js";
import { NodeInterface } from "./node_ui.js";

const request = makeClient(api);
let config = { providers: [], models: [], templates: [] };
let ready = false;
const liveNodes = new Set();

function editNode(node, change) {
  node.graph?.beforeChange();
  try { change(); } finally { node.graph?.afterChange(); }
  node.graph?.setDirtyCanvas(true, true);
}

function updateConfiguration(value) {
  config = value;
  for (const node of liveNodes) updateNode(node);
}
const panel = new ManagerPanel(app, request, updateConfiguration);

function updateNode(node) {
  if (!ready) return;
  const kind = node.comfyClass;
  const title = t(kind === "CustomAPIText" ? "node.text" : kind === "CustomAPIImage" ? "node.image" : "node.parameter");
  const defaults = new Set(["API Text / Vision", "API Image", "API Parameter", "API 文本 / 识图", "API 图像", "API 参数", node._capiDefaultTitle]);
  if (defaults.has(node.title)) node.title = title;
  node._capiDefaultTitle = title;
  for (const w of node.widgets || []) if (!w.name.startsWith("capi_")) w.label = t(`node.${w.name}`);
  for (const input of node.inputs || []) input.localized_name = t(`node.${input.name === "image" ? "imageInput" : input.name}`);
  for (const output of node.outputs || []) output.localized_name = t(`node.${output.name === "text" ? "textOutput" : output.name === "images" ? "imagesOutput" : output.name}`);
  (node.properties ||= {}).custom_api_language = language();
  node._capiUI?.render();
  node.graph?.setDirtyCanvas(true, true);
}

function installNode(node) {
  if (!node.comfyClass?.startsWith("CustomAPI") || node._capiInstalled) return;
  node._capiInstalled = true; liveNodes.add(node);
  const removed = node.onRemoved;
  node.onRemoved = function () { liveNodes.delete(this); return removed?.apply(this, arguments); };
  if (node.comfyClass !== "CustomAPIParameter") {
    node._capiUI = new NodeInterface(node, () => config, context => panel.open(context), editNode);
    node.setSize([380, 340]);
  }
  updateNode(node);
}

function localeChanged() {
  if (!ready) return;
  refreshLanguage();
  for (const node of liveNodes) updateNode(node);
  if (panel.dialog?.open) {
    try { panel.flushEditors(); panel.render(); } catch (error) { panel.status(error.message || t("invalidJSON"), true); }
  }
}

app.registerExtension({
  name: "CustomAPI",
  settings: [{ id: "CustomAPI.Language", name: "Model API language", category: ["CustomAPI", "Language"],
    type: "combo", options: [{ text: "Follow ComfyUI", value: "auto" }, { text: "English", value: "en" }, { text: "简体中文", value: "zh" }], defaultValue: "auto", onChange: localeChanged }],
  commands: [{ id: "CustomAPI.Manage", label: () => ready ? t("title") : "Model API", icon: "pi pi-server", function: () => panel.open() }],
  menuCommands: [{ path: ["Extensions"], commands: ["CustomAPI.Manage"] }],
  actionBarButtons: [{ icon: "icon-[lucide--server]", label: "API", tooltip: "Model API", onClick: () => panel.open() }],
  async setup() {
    document.head.append(el("link", { rel: "stylesheet", href: new URL("./panel.css", import.meta.url).href }));
    await Promise.all([initializeI18n(app), initializeIcons()]);
    config = await request("/config"); ready = true;
    for (const node of liveNodes) updateNode(node);
    api.addEventListener("custom-api-progress", event => {
      for (const node of liveNodes) if (String(node.id) === String(event.detail.node_id)) node._capiUI?.progress(event.detail);
    });
    api.addEventListener("executing", event => {
      for (const node of liveNodes) if (String(node.id) === String(event.detail)) node._capiUI?.progress({ status: "running" });
    });
    api.addEventListener("executed", event => {
      for (const node of liveNodes) if (String(node.id) === String(event.detail.display_node || event.detail.node)) node._capiUI?.progress({ status: "completed" });
    });
    new MutationObserver(localeChanged).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
  },
  nodeCreated(node) { installNode(node); },
});
