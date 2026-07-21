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

推荐用 **GitHub Actions** 发布（本仓库已有 `.github/workflows/pages.yml`）：

1. 直接打开：  
   https://github.com/GodyuFF/SuperVideoGenerator/settings/pages  
   （需仓库 **Admin** 权限；侧边栏在 **Code and automation → Pages**，不是往下翻主 Settings 页）
2. **Build and deployment → Source** 选 **GitHub Actions**
3. 回到仓库 **Actions** 页，打开 **Deploy Pages**，点 **Run workflow**（或再 push 一次 `site/`）
4. 成功后访问：`https://godyuff.github.io/SuperVideoGenerator/`

若侧边栏仍无 Pages：确认已登录、账号对该仓库有管理员权限，或用上面的直达链接。

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
