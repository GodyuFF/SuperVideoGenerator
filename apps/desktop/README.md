# SuperVideoGenerator Desktop (Electron)

本地 Electron 壳：复用 FastAPI + Web UI，剪辑媒体水合通过主进程读盘（IPC），避免浏览器 HTTP 二次拷贝。

## 两种使用方式

| 方式 | 对象 | 说明 |
|------|------|------|
| **开发壳** | 仓库贡献者 | 本机需 Python venv + Node；加载 Vite 开发服务器 |
| **完整安装包** | 终端用户 | 从 [GitHub Releases](https://github.com/GodyuFF/SuperVideoGenerator/releases) 安装；内置嵌入式 Python + 生产前端 |

发版、未签名分发与本地打包见 [`docs/desktop-packaging.md`](../../docs/desktop-packaging.md)。

---

## 开发壳：像 exe 一样启动（推荐）

仓库根目录执行一次：

```bat
create-desktop-shortcut.bat
```

桌面会出现 **SuperVideoGenerator** 快捷方式（圆软小夜枭图标，与窗口/浏览器标签一致）。之后：

1. 双击该图标（内部走 `launch-desktop.vbs`，无黑框）
2. Electron 自动拉起 API + Vite（若未在运行）
3. 打开应用窗口；关闭窗口即退出（并结束本进程拉起的后台服务）

也可直接双击：

- `launch-desktop.vbs` — 静默启动（推荐）
- `launch-desktop.bat` / `dev-desktop.bat` — 带日志的控制台启动

> 开发壳**不是**离线安装包：不捆绑 Python/Node，依赖仓库与本机环境。

## 开发壳：手动启动

```bat
cd apps\desktop
set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
npm start
```

主进程会：

1. **去掉默认菜单栏**（File / Edit / View…）
2. 探测 `:8000` / `:5173`，缺失时静默拉起（Windows 下 Vite 经 `cmd /c npm`）
3. 服务就绪后再加载 `http://localhost:5173`；失败时窗口内显示错误与日志路径

日志：`%LOCALAPPDATA%\SuperVideoGenerator\logs\desktop-servers.log`

---

## 完整安装包：本地构建

维护者在 Windows 上打未签名 NSIS 安装包：

```powershell
# 仓库根目录
.\scripts\packaging\build-desktop.ps1
```

产物：`apps/desktop/dist/SuperVideoGenerator-Setup-{version}-x64.exe`

正式发布：`git tag vX.Y.Z && git push origin vX.Y.Z`（触发 CI 构建 Win + Mac 并上传 Release）。

---

## 环境变量（开发壳）

| 变量 | 含义 | 默认 |
|------|------|------|
| `DESKTOP_WEB_URL` | 渲染进程加载地址 | `http://localhost:5173` |
| `SVG_DATA_ROOT` / `DESKTOP_DATA_ROOT` | 媒体 `data/` 根目录 | `<repo>/data` |
| `ELECTRON_MIRROR` | Electron 二进制镜像前缀 | `https://npmmirror.com/mirrors/electron/` |
| `SVG_ELECTRON_HOME` | 二进制安装根目录 | `%LOCALAPPDATA%\SuperVideoGenerator\electron` |
| `SVG_DESKTOP_SKIP_SERVERS` | `1` 时不自动拉起 API/Vite | 未设置 |

打包版使用用户目录下的 `data/`（见 `userDataPaths.cjs`），API 与 UI 同源 `http://127.0.0.1:8000`。

---

## 验证

```bat
cd apps\desktop
npm run test:paths
```

---

## 设计文档

- [`docs/superpowers/specs/2026-07-17-desktop-installer-design.md`](../../docs/superpowers/specs/2026-07-17-desktop-installer-design.md) — 完整安装包
- [`docs/superpowers/specs/2026-07-15-electron-desktop-shell-design.md`](../../docs/superpowers/specs/2026-07-15-electron-desktop-shell-design.md) — 开发壳
- [`docs/desktop-packaging.md`](../../docs/desktop-packaging.md) — 发版与用户安装说明
