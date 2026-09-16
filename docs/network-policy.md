# 网络模式与管理访问

0.3.0 提供默认模式和严格模式。首次安装使用默认模式，无需创建策略文件即可调用公网 API。

## 默认模式

- 公网 HTTP(S) API、模型发现、任务轮询和公网图片 CDN 无需逐个批准。
- 访问本地或局域网模型时，在供应商页面填写 IP 地址，例如 `http://127.0.0.1:11434/v1`，点击“允许访问此本地服务”并确认。授权只覆盖该协议、IP 和端口，不包含其他端口。
- 本地授权独立保存，不由导入配置、工作流或模板授予。需要多个本地服务时可在“网络与访问”中查看、添加或撤销。
- 本地服务使用 IP 字面量，不使用 `localhost` 或内网域名；域名解析到私网或混合公网/私网地址时仍会拒绝连接。

## 严格模式

在管理面板的“网络与访问”中选择“严格模式”，填写地址白名单并点击“保存网络设置”。仅批准的来源可被访问，包括 API、轮询、取消和图片 CDN。每项包含协议、精确主机和端口，不含路径或通配符。

严格模式只使用自己的白名单；默认模式的本地服务授权不会额外放行。严格模式下的本地 IP 也需列入白名单，可在供应商页面单独授权。特殊地址无法批准。

两种模式都可以通过面板配置，无需手动编辑文件或重启。保存对后续请求生效，不强制中断已建立的连接或清除已生成的缓存结果。

## 管理会话

仅监听回环地址的 ComfyUI，在本机通过 `127.0.0.1`、`localhost` 或 `::1` 打开时，管理面板自动建立会话。初始化检查请求来源、实际连接对端与 Host，不信任转发头。

使用 `--listen 0.0.0.0`、局域网 IP 或其他非回环监听时，网页需要解锁 API 管理：读取服务器私有目录 `user/__custom_api/management-access.json` 中的 `pairing_code`，在面板中输入。自定义私有目录由 `COMFYUI_CUSTOM_API_DIR` 指定。该文件在插件加载时自动生成，持有码者拥有插件完整管理权限，包括修改网络模式和授权本地服务。

配对码不会写进 URL、工作流或配置导出；浏览器仅在内存中保存运行期会话。刷新远程页面需要重新配对，服务器重启会使已有会话失效。需要轮换配对码时，关闭 ComfyUI，删除私有目录内的 `management-access.json` 后重新启动。

远程管理请使用 HTTPS 或可信隧道。反向代理不自动授予本机会话，需要配对。插件的配对只保护插件管理接口，不替代 ComfyUI 整体认证，也不提供多租户隔离。可执行本地代码或控制同源插件的用户属于本机信任边界。

## 始终保留的限制

- DNS 在实际连接时校验，并将已验证数字 IP 交给连接器，避免第二次解析。
- 云元数据、链路本地、未指定、组播、保留及 IPv6 过渡地址始终禁止。非标准数字 IP 表示也会拒绝。
- 图片下载及每次重定向都校验目标；跨源下载不携带供应商密钥。
- 禁止覆盖 Host 和代理路由头，禁用显式 HTTP 代理及环境代理，避免代理绕过目标检查。需要代理网络时使用管理员管理的可信网络隧道。
- 从环境变量读取密钥时，在“网络与访问”中单独批准变量名。直接填写 API Key 无需此设置。

策略保存在私有目录的 `network-policy.json`，不随普通配置导入导出。文件格式错误会阻止插件加载。下面是严格模式示例；默认模式不需要文件：

```json
{
  "mode": "strict",
  "allowed_origins": ["https://api.example.com", "https://images.example.com", "http://127.0.0.1:11434"],
  "local_origins": [],
  "allowed_key_env": ["MY_PROVIDER_API_KEY"]
}
```

开发期不提供旧版迁移或兼容模式。默认模式接受任意公网目的地，比严格模式宽松；共享部署可按需要选择严格模式。

## English

Version 0.3.0 has two modes. **Default** allows public HTTP(S) APIs and image CDNs without an origin allow-list. Local services need an explicit grant: enter a literal IP URL in provider settings, click **Authorize this local service**, and confirm. Grants cover exactly the scheme, IP and port. DNS names resolving to private addresses are still blocked.

**Strict** uses only its origin allow-list, including API, polling, cancellation, local IP services and image download destinations. Default-mode local grants do not bypass strict mode. Configure either mode in **Network & access**. Changes apply to subsequent requests without a restart; existing connections and cached results are not forcibly cleared.

Loopback-only ComfyUI listeners automatically establish a management session for same-origin local browsers. Non-loopback listeners require the `pairing_code` from the server's private `user/__custom_api/management-access.json` (or `COMFYUI_CUSTOM_API_DIR`). The file is generated on plugin startup. A pairing code grants full plugin administration. Sessions stay in browser memory and expire on server restart; remote page refreshes require pairing again. To rotate the code, stop ComfyUI, delete that private file, then restart. Reverse-proxy access requires pairing. Use HTTPS or a trusted tunnel remotely, and protect ComfyUI itself separately.

DNS pinning, private/mixed DNS answer rejection, redirect checks, cross-origin credential isolation, special-address blocking and proxy restrictions remain active in both modes. API key environment-variable names need separate approval in Network & access; pasted provider keys do not. Policies and management credentials stay outside normal config imports/exports. Malformed policy files fail closed. There is no legacy compatibility mode.
