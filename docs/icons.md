# LobeHub 品牌图标

图标网站：[LobeHub Icons](https://icons.lobehub.com/)。

来源：[lobehub/lobe-icons](https://github.com/lobehub/lobe-icons)，官方 npm 包 `@lobehub/icons-static-svg`，固定版本 `1.95.0`。使用 MIT 许可，版权为 Copyright (c) 2023 LobeHub。完整许可随资源保存在 `web/assets/lobehub/LICENSE`。

当前打包 322 个品牌主图标，存在彩色版本时优先使用彩色版本；不包含字标和组合标变体。目录为 `web/assets/lobehub/catalog.json`，每个图标以本地 SVG 资源提供。单色 SVG 通过 CSS mask 显示以适配主题。

供应商配置使用 `lobehub:qwen` 等稳定标识保存选择；后端仅接受本地目录中存在的图标。清空图标选择表示按供应商名称和地址匹配。模型名称/ID 中已识别的品牌可用于模型行和节点显示。自定义上传继续仅接受 PNG、JPEG、WebP。

完整源码中的资源导入命令（PowerShell 7）：

```powershell
$ErrorActionPreference = 'Stop'
npm pack '@lobehub/icons-static-svg@1.95.0' --pack-destination '.dev' --json
if ($LASTEXITCODE -ne 0) { throw '图标包下载失败' }
python scripts/import_icons.py '.dev/lobehub-icons-static-svg-1.95.0.tgz'
if ($LASTEXITCODE -ne 0) { throw '图标导入失败' }
```

该命令只用于维护资源，插件用户无需安装 Node.js 或联网下载图标。
