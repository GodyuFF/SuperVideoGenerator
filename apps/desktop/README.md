# SuperVideoGenerator Desktop (Electron)

本地 Electron 壳：复用 FastAPI + Web UI，剪辑媒体水合通过主进程读盘（IPC），避免浏览器 HTTP 二次拷贝。

## 两种使用方式

| 方式 | 对象 | 说明 |
|------|------|------|
| **开发壳** | 仓库贡献者 | 本机需 Python venv + Node；加载 Vite 开发服务器 |
| **完整安装包** | 终端用户 | 从 [GitHub Releases](https://github.com/GodyuFF/SuperVideoGenerator/releases) 安装；内置嵌入式 Python + 生产前端 |

---

## 开发壳：像 exe 一样启动（推荐）

仓库根目录双击：

- `launch-desktop.vbs` — 静默启动（推荐，无黑框）
- `launch-desktop.bat` — 带日志的控制台启动

之后：

1. 双击 `launch-desktop.vbs`
2. Electron 自动拉起 API + Vite（若未在运行）
3. 打开应用窗口；关闭窗口即退出（并结束本进程拉起的后台服务）

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
.\apps\desktop\packaging\build-desktop.ps1
```

产物：`apps/desktop/dist/SuperVideoGenerator-Setup-{version}-x64.exe`

正式发布：`git tag vX.Y.Z && git push origin vX.Y.Z`（触发 CI 构建 Win + Mac 并上传 Release）。

`electron-builder.yml` 的 `files` 为白名单：主进程 `require("./xxx.cjs")` 的模块必须显式列入，否则安装包会在启动时报 `Cannot find module`。可用 `npm run test:paths`（含 `packagingFiles.test.cjs`）校验。

未签名安装包在部分环境可能被 SmartScreen / Gatekeeper 拦截，属预期行为；可从发布页下载后按系统提示允许运行。macOS 若提示「已损坏」，对 `.app` 执行 `xattr -cr /Applications/SuperVideoGenerator.app` 清除隔离属性后再打开（详见用户手册 FAQ）。

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
