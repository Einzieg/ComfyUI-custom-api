# 自定义接口模板

模板是 JSON 配置，不执行 Python 或 JavaScript。模板内部 ID 固定；显示名称可以修改。建议复制一个预设再编辑，保存时会校验结构。

## 同步文本示例

下面的内容可以放进面板的“模板 JSON”编辑器。编辑器会保留当前模板的内部 ID。

```json
{
  "name": "自定义文本接口",
  "kind": "text",
  "request": {
    "method": "POST",
    "path": "/generate",
    "encoding": "json",
    "headers": {"X-API-Version": "2026-01"},
    "query": {},
    "body": {
      "model_name": "{{model}}",
      "input": "{{prompt}}",
      "options": {"temperature": "{{params.temperature}}"}
    },
    "files": []
  },
  "response": {
    "text": "$.result.text",
    "error": "$.error.message",
    "usage": "$.usage"
  },
  "parameters": [
    {
      "name": "temperature",
      "label": {"zh": "温度", "en": "Temperature"},
      "type": "number",
      "default": 0.7,
      "min": 0,
      "max": 2
    }
  ]
}
```

`base_url = https://host.example/v1` 与 `path = /generate` 拼成 `https://host.example/v1/generate`，保留 Base URL 的路径前缀。路径不接受其他供应商的完整 URL。动态路径变量会经过 URL 编码，查询参数放进 `query`。

## 变量

| 变量 | 类型与含义 |
|---|---|
| `{{model}}` | 供应商实际模型 ID |
| `{{prompt}}` / `{{system}}` | 提示词、系统提示词 |
| `{{messages}}` | 常见 Chat Completions 消息数组；有图片时生成多模态 content 数组 |
| `{{params}}` | 合并后的完整参数对象 |
| `{{params.name}}` | 指定参数 |
| `{{image}}` | 第一张输入图片的 Data URL，无输入时为空字符串 |
| `{{images}}` | 所有输入图片的 Data URL 数组 |
| `{{image_base64}}` | 第一张图片不含前缀的 Base64 |
| `{{mask}}` | 遮罩 PNG 的 Data URL，无输入时为空字符串 |
| `{{api_key}}` | 后端密钥，仅在发请求时解析 |
| `{{task_id}}` | 仅用于轮询/取消阶段的远端任务 ID |

如果整个 JSON 值是占位符，保留原始类型。例如 `"n": "{{params.n}}"` 会产生数值，`"input": "{{messages}}"` 会产生数组。`"prefix {{prompt}}"` 会产生字符串。变量不存在时明确报错，不静默替换为空。

支持的提取路径：`$.data[0].url`、`$.data[*].url`、`$["key.with.dots"]`。这不是完整 JSONPath 实现，不支持筛选表达式、脚本、递归搜索或负索引。

## 参数定义

`parameters` 是字段数组。`name` 为固定参数键，`label` 可为字符串或语言映射。类型支持 `string`、`integer`、`number`、`boolean`、`enum`、`json`；可使用 `default`、`required`、`min`、`max`。`enum` 需要 `options` 数组。

自定义字段只是构造参数值；必须在 `request.body`、`headers`、`query` 或路径中引用，才会发送给供应商。

## 图像返回

将 `kind` 设为 `image`。例如：

```json
{
  "images": "$.data[*]",
  "image_value": "auto",
  "error": "$.error.message"
}
```

`image_value = auto` 支持字符串以及含 `url`、`b64_json` 或 `base64` 的对象。特殊结构可以填写对象内部路径，比如 `$.asset.download_url`。`images` 可以提取一张图片，也可以提取图片数组。

供应商直接返回 `image/*` 二进制时自动转换，不需要 `images` 路径。单张图片最多 32 MB / 4000 万像素，一次最多 16 张；JSON 响应最多 64 MB。

## 表单与文件上传

`encoding` 可为 `json`、`form`、`multipart`。multipart 的普通字段取自 `body`，图片文件取自 `files`：

```json
{
  "method": "POST",
  "path": "/images/edits",
  "encoding": "multipart",
  "headers": {},
  "query": {},
  "body": {"model": "{{model}}", "prompt": "{{prompt}}"},
  "files": [
    {"field": "image[]", "source": "images"},
    {"field": "mask", "source": "mask", "optional": true}
  ]
}
```

`source` 支持 `image`（第一张图）、`images`（整个批次）和 `mask`。`field` 使用供应商规定的字段名；文件统一编码为 PNG。multipart 的 Content-Type 和 boundary 由 HTTP 客户端设置。

## 异步轮询

在模板顶层加入 `poll`，`request` 仍是提交任务的请求；顶层 `response` 用来解析**轮询成功后的最终响应**：

```json
{
  "task_id": "$.data.task_id",
  "request": {"method": "GET", "path": "/tasks/{{task_id}}"},
  "status": "$.data.status",
  "success": ["SUCCEEDED"],
  "failure": ["FAILED", "CANCELLED"],
  "interval": 2,
  "timeout": 600,
  "cancel": {"method": "POST", "path": "/tasks/{{task_id}}/cancel"}
}
```

状态字符串区分大小写。轮询间隔为 0.2–60 秒，总等待时间为 1–7200 秒。`cancel` 可省略；提供时，取消或超时后会尝试调用。调用记录包含任务 ID，方便后续到供应商处查询。当前版本不在 ComfyUI 重启后自动恢复任务。

## 自定义获取模型列表

供应商设置里的 `models_request` 与模板请求使用相同结构；配置 `models_path`、`model_id_path` 和 `model_name_path`，分别指定数组位置及每个条目的 ID/名称。例如返回 `{"items":[{"code":"model-a","title":"A"}]}` 时分别使用 `$.items`、`$.code` 和 `$.title`。

首版执行一次模型列表请求，不自动遍历分页。供应商使用分页时，可在请求 Query 中调整页码/每页数量，依次获取；已有条目会按供应商 + 模型 ID 去重。
