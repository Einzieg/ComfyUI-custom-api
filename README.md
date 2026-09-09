# ComfyUI Custom API

在 ComfyUI 中管理自定义模型供应商，并通过节点调用文本、识图、生图和图片编辑 API。提供简体中文和英文界面。

当前版本：**0.2.0**。新增本地 LobeHub 图标库、紧凑节点、统一模型搜索和批量接口绑定。

[English](docs/README.en.md) · [接口模板说明](docs/templates.md) · [验证记录](docs/validation.md)

[GitHub](https://github.com/Einzieg/ComfyUI-custom-api) · [下载安装包](https://github.com/Einzieg/ComfyUI-custom-api/releases/latest) · [反馈问题](https://github.com/Einzieg/ComfyUI-custom-api/issues) · [MIT License](LICENSE)

## 安装

ComfyUI-Manager 收录正在申请，暂时不能保证在默认目录搜索到。收录进度与 Registry 发布说明见 [发布说明](docs/publishing.md)。

### 从 GitHub 安装

在 **实际运行的 ComfyUI** 的 `custom_nodes` 目录打开 PowerShell 7：

```powershell
$ErrorActionPreference = 'Stop'
git clone https://github.com/Einzieg/ComfyUI-custom-api.git
if ($LASTEXITCODE -ne 0) { throw '插件下载失败' }
```

也可从 [Releases](https://github.com/Einzieg/ComfyUI-custom-api/releases/latest) 下载 ZIP：

1. 将发布包中的 `ComfyUI-custom-api` 文件夹放进 `custom_nodes` 目录。已通过 Git 安装时跳过此步。
2. 使用 **ComfyUI 自己的 Python 环境** 安装本插件的 `requirements.txt`。
3. 重启 ComfyUI，刷新浏览器。

PowerShell 7 示例（将路径改成你的实际安装位置）：

```powershell
$ErrorActionPreference = 'Stop'
& 'D:\ComfyUI\venv\Scripts\python.exe' -m pip install -r 'D:\ComfyUI\custom_nodes\ComfyUI-custom-api\requirements.txt'
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败' }
```

Windows 便携包通常使用 `python_embeded\python.exe`。插件不需要下载模型权重，API 节点可以在 CPU 模式运行。

测试环境：ComfyUI **0.35.0**、前端 **1.51.10**、Python **3.13.12**。旧版前端若没有工具栏入口，可尝试主菜单的 **Extensions → 模型 API**；旧版本不在本次完整验证范围内。

## 第一次使用

1. 点击顶部操作栏的 **API**，或主菜单 **Extensions → 模型 API**。
2. 添加供应商，填写名称、Base URL、鉴权方式及 API Key。可搜索选择 LobeHub 图标，也可根据名称自动匹配。
3. 点击“保存并获取模型”，或保存后手动添加模型。
4. 编辑模型，为支持的操作绑定模板：
   - 文本/识图：`Chat Completions`。
   - 生图：`Images · Generate`。
   - 图片编辑：`Images · Edit`。
   - 非标准接口：复制模板并按供应商文档修改。
5. 在“调用测试”中先预览请求，再根据需要点击实际调用。实际调用可能产生供应商费用。
6. 在工作流中添加 `API 文本 / 识图` 或 `API 图像`。点击节点顶部的模型选择器，搜索并选择模型；可按供应商筛选。

自动发现仅获取模型 ID 和名称，**不会猜测模型能力**。新发现的模型需要绑定模板。刷新列表会保留手动模型、别名、分组、绑定和参数。

模型列表支持勾选多项后批量绑定指定操作的模板；应用会替换所选模型在该操作上的绑定，保留其他操作。全选只选择当前搜索结果。模型编辑使用独立页面，可“保存并返回”或“保存并测试”。从节点进入管理面板时，可点击模型行中的“使用”返回当前节点。

## 节点操作

- 顶部模型选择器同时搜索模型名称、ID、分组和供应商，只列出当前节点类型可用的模型。
- 选择模型后同步供应商，并选用该模型支持的操作；不会在配置刷新时自动替换已选模型。
- 模型参数、系统提示词、JSON 和缓存设置收在“参数与高级设置”中，按需展开。
- 提示词、系统提示词和参数旁的“接入节点”可显示连线插槽。连接上游节点后，相应内容由连线提供；断开连线后可切回手动输入。
- “下次重新请求”更新请求编号，之后点击 ComfyUI 的运行按钮才会发送请求。
- 文本结果在收到响应后显示，可折叠、复制；没有结果时不占空白区域。

保留了 0.1.0 工作流的节点类型、输入名称和序列化顺序。升级不会迁移或覆盖供应商密钥。

## 品牌图标

内置 **322 个 LobeHub 品牌图标**，来自官方 [`@lobehub/icons-static-svg` 1.95.0](https://github.com/lobehub/lobe-icons)。图标随插件本地提供，运行时不请求外部图标 CDN。单色图标随界面颜色显示，彩色图标保留品牌色。

供应商图标可手动选择，或根据名称/地址自动匹配；模型列表及节点也会识别已知模型品牌。原有自定义图片仍可使用。来源和许可见 [图标说明](docs/icons.md)。

## 节点

| 节点 | 输入 | 输出 |
|---|---|---|
| API 文本 / 识图 | 提示词、系统提示词、参数 JSON、可选图片批次 | 文本、脱敏响应 JSON、调用信息 JSON；可在节点内查看文本 |
| API 图像 | 提示词、参数 JSON、可选图片批次和遮罩 | IMAGE 列表、脱敏响应 JSON、调用信息 JSON |
| API 参数 | 参数名称、字符串或 JSON 值、可选已有参数 JSON | 合并后的参数 JSON，可串联多个节点 |

图像输出可直接连接 `PreviewImage`、`SaveImage` 或其他图像节点。多张不同尺寸图片作为 ComfyUI 列表输出，保持原始尺寸，不强制缩放成同一个批次。

模板的参数定义会生成节点控件。模型默认参数覆盖模板默认值，节点参数再覆盖模型默认值。也可以把 `parameters` 转成输入，通过其他节点传入完整 JSON。**参数只有被接口模板引用时才会发送**，例如 `{{params.seed}}`；插件不会自动向供应商添加未声明字段。

遮罩输入采用 ComfyUI 的语义：1 表示编辑区域。上传时转为 PNG alpha 遮罩，透明区域表示编辑区域。供应商使用其他遮罩约定时，应先在工作流中转换，或改用符合其约定的图片输入与模板。

## 请求、响应和任务

- 支持 GET / POST / PUT / PATCH / DELETE、JSON、URL 编码表单和 multipart 文件上传。
- 支持 Bearer、自定义 Header、自定义 Query 鉴权和无鉴权。
- 支持嵌套 JSON、数组及保留数值/布尔类型的变量替换。
- 调用测试中的图片展示为最长边 1024 像素的预览图；图像节点输出保持原图。
- 图片支持远程 URL、Base64、Data URL 或直接返回的图片二进制。
- 异步接口支持提交任务、任务 ID 提取、状态轮询、超时和可选远端取消。
- 每个供应商可设置超时、并发数、HTTP 代理。
- GET 遇到 429/502/503/504 最多重试两次。**生成请求不会自动重试**，避免重复提交和扣费。
- 点击停止会取消本地等待；模板配置了 `poll.cancel` 时尝试请求远端取消。远端是否停止取决于供应商，无法保证退费。

详见 [模板配置示例](docs/templates.md)。预设只是常见格式的起点，同一模型名称在不同供应商下可能需要不同请求参数。

## 缓存与重新请求

默认 `reuse` 复用 ComfyUI 缓存。修改提示词、输入图片、参数或请求编号，才会再次请求。当前模型所引用的供应商、密钥或模板配置改变后，相关缓存也会失效。

- 修改 `request_nonce` 可主动发起新请求；它是缓存控制编号，不是模型随机种子。
- `refresh` 表示每次运行都请求，可能产生重复费用。
- 语言选择写入工作流展示属性，不作为模型输入，不会因切换语言单独触发新请求。

## 语言

管理面板可选择“跟随 ComfyUI / 简体中文 / English”。面板和现有节点的显示随设置更新。节点库与 ComfyUI 自带控件的翻译由宿主语言系统负责。

用户自定义的供应商名称、模型别名、提示词和模型返回内容原样显示。自定义参数标签可写成 `{"zh":"温度","en":"Temperature"}`。新增语言需要在源码中扩展语言选择与 `web/locales`，并调整、运行 `scripts/sync_locales.py` 生成宿主语言文件。

## 配置与密钥

- 默认使用 ComfyUI 的私有系统用户目录：`ComfyUI/user/__custom_api/`；自定义 `--user-directory` 时相应调整。
- `config.json` 保存供应商、模型和模板；`secrets.json` 单独保存密钥。
- 可设置 `COMFYUI_CUSTOM_API_DIR` 为独立私有目录。不要放进可通过 HTTP 访问的目录。
- 密钥也可通过供应商设置中的环境变量名称读取。环境变量优先于已存密钥。
- API Key 输入框不会回显旧密钥。不修改字段会保留密钥；编辑后清空表示删除密钥。
- 工作流与 PNG 元数据仅包含配置 ID。导出配置不包含已存密钥，导入会生成新的 ID 并保留当前配置。
- 供应商密钥不会随图片下载发送给不同域名的 CDN。
- 配置使用原子写入和修订号检查，防止两个窗口无提示地覆盖彼此的更改。

首版配置按 **ComfyUI 实例共享**，适合本机或受信任团队使用；不提供租户隔离或独立账号系统。密钥文件是受文件权限保护的本地明文文件，未宣称静态加密。对外部署应使用 ComfyUI 外部的认证与访问控制。

## 开发与验证

以下命令需要完整源码，安装包不包含开发脚本与测试。后端的 HTTP、模板和配置功能可独立于 ComfyUI 测试；完整图片节点测试使用 ComfyUI 环境里的 PyTorch。

开发依赖：`requirements.txt`、`pytest`、PyTorch，以及 Node.js 22 或更高版本。运行 `scripts/package.py` 构建安装包需要 Python 3.11 或更高版本。GitHub Actions 使用本地模拟供应商执行后端和前端测试。

```powershell
$ErrorActionPreference = 'Stop'
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw '后端测试失败' }
node --test tests/frontend.test.mjs
if ($LASTEXITCODE -ne 0) { throw '前端测试失败' }
```

`tests/mock_provider.py` 是只监听本机的模拟供应商，供开发验证，不会产生真实 API 费用。`scripts/smoke_comfyui.py` 会修改固定测试端口 `8191` 的配置，仅用于 `.dev` 隔离测试实例，**不要指向生产实例**。

`example_workflows` 提供 ComfyUI API 格式的文本和生图示例。示例中的 `provider_id`、`model_id` 留空，使用前需选择或填入自己配置的供应商和模型。

首版暂未实现视频/音频节点、流式文本、任意代码脚本、cURL 导入、费用账单和第三方文件存储上传。需要“先上传到专属存储取得 file_id，再发生成请求”的接口暂不直接适配；可先由上游节点提供已上传资源的 URL/ID，再通过参数模板引用。
