<p align="center">
  <img src="assets/logo.svg" width="104" height="104" alt="ComfyUI Custom API logo">
</p>

<h1 align="center">ComfyUI Custom API</h1>

<p align="center">Connect your model APIs to your ComfyUI workflows.</p>

<p align="center">
  <a href="https://github.com/Einzieg/ComfyUI-custom-api/releases"><img src="https://img.shields.io/github/v/release/Einzieg/ComfyUI-custom-api?color=5a9bff" alt="Release"></a>
  <a href="https://github.com/Einzieg/ComfyUI-custom-api/actions/workflows/test.yml"><img src="https://github.com/Einzieg/ComfyUI-custom-api/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-5a9bff" alt="MIT License"></a>
  <a href="https://registry.comfy.org/nodes/comfyui-custom-api"><img src="https://img.shields.io/badge/Comfy_Registry-published-5a9bff" alt="Comfy Registry"></a>
</p>

<p align="center">
  <a href="../README.md">简体中文</a> · English · <a href="#install">Install</a> · <a href="templates.md">Request templates</a> · <a href="https://github.com/Einzieg/ComfyUI-custom-api/issues">Issues</a>
</p>

Configure providers, discover models and customize request formats from the topbar. Use nodes for **text, vision, image generation and image editing**, with English and Simplified Chinese interfaces. No local model weights required.

![API nodes in a real ComfyUI workflow](assets/workflow.png)

<p align="center"><sub>Captured from the running extension with local demo configuration. Brand and model names are examples, not provider compatibility certifications.</sub></p>

## Features

| Capability | What it provides |
|---|---|
| **Providers** | Custom names, LobeHub icons, Base URLs, keys, authentication, timeouts and concurrency |
| **Models** | Discovery or manual entry; unified search; aliases, groups and bulk template assignment |
| **Requests** | JSON, forms and multipart; configurable paths, headers, queries, variables and response extraction |
| **Nodes** | Text / vision, image generation / editing, and composable JSON parameters |
| **Execution** | Async polling, cancellation, cached results and an explicit request nonce |
| **Configuration** | Separate local credential storage; saved keys excluded from workflows and configuration exports |

### Model management

Manage providers and model capabilities in one panel. Choose from **322 bundled LobeHub brand icons**, served locally.

![Provider and model management](assets/models.png)

<details>
<summary><strong>Request template editor and icon picker</strong></summary>

Edit request and response mappings to match your provider's documentation. Preview the request before making a call.

![Custom request template editor](assets/templates.png)

Search the local icon library or match icons from provider names automatically.

![LobeHub icon picker](assets/icons.png)

</details>

## Install

### Custom node manager

Search for **`comfyui-custom-api`** or **`ComfyUI Custom API`**.

- [Comfy Registry](https://registry.comfy.org/nodes/comfyui-custom-api): listed; installable versions depend on platform review.
- Legacy Manager catalog: [inclusion PR #3258](https://github.com/Comfy-Org/ComfyUI-Manager/pull/3258) awaits merging.

If the catalog has not refreshed or installation is unavailable, use Git or the release ZIP. [Publishing status →](publishing.md)

### Git or ZIP

Open PowerShell 7 in your **running ComfyUI installation's** `custom_nodes` directory:

```powershell
$ErrorActionPreference = 'Stop'
git clone https://github.com/Einzieg/ComfyUI-custom-api.git
if ($LASTEXITCODE -ne 0) { throw 'Plugin download failed' }
```

Alternatively, extract `ComfyUI-custom-api` from the [latest release ZIP](https://github.com/Einzieg/ComfyUI-custom-api/releases/latest) into `custom_nodes`.

Install `requirements.txt` using **that ComfyUI installation's Python**, then restart ComfyUI and refresh your browser. Replace these example paths:

```powershell
$ErrorActionPreference = 'Stop'
& 'D:\ComfyUI\venv\Scripts\python.exe' -m pip install -r 'D:\ComfyUI\custom_nodes\ComfyUI-custom-api\requirements.txt'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
```

Windows portable builds usually use `python_embeded\python.exe`. Validated with **ComfyUI 0.35.0 / frontend 1.51.10 / Python 3.13.12**, CPU mode.

## Quick start

Starting with **0.2.2**, the server owner must create `network-policy.json` in the private configuration directory, approve the API and image download origins, and restart ComfyUI. Outbound requests are denied by default. The web UI and configuration imports cannot change this allow-list. [Configuration example and upgrade notes](network-policy.md#english)

1. **Add a provider** using **API** in the topbar or **Extensions → Model API**. Enter its Base URL and authentication.
2. **Fetch models** with **Save & fetch models**, or add model IDs manually.
3. **Assign templates** to the model's supported operations. Copy and edit templates for nonstandard endpoints.
4. **Use a node**: choose a model in the searchable picker, enter a prompt, and run the workflow.

| Operation | Common template starting point |
|---|---|
| Text / vision | `Chat Completions` |
| Image generation | `Images · Generate` |
| Image editing | `Images · Edit` |
| Custom asynchronous tasks | Async task template, adapted to the provider's API |

**Discovery retrieves model IDs; it does not guess model capabilities.** Assign an operation template before a new model appears in the relevant node picker. Request previews make no generation call; running a test can incur provider charges.

## Nodes

| Node | Purpose | Outputs |
|---|---|---|
| **API Text / Vision** | Prompts, system messages and optional images | Text, redacted response JSON, call metadata |
| **API Image** | Image generation / editing, optional images and mask | IMAGE list, redacted response JSON, call metadata |
| **API Parameter** | Compose typed parameters through connections | Parameter JSON |

Images connect to `PreviewImage` or `SaveImage`, preserving different sizes in output lists. **Connect input** exposes sockets beside prompts, system messages and parameters. Advanced controls start collapsed.

**New result next run** updates the nonce; a request is sent when the workflow next runs. Paid submissions are not automatically retried.

## Documentation

- [Usage guide](usage.en.md): request parameters, configuration, caching, localization and limitations.
- [Template examples](templates.md): variables, request formats and response extraction.
- [Validation](validation.md): **33 backend tests + 9 frontend tests**, plus real ComfyUI workflow checks.
- [Publishing](publishing.md): Registry, Manager and maintainer release steps.

Keys are stored separately under `user/__custom_api/secrets.json` or read from configured environment variables. Local key files are plaintext protected by file permissions. Configuration is shared within a ComfyUI instance; there is no multi-tenant isolation.

Video/audio nodes, streaming, arbitrary scripts, cURL import and multistep storage uploads are outside this release. See the usage guide for protocol boundaries.

Development requires Python, PyTorch, `pytest`, `requirements.txt` dependencies and Node.js 22+. Run `python -m pytest -q` and `node --test tests/frontend.test.mjs`. Building with `scripts/package.py` requires Python 3.11+. Tests use a local mock provider and make no paid model calls.

Issues and pull requests for fixes, translations and request templates are welcome. Remove credentials and private configuration before sharing reports.

## License and credits

The project and its original logo use the [MIT License](../LICENSE). Thanks to [ComfyUI](https://github.com/Comfy-Org/ComfyUI) and [LobeHub Icons](https://icons.lobehub.com/). Brand icons come from `@lobehub/icons-static-svg@1.95.0` with its MIT license retained. [Icon provenance](icons.md) · [Screenshot and asset notes](assets/README.md).

Thanks also to the [LINUX DO](https://linux.do/) community for sharing knowledge and ideas.
