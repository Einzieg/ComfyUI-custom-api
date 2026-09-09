import { el, button, field, select } from "./dom.js";
import { language, t } from "./i18n.js";
import { parameterSchema, parseObject, selectableModels, selectionValues, supportedOperations } from "./client.js";
import { brandIcon } from "./icons.js";

const canonical = node => Object.fromEntries((node.widgets || []).filter(w => !w.name.startsWith("capi_")).map(w => [w.name, w]));

export class NodeInterface {
  constructor(node, getConfig, manage, edit) {
    this.node = node; this.getConfig = getConfig; this.manage = manage; this.edit = edit;
    this.allowed = node.comfyClass === "CustomAPIText" ? ["text", "vision"] : ["image", "image_edit"];
    this.widgets = canonical(node); this.height = 270; this.inputWidgets = new Map();
    this.root = el("div", { class: "capi-node" });
    // Preserve canonical widget order and values for existing workflows.
    for (const widget of Object.values(this.widgets)) {
      widget.hidden = true; widget.type = "hidden"; widget.computeSize = () => [0, -4];
      if (widget.element) widget.element.style.setProperty("display", "none", "important");
      if (widget.options) { widget.options.getMinHeight = () => 0; widget.options.getMaxHeight = () => 0; }
    }
    const dom = node.addDOMWidget("capi_interface", "custom-api-interface", this.root, {
      serialize: false, hideOnZoom: true, margin: 8,
      getMinHeight: () => this.height, getMaxHeight: () => this.height, getHeight: () => this.height,
    });
    dom.serializeValue = () => undefined;
    this.resizeObserver = new ResizeObserver(() => this.fit()); this.resizeObserver.observe(this.root);
    const configured = node.onConfigure;
    node.onConfigure = (...args) => { configured?.apply(node, args); queueMicrotask(() => this.render()); };
    const executed = node.onExecuted;
    node.onExecuted = message => { executed?.call(node, message); if (message.text) { this.result = message.text.join("\n"); this.showResult(); } };
    const connections = node.onConnectionsChange;
    node.onConnectionsChange = (...args) => { connections?.apply(node, args); queueMicrotask(() => this.render()); };
    for (const w of Object.values(this.widgets)) {
      const callback = w.callback;
      w.callback = (...args) => {
        callback?.apply(w, args);
        if (!this.committing) queueMicrotask(() => {
          if (this.valueSignature() !== this.renderedValues) this.render();
        });
      };
    }
    const removed = node.onRemoved;
    node.onRemoved = (...args) => { this.resizeObserver.disconnect(); this.closePicker(); cancelAnimationFrame(this.resizeFrame); removed?.apply(node, args); };
  }

  value(name) { return this.widgets[name]?.value; }
  valueSignature() { return JSON.stringify(Object.values(this.widgets).map(w => w.value)); }
  linked(name) { return this.node.inputs?.some(input => input.name === name && input.link != null); }
  inputExposed(name) { return this.node.inputs?.some(input => input.name === name && !input.widget); }
  syncInputs() {
    const exposed = this.node.properties?.custom_api_inputs || [];
    for (const name of Object.keys(this.widgets)) {
      let slot = this.node.inputs?.find(input => input.name === name);
      if (!exposed.includes(name) && slot?.link == null) continue;
      if (!slot) { this.node.addInput(name, "STRING"); slot = this.node.inputs.find(input => input.name === name); }
      if (slot.widget) { this.inputWidgets.set(name, slot.widget); delete slot.widget; }
      slot._widget = undefined; slot.pos = undefined;
      slot.localized_name = t(`node.${name}`);
    }
  }
  inputToggle(name) {
    const toggle = button(t(this.inputExposed(name) ? "manualInput" : "connectionInput"), () => {
      this.edit(this.node, () => {
        let slot = this.node.inputs.find(input => input.name === name);
        const exposed = new Set(this.node.properties?.custom_api_inputs || []);
        if (slot && !slot.widget) { slot.widget = this.inputWidgets.get(name) || { name }; slot._widget = this.widgets[name]; exposed.delete(name); }
        else {
          if (!slot) { this.node.addInput(name, "STRING"); slot = this.node.inputs.find(input => input.name === name); }
          if (slot.widget) this.inputWidgets.set(name, slot.widget);
          delete slot.widget; slot._widget = undefined; exposed.add(name);
        }
        slot.pos = undefined; slot.localized_name = t(`node.${name}`);
        (this.node.properties ||= {}).custom_api_inputs = [...exposed];
      });
      this.render();
    }, "capi-input-toggle");
    toggle.setAttribute("aria-label", t(this.inputExposed(name) ? "manualNamedInput" : "connectNamedInput", { name: t(`node.${name}`) }));
    toggle.disabled = this.linked(name); return toggle;
  }
  commit(values) {
    this.committing = true;
    try { this.edit(this.node, () => { for (const [name, value] of Object.entries(values)) if (this.widgets[name]) this.widgets[name].value = value; }); }
    finally { this.renderedValues = this.valueSignature(); this.committing = false; }
  }
  fit() {
    cancelAnimationFrame(this.resizeFrame);
    this.resizeFrame = requestAnimationFrame(() => {
      if (!this.root.isConnected) return;
      const height = Math.ceil(this.root.scrollHeight) + 16;
      this.height = height;
      const size = [Math.max(340, this.node.size[0]), this.node.computeSize()[1]];
      if (Math.abs(size[1] - this.node.size[1]) < 2 && size[0] === this.node.size[0]) return;
      this.node.setSize(size);
      this.node.graph?.setDirtyCanvas(true, true);
    });
  }
  choose(modelId) {
    const values = selectionValues(this.getConfig(), modelId, this.allowed, this.value("operation"));
    if (!values) return;
    if (modelId !== this.value("model_id") && !this.linked("parameters")) values.parameters = "{}";
    this.commit(values); this.closePicker(); this.render();
  }
  openManager() { this.closePicker(); this.manage({ providerId: this.value("provider_id"), operations: this.allowed, onSelect: id => this.choose(id) }); }
  closePicker() { this.picker?.remove(); this.picker = null; this.modelButton?.setAttribute("aria-expanded", "false"); }
  openPicker() {
    if (this.picker) { this.closePicker(); return; }
    const config = this.getConfig();
    const menu = el("div", { class: "capi-floating capi-model-menu", popover: "auto", "aria-label": t("selectModel") });
    const search = el("input", { type: "search", placeholder: t("searchAllModels"), "aria-label": t("searchAllModels") });
    const providers = select("", [{ value: "", label: t("allProviders") }, ...config.providers.filter(p => p.enabled !== false).map(p => ({ value: p.id, label: p.name }))], () => populate(), { "aria-label": t("filterProvider") });
    const list = el("div", { class: "capi-model-options", role: "listbox", "aria-label": t("availableModels") });
    const populate = () => {
      const models = selectableModels(config, this.allowed, providers.value, search.value);
      list.replaceChildren(...models.map(model => {
        const provider = config.providers.find(p => p.id === model.provider_id);
        const row = button("", () => this.choose(model.id), "capi-model-option");
        row.setAttribute("role", "option"); row.setAttribute("aria-selected", String(model.id === this.value("model_id")));
        row.append(brandIcon(provider, model), el("span", { class: "capi-model-copy" }, el("strong", { text: model.name }), el("small", { text: `${provider.name} · ${model.model_id}` })), el("span", { class: "capi-model-check", text: model.id === this.value("model_id") ? "✓" : "" }));
        return row;
      }));
      if (!models.length) list.append(el("p", { class: "capi-picker-empty", text: t(config.models.length ? "noCompatibleModels" : "noModels") }));
    };
    search.addEventListener("input", populate);
    menu.addEventListener("keydown", event => {
      const items = [search, providers, ...list.querySelectorAll("button")];
      if (["ArrowDown", "ArrowUp"].includes(event.key)) {
        event.preventDefault(); const index = items.indexOf(document.activeElement);
        items[(index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
      } else if (event.key === "Enter" && document.activeElement === search) { event.preventDefault(); list.querySelector("button")?.click(); }
    });
    menu.append(el("div", { class: "capi-picker-search" }, search, providers), list, button(t("manageProviders"), () => this.openManager(), "capi-picker-manage"));
    this.picker = menu; document.body.append(menu); populate();
    const rect = this.modelButton.getBoundingClientRect(); const width = Math.min(430, window.innerWidth - 24);
    menu.style.width = `${width}px`; menu.style.left = `${Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))}px`;
    menu.style.top = `${Math.max(12, Math.min(rect.bottom + 6, window.innerHeight - 450))}px`;
    menu.showPopover(); this.modelButton.setAttribute("aria-expanded", "true"); search.focus();
    menu.addEventListener("toggle", event => { if (event.newState === "closed") this.closePicker(); });
  }
  textInput(name, label, placeholder, rows) {
    const linked = this.linked(name);
    const input = el("textarea", { value: linked ? "" : this.value(name) || "", rows, placeholder: linked ? t("connectedInput") : placeholder,
      disabled: linked, "aria-label": label, spellcheck: false, oninput: event => this.commit({ [name]: event.target.value }) });
    return el("div", { class: "capi-field" }, el("div", { class: "capi-field-heading" },
      el("span", { text: label + (linked ? ` · ${t("connectedInput")}` : "") }), this.inputToggle(name)), input);
  }
  renderParameters(container) {
    if (this.linked("parameters")) return;
    const schema = parameterSchema(this.getConfig(), this.value("model_id"), this.value("operation"));
    let values;
    try { values = parseObject(this.value("parameters")); } catch { container.append(el("small", { class: "capi-inline-error", text: t("invalidJSON") })); return; }
    const disabled = this.linked("parameters");
    for (const spec of schema) {
      const label = typeof spec.label === "object" ? spec.label[language()] || spec.label.en || spec.name : spec.label || spec.name;
      const initial = values[spec.name] ?? spec.default ?? "";
      const update = value => {
        try { const current = parseObject(this.value("parameters")); current[spec.name] = value; this.commit({ parameters: JSON.stringify(current, null, 2) }); if (this.rawParameters) this.rawParameters.value = this.value("parameters"); }
        catch { /* Keep invalid JSON in the source editor. */ }
      };
      let input;
      if (spec.type === "enum") input = select(String(initial), (spec.options || []).map(value => ({ value: String(value), label: String(value) })), value => update(spec.options.find(option => String(option) === value)), { disabled });
      else if (spec.type === "boolean") input = el("input", { type: "checkbox", checked: Boolean(initial), disabled, onchange: event => update(event.target.checked) });
      else if (["integer", "number"].includes(spec.type)) input = el("input", { type: "number", value: initial, min: spec.min, max: spec.max, step: spec.type === "integer" ? 1 : "any", disabled,
        onchange: event => { if (event.target.value !== "" && event.target.reportValidity()) update(Number(event.target.value)); } });
      else input = el(spec.type === "json" ? "textarea" : "input", { value: spec.type === "json" && typeof initial !== "string" ? JSON.stringify(initial) : initial, rows: 2, disabled,
        onchange: event => {
          try { const value = spec.type === "json" ? JSON.parse(event.target.value) : event.target.value; event.target.setCustomValidity(""); update(value); }
          catch { event.target.setCustomValidity(t("invalidJSON")); event.target.reportValidity(); }
        } });
      container.append(field(label, input));
    }
  }
  render() {
    this.syncInputs();
    const config = this.getConfig(); const model = config.models.find(m => m.id === this.value("model_id"));
    const provider = config.providers.find(p => p.id === this.value("provider_id")) || config.providers.find(p => p.id === model?.provider_id);
    const usable = selectableModels(config, this.allowed).some(m => m.id === model?.id && (!this.value("provider_id") || m.provider_id === this.value("provider_id"))) && supportedOperations(config, model, this.allowed).includes(this.value("operation"));
    this.closePicker(); this.root.replaceChildren();
    this.modelButton = button("", () => this.openPicker(), "capi-model-trigger");
    this.modelButton.setAttribute("aria-label", t("selectModel")); this.modelButton.setAttribute("aria-haspopup", "listbox"); this.modelButton.setAttribute("aria-expanded", "false");
    this.modelButton.append(brandIcon(provider, model), el("span", { class: "capi-model-copy" }, el("strong", { text: usable ? model.name : t("selectModel") }), el("small", { text: usable ? provider.name : t("chooseModelHint") })), el("span", { class: "capi-chevron", text: "⌄" }));
    const manage = button("…", () => this.openManager(), "capi-node-manage"); manage.title = t("manageProviders"); manage.setAttribute("aria-label", t("manageProviders"));
    this.root.append(el("div", { class: "capi-model-header" }, this.modelButton, manage));
    if (this.value("model_id") && !usable) this.root.append(el("small", { class: "capi-inline-error", text: t("selectionUnavailable") }));
    const ops = supportedOperations(config, model, this.allowed); const operation = this.value("operation");
    const modes = el("div", { class: "capi-node-modes", role: "group", "aria-label": t("operation") });
    for (const op of ops.length ? ops : this.allowed) {
      const mode = button(t(`operation.${op}`), () => { this.commit({ operation: op }); this.render(); }, op === operation ? "active" : "");
      mode.disabled = !ops.includes(op); mode.setAttribute("aria-pressed", String(op === operation)); modes.append(mode);
    }
    this.root.append(modes, this.textInput("prompt", t("prompt"), t("promptPlaceholder"), 4));
    if (["vision", "image_edit"].includes(operation) && !this.linked("image")) this.root.append(el("small", { class: "capi-input-hint", text: t("connectImageHint") }));
    const settings = el("details", { class: "capi-node-settings", open: Boolean(this.node.properties?.custom_api_advanced) }, el("summary", { text: t("advancedSettings") }));
    settings.addEventListener("toggle", () => { if (settings.isConnected) { (this.node.properties ||= {}).custom_api_advanced = settings.open; this.fit(); } });
    settings.append(el("div", { class: "capi-field-heading" }, el("span", { text: t(this.linked("parameters") ? "connectedParameters" : "modelParameters") }), this.inputToggle("parameters")));
    const parameters = el("div", { class: "capi-node-parameters" }); this.renderParameters(parameters); settings.append(parameters);
    if (this.widgets.system) settings.append(this.textInput("system", t("system"), t("systemPlaceholder"), 3));
    const raw = el("details", { class: "capi-node-json" }, el("summary", { text: t("parameters") }));
    this.rawParameters = el("textarea", { value: this.value("parameters"), rows: 4, disabled: this.linked("parameters"), "aria-label": t("parameters"), spellcheck: false, oninput: event => {
      this.commit({ parameters: event.target.value });
      try { parseObject(event.target.value); event.target.setCustomValidity(""); } catch { event.target.setCustomValidity(t("invalidJSON")); }
    }, onchange: () => { parameters.replaceChildren(); this.renderParameters(parameters); this.fit(); } });
    raw.append(this.rawParameters); raw.addEventListener("toggle", () => this.fit());
    if (!this.linked("parameters")) settings.append(raw);
    settings.append(field(t("node.cache_mode"), select(this.value("cache_mode"), ["reuse", "refresh"].map(value => ({ value, label: t(`cache.${value}`) })), value => { this.commit({ cache_mode: value }); this.render(); })),
      field(t("node.request_nonce"), el("input", { type: "number", value: this.value("request_nonce"), min: 0, max: 2147483647, step: 1, onchange: event => { if (event.target.value !== "" && event.target.reportValidity()) this.commit({ request_nonce: Number(event.target.value) }); } })), el("small", { text: t("nonceHint") }));
    this.root.append(settings);
    const next = button(t("newRequest"), () => { this.commit({ request_nonce: this.value("request_nonce") >= 2147483647 ? 0 : Number(this.value("request_nonce") || 0) + 1 }); this.statusText = t("requestPrepared"); this.render(); }, "capi-next-request"); next.title = t("newRequestHint");
    this.statusNode = el("small", { class: "capi-node-progress", role: "status", text: this.statusText || t(this.value("cache_mode") === "refresh" ? "alwaysRequestHint" : "reuseHint") });
    this.root.append(el("div", { class: "capi-node-footer" }, this.statusNode, next));
    this.resultContainer = el("div", { class: "capi-node-result" }); this.root.append(this.resultContainer); this.showResult(); this.renderedValues = this.valueSignature(); this.fit();
  }
  showResult() {
    if (!this.resultContainer) return;
    this.resultContainer.replaceChildren();
    if (!this.result) { this.fit(); return; }
    const details = el("details", { open: true }, el("summary", { text: t("node.textOutput") }));
    const copy = button(t("copyResult"), async () => {
      try { await navigator.clipboard.writeText(this.result); copy.textContent = t("copied"); }
      catch { output.focus(); output.select(); }
    });
    const rows = Math.min(8, Math.max(2, this.result.split("\n").reduce((sum, line) => sum + Math.max(1, Math.ceil(line.length / 44)), 0)));
    const output = el("textarea", { class: "capi-node-output", readOnly: true, rows, value: this.result, "aria-label": t("node.textOutput") });
    details.append(output, copy); details.addEventListener("toggle", () => this.fit()); this.resultContainer.append(details); this.fit();
  }
  progress(data) {
    this.statusText = t(`progress.${data.status}`);
    if (this.statusText.startsWith("progress.")) this.statusText = data.status;
    if (data.progress != null) this.statusText += ` · ${data.progress}`;
    if (this.statusNode) this.statusNode.textContent = this.statusText;
  }
}
