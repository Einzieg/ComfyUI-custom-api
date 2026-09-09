# 发布与收录

- 源码仓库：[Einzieg/ComfyUI-custom-api](https://github.com/Einzieg/ComfyUI-custom-api)。
- 安装包：[GitHub Releases](https://github.com/Einzieg/ComfyUI-custom-api/releases)。
- 许可：[MIT](../LICENSE)，LobeHub 图标另附上游 MIT 许可。
- 搜索名称：`ComfyUI Custom API`；Registry 包 ID：`comfyui-custom-api`。

公开 GitHub 仓库不会自动加入 ComfyUI 的自定义节点搜索目录。

## ComfyUI-Manager

按[官方收录流程](https://github.com/Comfy-Org/ComfyUI-Manager#how-to-register-your-custom-node-into-comfyui-manager)，向 `custom-node-list.json` 添加条目并提交 PR。PR 合并、远程目录更新后，可在 Manager 的 **Custom Nodes** 中搜索 `ComfyUI Custom API`。列表仍旧时刷新目录；旧版 Manager 可选择 `Channel (remote)`。

已提交 [收录 PR #3258](https://github.com/Comfy-Org/ComfyUI-Manager/pull/3258)，目前等待合并。上游 JSON 校验通过；真实 ComfyUI 0.35.0 / Manager 3.41 的本地目录接口返回 HTTP 200，并找到唯一对应条目。审核期间可从 GitHub 克隆或使用发布 ZIP 安装。

## Comfy Registry

Registry 是新版节点管理器的目录来源。需要在 [registry.comfy.org](https://registry.comfy.org) 创建发布者，获取真实的 Publisher ID 和 Registry 发布密钥。GitHub 登录凭据不能代替此密钥。

1. 在 `pyproject.toml` 中填写已注册的 `PublisherId`，提交到 `main`。该身份在 Registry 中不可更改，请使用实际值。
2. 将发布密钥保存到仓库的 Actions Secret：`REGISTRY_ACCESS_TOKEN`。不要写入源码、Issue 或聊天。
3. 在 GitHub Actions 中手动运行 **Publish to Comfy Registry**。工作流先运行测试、检查元数据，再发布当前 `main` 的版本。
4. 检查 Registry 中的版本状态和实际搜索结果。提交成功与完成审核/索引是不同状态。

发布者为 `einzieg`，[Registry 节点页面](https://registry.comfy.org/nodes/comfyui-custom-api)。`0.2.0` 已通过 [GitHub Actions](https://github.com/Einzieg/ComfyUI-custom-api/actions/runs/34345569309) 上传，官方搜索接口已返回该插件，安装接口和 CDN 安装包已验证。当前版本状态为 `NodeVersionStatusPending`，仍待平台审核；该状态不等于审核已完成。

后续发布需递增 `pyproject.toml` 的版本；已发布的版本号不可重复使用。后续文档、截图和图标更新会随下一个 Registry 版本打包；GitHub 始终显示最新文档。

`.comfyignore` 排除测试及开发脚本。`.gitignore` 排除本地配置、密钥和 `.dev` 测试环境。官方流程详见 [Publishing Nodes](https://docs.comfy.org/registry/publishing)。
