# SuperVideoGenerator 本地介绍页

仓库内可选的静态单页（中/EN），用于本地预览流水线叙事与成片。  
**项目对外介绍以根目录 [README.md](../README.md) 为准，不依赖 GitHub Pages。**

## 本地预览

```powershell
# 在 site 目录
start index.html
```

或从仓库根目录：

```bash
npx serve site
```

## 冒烟检查

```bash
node site/smoke-check.mjs
```

## 素材

| 文件 | 用途 |
|------|------|
| `assets/demo-final.mp4` | 女娲补天成片 |
| `assets/edit-timeline.png` | 剪辑时间轴截图 |
| `assets/wechat-group-qr.png` | 微信群二维码 |

流水线占位可后续替换为：

| 文件 | 用途 |
|------|------|
| `assets/pipeline-chat.png` | 对话步骤 |
| `assets/pipeline-board.png` | 看板 / 分镜 |
| `assets/pipeline-assets.png` | 资产详情 |
