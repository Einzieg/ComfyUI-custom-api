# 发布与收录

- 源码仓库：[Einzieg/ComfyUI-custom-api](https://github.com/Einzieg/ComfyUI-custom-api)。
- 安装包：[GitHub Releases](https://github.com/Einzieg/ComfyUI-custom-api/releases)。
- 许可：[MIT](../LICENSE)，LobeHub 图标另附上游 MIT 许可。
- 搜索名称：`ComfyUI Custom API`；Registry 包 ID：`comfyui-custom-api`。

当前工作区为 **0.3.0 开发版**，新增默认/严格网络模式和管理会话。以下 0.2.x 审核记录是历史状态，不代表 0.3.0 已发布或获准；新版本需要独立复核。

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

发布者为 `einzieg`，[Registry 节点页面](https://registry.comfy.org/nodes/comfyui-custom-api)。上传与平台审核是两个步骤；发布工作流成功不代表版本已获准安装。

2026-09-10 复核时，`0.2.1` 为 `NodeVersionStatusFlagged`。公开版本列表加 `include_status_reason=true` 可查看扫描原因；[人工复核申请 #230](https://github.com/Comfy-Org/registry-backend/issues/230) 已提交。随后 Manager 维护者指出配置接口缺少独立出站白名单，0.2.2 对此增加服务器本地策略并调整官方国际化集成；应使用修复后的版本，后续版本仍需单独经过 Registry 审核。若 Registry 暂时无法安装，请使用 [GitHub 最新 Release](https://github.com/Einzieg/ComfyUI-custom-api/releases/latest) 或 Git 安装。

后续发布需递增 `pyproject.toml` 的版本；已发布的版本号不可重复使用。后续文档、截图和图标更新会随下一个 Registry 版本打包；GitHub 始终显示最新文档。

`.comfyignore` 排除测试及开发脚本。`.gitignore` 排除本地配置、密钥和 `.dev` 测试环境。官方流程详见 [Publishing Nodes](https://docs.comfy.org/registry/publishing)。
