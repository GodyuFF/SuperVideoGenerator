# Electron 桌面壳（方案 A）设计

> 日期：2026-07-15  
> 状态：已定案（用户确认方案 A 并要求执行）  
> 范围：MVP — 可启动的桌面窗口 + 剪辑媒体本地读盘（跳过 HTTP 水合）

## 目标

在**不重写** `core/` / `apps/api` / 现有 React UI 的前提下，用 Electron 包装本机前后端，使 OpenCut 剪辑媒体水合走 **主进程 `fs.readFile`**，避免浏览器经 `/api/...` 再拷贝一遍大文件。

## 架构

```
Electron Main
  ├── 启动/探测本机 FastAPI (:8000)
  ├── 加载 Renderer：dev→Vite :5173；prod→apps/web/dist
  └── IPC media:readLocal → 解析 DATA_ROOT 下相对路径 → ArrayBuffer

Preload (contextBridge)
  └── window.svfDesktop = { isDesktop, readLocalMedia(...) }

Renderer (现有 apps/web)
  └── hydrateSvfMediaFiles：若 isDesktop 则 IPC 读盘，否则保持 fetch
```

## 非目标（本 MVP 不做）

- 完整 NSIS/Squirrel 安装包、自动更新、PyInstaller 单文件捆绑 Python/Node（体积与签名另议）
- Tauri / 原生 UI 重写
- 取消 REST/WS（桌面仍走 localhost API，领域逻辑不变）
- 图片看板 `<img src>` 改本地协议（剪辑水合优先）

## 像 exe 一样的日常启动（已实现）

- `create-desktop-shortcut.bat` → 桌面 `SuperVideoGenerator.lnk`（图标：`apps/desktop/icon.ico` 猫头鹰取景器品牌标）
- 双击走 `launch-desktop.vbs`（无控制台）；`main.cjs` 内经 `devServers.cjs` 探测并静默拉起 API/Vite；窗口 `BrowserWindow.icon` 同套 ICO
- 关闭 Electron 窗口时，仅结束**本进程拉起**的子服务（外部分已运行的 API/Vite 不杀）
- `SVG_DESKTOP_SKIP_SERVERS=1` 可关闭自动拉起

完整商业级安装包见后续里程碑设计：[`2026-07-17-desktop-installer-design.md`](./2026-07-17-desktop-installer-design.md)。当前交付是「桌面快捷方式级体验」。

## 媒体路径解析

支持输入：

- `/api/projects/{pid}/scripts/{sid}/assets/media/{file}`
- `/api/projects/{pid}/scripts/{sid}/assets/exports/{file}`
- `projects/{pid}/scripts/{sid}/assets/media/{file}`

映射到：`{repoOrDataRoot}/data/projects/...`（`SVG_DATA_ROOT` 可覆盖）。

路径必须规范化并约束在 `data/` 内，防路径穿越。

## 安全

- `contextIsolation: true`，`nodeIntegration: false`
- 仅暴露白名单 IPC
- `media:readLocal` 拒绝 `data/` 外路径

## 启动与二进制安装（实现约束）

- `dev-desktop.bat` / `apps/desktop/npm start` 经 `ensure-electron.cjs` 安装 **Electron 官方 zip 二进制** 到 `%LOCALAPPDATA%\SuperVideoGenerator\electron\v{version}\`（可用 `SVG_ELECTRON_HOME` 覆盖），**不依赖** 工作区内残缺的 `node_modules/electron`（Windows 上 Cursor/索引常锁住 `default_app.asar`，导致 `ECONNRESET` / `EBUSY` 后安装半残、窗口一闪退出）。
- 默认 `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`；`DESKTOP_WEB_URL` 固定 `http://localhost:5173`（见 `docs/superpowers/reference/i18n.md`）。
- Vite 开发服须 `server.host: true`（`apps/web/vite.config.ts`）：默认仅绑 `::1` 时 Electron 窗口可能空白；主进程在 `did-fail-load` 时可见并重试加载。

## 验收

1. `dev-desktop.bat`（或 `cd apps/desktop && npm start`）打开窗口并加载工作台
2. 桌面下打开剪辑 Tab，水合不再对本机媒体发大体积 `fetch`（devtools Network 可见），改走 IPC
3. 浏览器模式行为不变（无 `svfDesktop` 时仍 HTTP 水合）
4. 相关单测通过；`docs/superpowers/reference/code-design-plan.md` 仓库结构含 `apps/desktop`
