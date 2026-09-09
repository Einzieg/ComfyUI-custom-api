# Development references

Official ComfyUI documentation used to verify extension registration, locale files and execution behavior:

- [Topbar menu](https://docs.comfy.org/custom-nodes/js/javascript_topbar_menu)
- [Custom node properties and caching](https://docs.comfy.org/custom-nodes/backend/server_overview)
- [Custom node localization](https://docs.comfy.org/custom-nodes/i18n)
- [Custom HTTP routes](https://docs.comfy.org/development/comfyui-server/comms_routes)
- [Frontend extension types](https://github.com/Comfy-Org/ComfyUI_frontend/blob/main/src/types/comfy.ts): `actionBarButtons` and menu commands.
- [ComfyUI source](https://github.com/Comfy-Org/ComfyUI): isolated CPU host used for validation.
- [Registry publishing](https://docs.comfy.org/registry/publishing) and [metadata specifications](https://docs.comfy.org/registry/specifications): publisher credentials, archive exclusions, and release metadata.
- [ComfyUI-Manager registration](https://github.com/Comfy-Org/ComfyUI-Manager#how-to-register-your-custom-node-into-comfyui-manager): submit a catalog entry through a pull request.

Documentation retrieval commands, run from PowerShell 7:

```powershell
$ErrorActionPreference = 'Stop'
smart-search fetch 'https://docs.comfy.org/custom-nodes/js/javascript_topbar_menu' --format markdown
smart-search fetch 'https://docs.comfy.org/custom-nodes/backend/server_overview' --format markdown
smart-search fetch 'https://docs.comfy.org/custom-nodes/i18n' --format markdown
smart-search fetch 'https://docs.comfy.org/development/comfyui-server/comms_routes' --format markdown
smart-search fetch 'https://docs.comfy.org/registry/publishing' --format markdown
smart-search fetch 'https://docs.comfy.org/registry/specifications' --format markdown
```
