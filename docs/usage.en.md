# Usage guide

[Project overview](README.en.md) · [Template examples](templates.md)

## Templates

Version **0.2.0** adds 322 bundled [LobeHub brand icons](https://github.com/lobehub/lobe-icons), a compact node interface and searchable model selection across providers. Advanced controls start collapsed; text results appear after execution. Use **Connect input** beside prompt, system or parameters to expose a socket. Connected values come from upstream nodes. **New result next run** updates the nonce; it does not submit a request until you press ComfyUI Run.

Provider settings include a searchable icon library and **Save & fetch models**. The model list supports bulk template assignment to selected models, while the editor provides **Save & return** and **Save & test**. Opening the manager from a node also provides a **Use** action. Existing workflow input order and provider credentials are preserved.

Icons are served locally from `@lobehub/icons-static-svg@1.95.0` under the MIT license. See [icon provenance](icons.md).

Templates configure HTTP methods, relative endpoint paths, headers, queries, JSON/form/multipart bodies, response extraction and asynchronous polling. The built-in templates cover common Chat Completions, Images generation/edit, and a customizable asynchronous task pattern.

Use placeholders such as `{{model}}`, `{{prompt}}`, `{{messages}}`, `{{params.temperature}}`, `{{image}}`, `{{images}}`, `{{api_key}}`, and `{{task_id}}`. Whole-value placeholders preserve JSON types. Paths support `$.data[0].url`, `$.data[*]` and bracketed string keys. No executable scripting is supported.

Template parameters define typed controls. Model defaults override template defaults; node parameters override model defaults. Only parameters explicitly referenced in the request template are sent.

See the JSON examples in [templates.md](templates.md). Polling supports an optional cancellation request; local cancellation cannot guarantee remote termination or refunds. Paid submissions are never automatically retried. Transient read-only GET requests may retry twice.

## Configuration and privacy

The default location is ComfyUI's private system-user directory, `user/__custom_api`. `config.json` and `secrets.json` are separate. Set `COMFYUI_CUSTOM_API_DIR` to use another private directory, or configure an environment variable as a provider's API key source.

Saved keys are never returned by the configuration endpoint. Workflows and PNG metadata contain configuration IDs, and exports omit stored keys. Imports create new IDs and do not overwrite existing entries. Credentials are not forwarded to different image download hosts. API templates should reference `{{api_key}}` instead of containing literal credentials.

This first release shares configuration within a ComfyUI instance; it does not implement multi-tenant accounts. Local key files are plaintext protected by file permissions, not encrypted storage. Use external authentication and access control for shared deployments.

## Execution and localization

The default cache mode reuses unchanged results. Change the request nonce to request another result, or select `refresh` to request every time. A nonce is not a model seed. Changing the selected provider, key, model or template invalidates the related cache. UI language is stored as presentation metadata rather than a model input.

The panel and existing node displays use the plugin language preference. The node library uses ComfyUI's locale files. Custom provider/model names and model outputs remain untranslated.

Video/audio nodes, streaming, cURL import, arbitrary scripts, multi-step file storage uploads, automatic model-list pagination and restart recovery for remote tasks are outside this release.
