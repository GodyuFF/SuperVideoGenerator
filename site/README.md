# SuperVideoGenerator 展示站

静态单页，演示流水线与成片；中英切换见 `i18n.js`。

## 本地预览

```powershell
start index.html
```

或从仓库根目录：

```bash
npx serve site
```

## GitHub Pages

1. 打开仓库 **Settings → Pages**
2. **Build and deployment → Source**：Deploy from a branch
3. **Branch**：`main`，文件夹 **`/site`**
4. **Save**；几分钟后访问 Settings 中显示的 Pages URL（通常为 `https://godyuff.github.io/SuperVideoGenerator/`）

## 冒烟检查

```bash
node site/smoke-check.mjs
```

校验必需文件存在，且 `index.html` 中所有 `data-i18n` 键均在 `i18n.js` 字典内。

## 替换流水线占位素材

`index.html` 流水线步骤中的截图/录屏占位，后续按以下文件名放入 `assets/`，并在 HTML 中引用同名路径：

| 文件 | 用途 |
|------|------|
| `assets/pipeline-chat.png` | 对话步骤截图 |
| `assets/pipeline-board.png` | 看板 / 分镜截图 |
| `assets/pipeline-assets.png` | 资产详情截图 |

已有成品素材保持现有命名即可，例如 `assets/demo-final.mp4`（成片）、`assets/edit-timeline.png`（剪辑时间轴）。新增或替换后运行 `node site/smoke-check.mjs`，并在 `mustFiles` 中按需追加检查项。
