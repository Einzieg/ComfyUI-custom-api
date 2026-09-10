# 出站网络策略（0.2.2 起）

0.2.1 的管理接口允许修改请求目标，缺少出站白名单。在配置接口可达的部署中，调用方可能借服务器访问内网服务。0.2.2 将网络许可与网页可编辑的供应商配置分开；默认拒绝全部出站请求。

服务器管理员在私有目录创建 `network-policy.json`，审核内容后重启 ComfyUI。默认位置是 `ComfyUI/user/__custom_api/network-policy.json`；设置了 `COMFYUI_CUSTOM_API_DIR` 时放在该目录内。文件不能放进可由 HTTP 下载的目录。网页、导入文件、节点和工作流均不能编辑此策略，也不会从旧供应商配置自动生成许可。

下面只是填写格式；只加入自己需要并信任的地址。也可参考 [JSON 示例](network-policy.example.json)。

```json
{
  "allowed_origins": [
    "https://api.openai.com",
    "http://127.0.0.1:11434"
  ],
  "allowed_key_env": ["OPENAI_API_KEY"]
}
```

- 每项是完整来源：协议、精确主机和可选端口，不含 `/v1` 等路径；非默认端口必须填写。不同协议、端口或子域名需要分别批准，不支持通配符。
- API 提交、模型发现、轮询、取消、图片 URL 和每一跳图片重定向都受限制。供应商返回另一个图片 CDN 时，也需由管理员明确批准该来源。
- 域名在实际建连时解析，所有解析结果都必须是公网 IP。通过检查的 IP 直接交给连接器，避免检查后再次解析产生 DNS 重绑定窗口。
- 使用本地模型服务时，明确批准其 IP 字面量和端口，例如 `http://127.0.0.1:11434`。允许显式批准的回环、RFC1918 和 IPv6 ULA 地址；域名解析到这些地址仍会被拒绝。
- 链路本地地址（包括常见云元数据地址）、未指定地址、组播及 IPv6 过渡地址不能获准。非标准数字 IP 表示也会被拒绝。
- 环境密钥只能读取 `allowed_key_env` 列出的名称，不填则不允许从环境变量读密钥。普通 API Key 输入框不依赖此列表。
- 不允许覆盖 Host 或代理路由请求头。显式 HTTP 代理已禁用，以免代理代替客户端解析目标并绕过地址检查；旧供应商如保存了代理，在高级设置中点击“清除已保存的 HTTP 代理”。需要代理网络时，由管理员提供可信的网络隧道。

升级后，已有供应商、模型、模板和独立密钥文件会保留；其地址获准前请求会报明确错误。修改文件需要重启，策略文件格式错误会阻止插件加载。私有策略不包含在工作流、导出配置或安装包内。

白名单控制服务器可以请求的目的地。实例仍按受信任用户共享配置；对外提供 ComfyUI 时继续使用认证和访问控制。

## English

Version 0.2.2 fixes an SSRF boundary in earlier versions: reachable management routes could change the outbound destination without a separate allow-list. Outbound access is now denied by default.

The server owner creates `network-policy.json` in ComfyUI's private `user/__custom_api/` directory, or the directory set by `COMFYUI_CUSTOM_API_DIR`, then restarts ComfyUI. The UI, imports and workflows cannot edit this policy or automatically approve old provider URLs. The JSON example above grants exact origins only: scheme, host and optional port, without an API path. Add only trusted API and image CDN origins that you actually need.

The policy covers execution, discovery, polling, cancellation, image downloads and every image redirect. DNS answers are validated at connection time and those same numeric IPs are passed to the connector. All DNS answers must be public; mixed public/private answers are rejected. Local services require an explicitly approved IP literal and port. Link-local/cloud metadata, multicast, unspecified, IPv6 transition and ambiguous numeric addresses are blocked.

`allowed_key_env` lists the only environment variables available as API credentials. Stored API keys still work without environment variables. Host/proxy routing headers cannot be overridden. Explicit HTTP proxies are disabled because they can resolve destinations outside these checks; clear an old saved proxy from the provider's advanced settings, and use an administrator-managed network tunnel if needed.

Existing provider/model/template data and key files remain intact. Requests fail with an actionable error until the server owner approves their destinations. Policy changes require a restart, and malformed policy files fail closed. The private policy file is excluded from exported configurations and installation packages. This remains a shared, trusted-user ComfyUI instance; external deployments require authentication and access control.
