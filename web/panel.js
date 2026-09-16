import { el, button, field, select, readFile } from "./dom.js";
import { t, errorText, refreshLanguage } from "./i18n.js";
import { downloadJSON, parameterSchema, parseObject, supportedOperations } from "./client.js";
import { brandIcon, iconCatalog, iconId } from "./icons.js";

const uid = () => crypto.randomUUID().replaceAll("-", "");
const pretty = value => JSON.stringify(value, null, 2);
const operations = ["text", "vision", "image", "image_edit"];

export class ManagerPanel {
  constructor(app, request, onConfig) {
    this.app = app;
    this.request = request;
    this.onConfig = onConfig;
    this.tab = "models";
    this.secretUpdates = {};
    this.pendingEditors = new Map();
    this.selectedModels = new Set();
    this.modelQuery = "";
    this.bulkOperation = "text";
    this.testState = { prompt: "", system: "", parameters: "{}", images: [], operation: "text", model_id: "" };
  }

  async open(context = {}) {
    if (this.dialog?.open) { this.dialog.focus(); return; }
    try {
      if (!this.dirty) {
        this.config = await this.request("/config");
        this.onConfig(this.config);
      }
      this.policy = await this.request("/network-policy");
      this.context = context;
      this.providerId = context.providerId || this.providerId || this.config.providers[0]?.id;
      if (context.onSelect) { this.tab = "models"; this.editModelId = null; this.bulkOperation = context.operations[0]; }
      refreshLanguage();
      this.render();
      this.dialog.showModal();
    } catch (error) {
      if (error.code === "management_auth_required") { this.pairingDialog(context); return; }
      this.app.extensionManager?.toast?.add?.({ severity: "error", summary: t("title"), detail: errorText(error), life: 8000 });
    }
  }

  pairingDialog(context) {
    const dialog = el("dialog", { class: "capi capi-pairing", "aria-label": t("pairManagement") });
    const code = el("input", { type: "password", autocomplete: "off", "aria-label": t("pairingCode") });
    const status = el("p", { role: "status" });
    dialog.append(el("h2", { text: t("pairManagement") }), el("p", { text: t("pairingHint") }), field(t("pairingCode"), code), status,
      button(t("pairManagement"), async () => {
        try { await this.request.pair(code.value.trim()); dialog.close(); await this.open(context); }
        catch (error) { status.textContent = errorText(error); }
      }, "primary"), button(t("close"), () => dialog.close()));
    dialog.addEventListener("close", () => dialog.remove());
    document.body.append(dialog); dialog.showModal(); code.focus();
  }

  status(message, error = false) {
    this.statusMessage = message;
    if (this.statusNode) {
      this.statusNode.textContent = message;
      this.statusNode.classList.toggle("error", error);
    }
  }

  markDirty() {
    this.dirty = true;
    if (this.saveButton) this.saveButton.textContent = t("saveChanges");
    this.status(t("unsaved"));
  }

  flushEditors() {
    for (const save of this.pendingEditors.values()) save();
    this.pendingEditors.clear();
  }

  async action(fn) {
    if (this.busy) return;
    this.busy = true;
    try { await fn(); }
    catch (error) { this.status(errorText(error), true); }
    finally { this.busy = false; }
  }

  async save() {
    this.flushEditors();
    this.config = await this.request("/config", "PUT", { config: this.config, secrets: this.secretUpdates });
    this.secretUpdates = {};
    this.dirty = false;
    this.onConfig(this.config);
    this.renderContent();
    this.renderSidebar();
    this.saveButton.textContent = t("save");
    this.status(t("saved"));
  }

  navigate(fn) {
    try { this.flushEditors(); fn(); this.renderSidebar(); this.renderContent(); }
    catch (error) { this.status(errorText(error), true); }
  }

  render() {
    const wasOpen = this.dialog?.open;
    this.dialog?.remove();
    this.dialog = el("dialog", { class: "capi", "aria-label": t("title") });
    this.dialog.addEventListener("cancel", event => {
      if (this.testRunning) { event.preventDefault(); this.status(t("testStillRunning")); }
    });
    this.saveButton = button(t(this.dirty ? "saveChanges" : "save"), () => this.action(() => this.save()), "primary");
    const importInput = el("input", { type: "file", accept: ".json,application/json", hidden: true, onchange: event => {
      const file = event.target.files[0];
      if (!file) return;
      this.action(async () => {
        this.flushEditors();
        if (this.dirty) await this.save();
        const config = JSON.parse(await file.text());
        this.config = await this.request("/import", "POST", { config });
        this.providerId = this.config.providers.at(-1)?.id;
        this.onConfig(this.config);
        this.renderSidebar(); this.renderContent();
        this.status(t("imported"));
      });
      event.target.value = "";
    }});
    const top = el("header", { class: "capi-top" },
      el("div", { class: "capi-brand" }, el("span", { class: "capi-brand-mark", text: "API" }), el("span", { text: t("title") })),
      button(t("import"), () => importInput.click()),
      button(t("export"), () => this.action(async () => {
        this.flushEditors();
        if (this.dirty) await this.save();
        downloadJSON(await this.request("/export"), "model-api-config.json"); this.status(t("exported"));
      })), this.saveButton,
      button("×", () => { if (this.testRunning) this.status(t("testStillRunning")); else this.dialog.close(); }, "capi-close"), importInput);
    top.querySelector(".capi-close").setAttribute("aria-label", t("close"));
    this.sidebar = el("aside", { class: "capi-sidebar" });
    this.tabs = el("nav", { class: "capi-tabs", "aria-label": t("navigation") });
    this.content = el("div", { class: "capi-content" });
    this.statusNode = el("div", { class: "capi-status", role: "status", "aria-live": "polite", text: this.dirty ? t("unsaved") : this.statusMessage || t("localCredentials") });
    this.dialog.append(top, el("div", { class: "capi-layout" }, this.sidebar,
      el("main", { class: "capi-main" }, this.tabs, this.content, this.statusNode)));
    document.body.append(this.dialog);
    this.renderSidebar(); this.renderContent();
    if (wasOpen) this.dialog.showModal();
  }

  renderSidebar() {
    this.sidebar.replaceChildren(el("div", { class: "capi-sidebar-label", text: t("providers") }));
    const list = el("div", { class: "capi-provider-list" });
    for (const provider of this.config.providers) {
      const icon = brandIcon(provider);
      const count = this.config.models.filter(m => m.provider_id === provider.id).length;
      const row = button("", () => this.navigate(() => { this.providerId = provider.id; this.editModelId = null; this.modelQuery = ""; this.selectedModels.clear(); this.tab = "models"; }), `capi-provider ${provider.id === this.providerId ? "active" : ""}`);
      row.append(icon, el("span", { class: "capi-provider-copy" }, el("span", { class: "capi-provider-name", text: provider.name }),
        el("small", { text: provider.enabled === false ? t("disabled") : t("modelCount", { count }) })));
      list.append(row);
    }
    this.sidebar.append(list, button(t("addProvider"), () => this.navigate(() => this.addProvider())));
  }

  renderContent() {
    this.tabs.replaceChildren(...["models", "provider", "templates", "test", "history", "network"].map(tab =>
      button(t(`tab.${tab}`), () => this.navigate(() => { this.tab = tab; }), tab === this.tab ? "active" : "")));
    this.content.replaceChildren();
    const provider = this.config.providers.find(p => p.id === this.providerId);
    if (["models", "provider"].includes(this.tab) && !provider) {
      this.content.append(el("div", { class: "capi-empty" }, el("span", { class: "capi-brand-mark", text: "API" }),
        el("h2", { text: t("welcome") }), el("p", { text: t("welcomeHint") }), button(t("addProvider"), () => this.navigate(() => this.addProvider()), "primary")));
      return;
    }
    if (this.tab === "provider") this.providerForm(provider);
    else if (this.tab === "models") this.modelList(provider);
    else if (this.tab === "templates") this.templateEditor();
    else if (this.tab === "test") this.testForm();
    else if (this.tab === "network") this.networkForm();
    else this.showHistory();
  }

  networkForm() {
    const draft = structuredClone(this.policy);
    const mode = select(draft.mode, ["default", "strict"].map(value => ({ value, label: t(`networkMode.${value}`) })), value => {
      draft.mode = value; lists[0].hidden = value !== "default"; lists[1].hidden = value !== "strict";
    }, { "aria-label": t("networkMode") });
    const lists = ["local_origins", "allowed_origins", "allowed_key_env"].map(key => {
      const input = el("textarea", { rows: 3, value: draft[key].join("\n"), spellcheck: false, "aria-label": t(`network.${key}`),
        oninput: event => { draft[key] = event.target.value.split(/\r?\n/).map(s => s.trim()).filter(Boolean); } });
      const wrapper = el("div", {}, field(t(`network.${key}`), input, t(`network.${key}Hint`)));
      wrapper.hidden = key === "local_origins" ? draft.mode !== "default" : key === "allowed_origins" && draft.mode !== "strict";
      return wrapper;
    });
    this.content.append(el("h2", { text: t("network") }), el("p", { text: t("networkModesHint") }), field(t("networkMode"), mode), ...lists,
      button(t("saveNetwork"), () => this.action(async () => {
        this.policy = await this.request("/network-policy", "PUT", draft);
        this.status(t("networkSaved")); this.renderContent();
      }), "primary"));
  }

  input(object, key, label, options = {}) {
    const node = el("input", { value: object[key] ?? "", type: "text", ...options,
      oninput: event => { object[key] = options.type === "number" ? Number(event.target.value) : event.target.value; this.markDirty(); } });
    return field(label, node);
  }

  jsonInput(value, label, apply, hint, rows = 7) {
    const textarea = el("textarea", { class: "code", value: pretty(value), rows, spellcheck: false });
    const save = () => {
      try { apply(JSON.parse(textarea.value)); textarea.setCustomValidity(""); }
      catch (error) { textarea.setCustomValidity(t("invalidJSON")); throw { code: "invalid_config", detail: `${label}: ${t("invalidJSON")}` }; }
    };
    textarea.addEventListener("input", () => { this.pendingEditors.set(textarea, save); this.markDirty(); });
    return field(label, textarea, hint);
  }

  toggle(object, key, label) {
    return el("label", { class: "capi-row" }, el("input", { type: "checkbox", checked: object[key] !== false,
      onchange: event => { object[key] = event.target.checked; this.markDirty(); } }), el("span", { text: label }));
  }

  addProvider() {
    const provider = { id: uid(), name: t("newProvider"), icon: "", base_url: "", enabled: true,
      auth: { type: "bearer" }, timeout: 120, concurrency: 2, api_key_env: "",
      models_request: { method: "GET", path: "/models", encoding: "json", headers: {}, query: {}, body: {}, files: [] },
      models_path: "$.data", model_id_path: "$.id", model_name_path: "$.id" };
    this.config.providers.push(provider); this.providerId = provider.id; this.tab = "provider"; this.markDirty();
  }

  providerForm(provider) {
    this.content.append(el("div", { class: "capi-row" }, el("h2", { text: provider.name }), button(t("deleteProvider"), () => {
      if (!confirm(t("deleteProviderConfirm"))) return;
      this.navigate(() => {
        this.config.providers = this.config.providers.filter(p => p.id !== provider.id);
        this.config.models = this.config.models.filter(m => m.provider_id !== provider.id);
        delete this.secretUpdates[provider.id];
        this.providerId = this.config.providers[0]?.id; this.markDirty();
      });
    }, "danger")), el("p", { text: t("providerHint") }));
    const grid = el("div", { class: "capi-grid" });
    grid.append(this.input(provider, "name", t("providerName")), this.input(provider, "base_url", "Base URL", { placeholder: "https://api.example.com/v1" }));
    grid.append(el("small", { class: "capi-full", text: t("networkPolicyHint") }));
    grid.append(button(t("authorizeLocal"), () => this.action(async () => {
      const origin = new URL(provider.base_url).origin;
      if (!confirm(t("authorizeLocalConfirm", { origin }))) return;
      this.policy = await this.request("/network-policy/local", "POST", { origin });
      this.status(t("networkSaved"));
    })));
    const iconUpload = el("input", { type: "file", accept: "image/png,image/jpeg,image/webp", onchange: event => this.action(async () => {
      const file = event.target.files[0];
      if (!file) return;
      if (file.size > 512 * 1024) throw { code: "media_too_large", detail: t("iconHint") };
      provider.icon = await readFile(file); this.markDirty(); this.renderSidebar(); this.renderContent();
    }) });
    const icons = el("details", { class: "capi-icon-library" }, el("summary", {}, brandIcon(provider), el("span", { text: t("chooseIcon") }), el("small", { text: "LobeHub" })));
    const iconGrid = el("div", { class: "capi-icon-grid" });
    const populateIcons = (query = "") => {
      iconGrid.replaceChildren(...iconCatalog.filter(icon => `${icon.id} ${icon.name}`.toLowerCase().includes(query.toLowerCase())).map(icon => {
        const choice = button("", () => { this.flushEditors(); provider.icon = `lobehub:${icon.id}`; this.markDirty(); this.renderSidebar(); this.renderContent(); }, icon.id === iconId(provider) ? "selected" : "");
        choice.title = icon.name; choice.setAttribute("aria-label", icon.name);
        choice.append(brandIcon({ icon: `lobehub:${icon.id}` }), el("span", { text: icon.name })); return choice;
      }));
      if (!iconGrid.childElementCount) iconGrid.append(el("small", { text: t("noIcons") }));
    };
    icons.append(el("input", { type: "search", placeholder: t("searchIcons"), "aria-label": t("searchIcons"), oninput: event => populateIcons(event.target.value) }),
      iconGrid, button(t("autoIcon"), () => { provider.icon = ""; this.markDirty(); this.renderSidebar(); this.renderContent(); }));
    icons.addEventListener("toggle", () => { if (icons.open && !iconGrid.childElementCount) populateIcons(); });
    const customIcon = el("details", { class: "capi-custom-icon" }, el("summary", { text: t("customIcon") }), field(t("icon"), iconUpload, t("iconHint")));
    const iconField = el("div", { class: "capi-full" }, icons, el("small", { text: t("iconLibraryHint") }), customIcon);
    grid.append(iconField);
    provider.auth ||= { type: "bearer" };
    grid.append(field(t("authentication"), select(provider.auth.type, ["bearer", "header", "query", "none"].map(value => ({ value, label: t(`auth.${value}`) })), value => {
      this.flushEditors(); provider.auth.type = value; this.markDirty(); this.renderContent();
    })));
    const keyInput = el("input", { type: "password", value: this.secretUpdates[provider.id] ?? "", autocomplete: "new-password",
      placeholder: provider.has_key ? t("keyStored") : t("enterKey"), oninput: event => { this.secretUpdates[provider.id] = event.target.value; this.markDirty(); } });
    if (provider.auth.type !== "none") grid.append(field("API Key", keyInput, t("keyHint")));
    if (provider.auth.type === "header") grid.append(this.input(provider.auth, "header", t("headerName"), { placeholder: "x-api-key" }), this.input(provider.auth, "prefix", t("headerPrefix"), { placeholder: "Bearer " }));
    if (provider.auth.type === "query") grid.append(this.input(provider.auth, "query", t("queryName"), { placeholder: "key" }));
    this.content.append(grid, el("div", { class: "capi-section" }, this.toggle(provider, "enabled", t("enabled"))));
    const advanced = el("details", { class: "capi-section" }, el("summary", { text: t("advancedNetwork") }));
    advanced.append(el("div", { class: "capi-grid" },
      this.input(provider, "timeout", t("timeout"), { type: "number", min: 1, max: 3600 }),
      this.input(provider, "concurrency", t("concurrency"), { type: "number", min: 1, max: 32 }),
      this.input(provider, "api_key_env", t("keyEnvironment"), { placeholder: "MY_PROVIDER_API_KEY" })));
    const listing = el("details", { class: "capi-section" }, el("summary", { text: t("modelDiscovery") }),
      this.jsonInput(provider.models_request || { method: "GET", path: "/models" }, t("discoveryRequest"), value => { provider.models_request = value; }, t("templateSecrets")),
      el("div", { class: "capi-grid" }, this.input(provider, "models_path", t("modelsPath")), this.input(provider, "model_id_path", t("modelIdPath")), this.input(provider, "model_name_path", t("modelNamePath"))));
    this.content.append(advanced, listing, el("div", { class: "capi-form-actions" }, button(t("saveAndFetch"), () => this.action(() => this.fetchModels(provider.id)), "primary"),
      button(t("saveAndModels"), () => this.action(async () => { await this.save(); this.tab = "models"; this.renderContent(); }))));
  }

  async fetchModels(providerId) {
    await this.save(); this.status(t("fetchingModels"));
    const result = await this.request(`/providers/${providerId}/models`, "POST", {});
    this.config = result.config; this.onConfig(this.config); this.tab = "models"; this.editModelId = null;
    this.renderSidebar(); this.renderContent(); this.status(t("modelsFetched", { count: result.added }));
  }

  modelList(provider) {
    const editing = this.config.models.find(m => m.id === this.editModelId && m.provider_id === provider.id);
    if (editing) {
      this.content.append(button(t("backToModels"), () => this.navigate(() => { this.editModelId = null; }), "capi-back"));
      this.modelForm(editing); return;
    }
    this.content.append(el("div", { class: "capi-row" }, el("h2", { text: provider.name }),
      button(t("fetchModels"), () => this.action(() => this.fetchModels(provider.id))), button(t("addModel"), () => this.navigate(() => {
        const model = { id: uid(), provider_id: provider.id, model_id: "", name: t("newModel"), enabled: true, source: "manual", group: "", bindings: {}, defaults: {} };
        this.config.models.push(model); this.editModelId = model.id; this.markDirty();
      }), "primary")), el("p", { text: t("modelsHint") }));
    const models = this.config.models.filter(m => m.provider_id === provider.id);
    const table = el("table", { class: "capi-table" });
    const tbody = el("tbody");
    const visibleModels = () => models.filter(m => `${m.name} ${m.model_id} ${m.group || ""}`.toLowerCase().includes(this.modelQuery.toLowerCase()));
    const selectAll = el("input", { type: "checkbox", "aria-label": t("selectVisibleModels"), onchange: event => {
      for (const model of visibleModels()) { if (event.target.checked) this.selectedModels.add(model.id); else this.selectedModels.delete(model.id); }
      populate();
    } });
    table.append(el("thead", {}, el("tr", {}, el("th", {}, selectAll), ["model", "capabilities", "state", "actions"].map(key => el("th", { text: t(key) })))), tbody);
    const bulk = el("div", { class: "capi-bulk" });
    const refreshBulk = () => {
      const selected = models.filter(m => this.selectedModels.has(m.id));
      const visible = visibleModels(); selectAll.checked = Boolean(visible.length) && visible.every(m => this.selectedModels.has(m.id));
      selectAll.indeterminate = !selectAll.checked && visible.some(m => this.selectedModels.has(m.id));
      const kind = ["text", "vision"].includes(this.bulkOperation) ? "text" : "image";
      const templates = this.config.templates.filter(tmp => tmp.kind === kind);
      if (!templates.some(tmp => tmp.id === this.bulkTemplate)) this.bulkTemplate = templates[0]?.id || "";
      const apply = button(t("applyBinding"), () => {
        for (const model of selected) (model.bindings ||= {})[this.bulkOperation] = this.bulkTemplate;
        this.markDirty(); populate();
      }, "primary"); apply.disabled = !selected.length || !this.bulkTemplate;
      bulk.replaceChildren(el("small", { text: t("selectedCount", { count: selected.length }) }),
        select(this.bulkOperation, operations.map(value => ({ value, label: t(`operation.${value}`) })), value => { this.bulkOperation = value; refreshBulk(); }, { "aria-label": t("bulkOperation") }),
        select(this.bulkTemplate, templates.map(tmp => ({ value: tmp.id, label: tmp.name })), value => { this.bulkTemplate = value; refreshBulk(); }, { "aria-label": t("bulkTemplate") }), apply);
    };
    const populate = () => {
      tbody.replaceChildren(...visibleModels().map(model => el("tr", {},
        el("td", {}, el("input", { type: "checkbox", checked: this.selectedModels.has(model.id), "aria-label": t("selectNamedModel", { name: model.name }), onchange: event => {
          if (event.target.checked) this.selectedModels.add(model.id); else this.selectedModels.delete(model.id); refreshBulk();
        } })),
        el("td", {}, el("div", { class: "capi-model-identity" }, brandIcon(provider, model), el("div", {}, el("strong", { text: model.name }), el("small", { text: model.model_id || "—" })))),
        el("td", {}, Object.keys(model.bindings || {}).length ? Object.keys(model.bindings).map(op => el("span", { class: "capi-tag", text: t(`operation.${op}`) })) : el("span", { class: "capi-tag", text: t("needsTemplate") })),
        el("td", { text: t(model.enabled === false ? "disabled" : "enabled") }),
        el("td", {}, button(t("edit"), () => this.navigate(() => { this.editModelId = model.id; })),
          this.context?.onSelect && model.enabled !== false && provider.enabled !== false && supportedOperations(this.config, model, this.context.operations).length ? button(t("useModel"), () => this.action(async () => {
            await this.save(); this.context.onSelect(model.id); this.dialog.close();
          }), "primary") : null))));
      const visible = visibleModels(); refreshBulk();
      if (models.length && !visible.length) tbody.append(el("tr", {}, el("td", { colSpan: 5, text: t("noMatchingModels") })));
    };
    populate();
    this.content.append(el("div", { class: "capi-row" }, el("input", { type: "search", value: this.modelQuery, placeholder: t("searchModels"), "aria-label": t("searchModels"), oninput: event => { this.modelQuery = event.target.value; populate(); } })), bulk, table);
    if (!models.length) this.content.append(el("p", { text: t("noModels") }));
  }

  modelForm(model) {
    const container = el("section", { class: "capi-editor" }, el("div", { class: "capi-row" }, el("h3", { text: t("editModel") }),
      button(t("delete"), () => this.navigate(() => { this.config.models = this.config.models.filter(m => m.id !== model.id); this.editModelId = null; this.markDirty(); }), "danger")));
    const grid = el("div", { class: "capi-grid" }, this.input(model, "name", t("displayName")), this.input(model, "model_id", t("upstreamModelId")), this.input(model, "group", t("group")));
    model.bindings ||= {};
    for (const op of operations) {
      const kind = ["text", "vision"].includes(op) ? "text" : "image";
      grid.append(field(t(`operation.${op}`), select(model.bindings[op] || "", [{ value: "", label: t("notSupported") },
        ...this.config.templates.filter(tmp => tmp.kind === kind).map(tmp => ({ value: tmp.id, label: tmp.name }))], value => {
        if (value) model.bindings[op] = value; else delete model.bindings[op];
        this.markDirty();
      })));
    }
    container.append(grid, el("div", { class: "capi-section" }, this.toggle(model, "enabled", t("enabled")),
      this.jsonInput(model.defaults || {}, t("defaultParameters"), value => { model.defaults = value; }, t("defaultParametersHint"), 4)));
    container.append(el("div", { class: "capi-form-actions" }, button(t("saveAndReturn"), () => this.action(async () => {
      await this.save(); this.editModelId = null; this.renderContent();
    }), "primary"), button(t("saveAndTest"), () => this.action(async () => {
      await this.save(); this.testState.model_id = model.id; this.testState.operation = Object.keys(model.bindings || {})[0] || "text";
      this.testState.parameters = "{}"; this.tab = "test"; this.renderContent();
    }))));
    this.content.append(container);
  }

  templateEditor() {
    this.content.append(el("div", { class: "capi-row" }, el("h2", { text: t("tab.templates") }), button(t("addTemplate"), () => this.navigate(() => {
      const template = { id: uid(), name: t("newTemplate"), kind: "text", request: { method: "POST", path: "/generate", encoding: "json", headers: {}, query: {}, body: { model: "{{model}}", prompt: "{{prompt}}" }, files: [] }, response: { text: "$.text", error: "$.error.message" }, parameters: [] };
      this.config.templates.push(template); this.templateId = template.id; this.markDirty();
    }), "primary")), el("p", { text: t("templatesHint") }));
    this.templateId ||= this.config.templates[0]?.id;
    const selected = this.config.templates.find(tmp => tmp.id === this.templateId);
    const list = el("div", { class: "capi-template-list" }, this.config.templates.map(tmp => button(tmp.name,
      () => this.navigate(() => { this.templateId = tmp.id; }), selected?.id === tmp.id ? "active" : "")));
    const editor = el("div", { class: "capi-template-editor" });
    if (selected) {
      editor.append(el("div", { class: "capi-row" }, button(t("duplicate"), () => this.navigate(() => {
        const copy = structuredClone(this.config.templates.find(tmp => tmp.id === selected.id)); copy.id = uid(); copy.name += " · " + t("copy"); this.config.templates.push(copy); this.templateId = copy.id; this.markDirty();
      })), button(t("delete"), () => this.navigate(() => {
        if (this.config.models.some(model => Object.values(model.bindings || {}).includes(selected.id))) throw { code: "template_in_use" };
        this.config.templates = this.config.templates.filter(tmp => tmp.id !== selected.id); this.templateId = this.config.templates[0]?.id; this.markDirty();
      }), "danger")));
      const editable = structuredClone(selected); delete editable.id;
      editor.append(this.jsonInput(editable, t("templateJSON"), value => {
        if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("object");
        this.config.templates = this.config.templates.map(tmp => tmp.id === selected.id ? { ...value, id: selected.id } : tmp);
      }, t("templateSecrets"), 24), el("small", { text: t("templateVariables") }));
    }
    this.content.append(el("div", { class: "capi-template-layout" }, list, editor));
  }

  testForm() {
    const state = this.testState;
    const active = this.config.models.filter(model => model.enabled !== false && this.config.providers.some(p => p.id === model.provider_id && p.enabled !== false));
    this.content.append(el("h2", { text: t("tab.test") }), el("p", { text: t("testHint") }));
    const model = active.find(m => m.id === state.model_id);
    const opOptions = operations.filter(op => model?.bindings?.[op]);
    if (!opOptions.includes(state.operation)) state.operation = opOptions[0] || "text";
    const refreshDefaults = () => {
      state.parameters = pretty(Object.fromEntries(parameterSchema(this.config, state.model_id, state.operation).filter(p => p.default !== undefined).map(p => [p.name, p.default])));
    };
    this.content.append(el("div", { class: "capi-grid" }, field(t("model"), select(state.model_id,
      [{ value: "", label: t("selectModel") }, ...active.map(m => ({ value: m.id, label: `${this.config.providers.find(p => p.id === m.provider_id)?.name} / ${m.name}` }))], value => {
        state.model_id = value; const selected = active.find(m => m.id === value); state.operation = Object.keys(selected?.bindings || {})[0] || "text";
        refreshDefaults(); this.renderContent();
      }, { disabled: this.testRunning })), field(t("operation"), select(state.operation, opOptions.map(value => ({ value, label: t(`operation.${value}`) })), value => {
        state.operation = value; refreshDefaults(); this.renderContent();
      }, { disabled: this.testRunning }))));
    this.content.append(field(t("prompt"), el("textarea", { value: state.prompt, rows: 4, oninput: event => { state.prompt = event.target.value; } })),
      field(t("system"), el("textarea", { value: state.system, rows: 2, oninput: event => { state.system = event.target.value; } })),
      field(t("parameters"), el("textarea", { class: "code", value: state.parameters, rows: 3, oninput: event => { state.parameters = event.target.value; } })),
      field(t("inputImages"), el("input", { type: "file", accept: "image/png,image/jpeg,image/webp", multiple: true, onchange: event => this.action(async () => {
        const files = Array.from(event.target.files);
        if (files.length > 16 || files.reduce((sum, file) => sum + file.size, 0) > 24 * 1024 * 1024) throw { code: "media_too_large" };
        state.images = await Promise.all(files.map(readFile)); this.status(t("imagesSelected", { count: files.length }));
      }) }), t("imagesSelected", { count: state.images.length })));
    const actions = el("div", { class: "capi-row" });
    const preview = button(t("previewRequest"), () => this.action(() => this.runTest(true)));
    const run = button(t(this.testRunning ? "running" : "runTest"), () => this.action(() => this.runTest(false)), "primary");
    preview.disabled = run.disabled = this.testRunning || !model || !opOptions.length;
    actions.append(preview, run);
    if (this.testRunning) actions.append(button(t("cancel"), () => this.action(async () => {
      await this.request(`/jobs/${this.jobId}/cancel`, "POST", {}); this.status(t("cancelling"));
    })));
    this.content.append(actions);
    this.resultContainer = el("div"); this.content.append(this.resultContainer);
    this.renderTestResult();
  }

  async runTest(preview) {
    this.flushEditors();
    if (this.dirty) await this.save();
    const state = this.testState;
    this.status(t(preview ? "preparingPreview" : "running"));
    const result = await this.request("/test", "POST", { ...state, parameters: parseObject(state.parameters), preview });
    if (preview) { this.testResult = result; this.renderTestResult(); this.status(t("previewReady")); return; }
    this.jobId = result.id; this.testRunning = true; this.testResult = null; this.renderContent();
    this.pollTest();
  }

  async pollTest() {
    let failures = 0;
    while (this.testRunning) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      try {
        const job = await this.request(`/jobs/${this.jobId}`);
        failures = 0;
        if (job.state === "running") {
          this.status(job.progress ? `${t("running")} · ${job.progress.status} · ${job.progress.task_id}` : t("running"));
          continue;
        }
        this.testRunning = false;
        this.testResult = job.result || job;
        if (this.tab === "test") this.renderContent();
        this.status(job.error ? errorText(job.error) : t(`state.${job.state}`), Boolean(job.error));
      } catch (error) {
        this.status(errorText(error), true);
        if (++failures >= 5) { this.testRunning = false; if (this.tab === "test") this.renderContent(); }
      }
    }
  }

  renderTestResult() {
    if (!this.resultContainer?.isConnected || !this.testResult) return;
    this.resultContainer.replaceChildren();
    const result = this.testResult;
    if (result.images?.length) this.resultContainer.append(el("div", { class: "capi-result-images" }, result.images.map(src => el("img", { src, alt: t("generatedImage") }))));
    this.resultContainer.append(el("pre", { text: pretty({ ...result, ...(result.images ? { images: t("imageResults", { count: result.images.length }) } : {}) }) }));
  }

  async showHistory() {
    this.content.append(el("div", { class: "capi-row" }, el("h2", { text: t("tab.history") }), button(t("refresh"), () => this.renderContent())), el("p", { text: t("historyHint") }));
    const target = el("div"); this.content.append(target);
    try {
      const history = await this.request("/history");
      if (!history.items.length) target.append(el("p", { text: t("noHistory") }));
      for (const entry of history.items) target.append(el("details", { class: "capi-section" },
        el("summary", { text: `${entry.provider} / ${entry.model} · ${t(`state.${entry.status}`)} · ${entry.duration_ms} ms · ${new Date(entry.time * 1000).toLocaleTimeString()}` }),
        el("pre", { text: pretty(entry) })));
    } catch (error) { this.status(errorText(error), true); }
  }
}
