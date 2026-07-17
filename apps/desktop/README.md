# SuperVideoGenerator Desktop (Electron)

本地 Electron 壳：复用现有 FastAPI + Vite UI，剪辑媒体水合通过主进程读盘（IPC），避免浏览器 HTTP 二次拷贝。

**日常使用像 exe：双击桌面图标即可**，不必开浏览器，也不必盯着多个黑色命令行窗口。

## 像 exe 一样启动（推荐）

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

> 这不是安装包级单文件 `.exe`（不捆绑 Python/Node）。本质是「一键启动器 + Electron 窗口」。完整安装包仍属后续里程碑。

## 手动开发启动

```bat
:: 终端：仍可用
cd apps\desktop
set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
npm start
```

主进程会：

1. **去掉默认菜单栏**（File / Edit / View…）
2. 探测 `:8000` / `:5173`，缺失时静默拉起（Windows 下 Vite 经 `cmd /c npm`）
3. 服务就绪后再加载 `http://localhost:5173`；失败时窗口内显示错误与日志路径

日志：`%LOCALAPPDATA%\SuperVideoGenerator\logs\desktop-servers.log`

环境变量：

| 变量 | 含义 | 默认 |
|------|------|------|
| `DESKTOP_WEB_URL` | 渲染进程加载地址 | `http://localhost:5173` |
| `SVG_DATA_ROOT` / `DESKTOP_DATA_ROOT` | 媒体 `data/` 根目录 | `<repo>/data` |
| `ELECTRON_MIRROR` | Electron 二进制镜像前缀 | `https://npmmirror.com/mirrors/electron/` |
| `SVG_ELECTRON_HOME` | 二进制安装根目录 | `%LOCALAPPDATA%\SuperVideoGenerator\electron` |
| `SVG_DESKTOP_SKIP_SERVERS` | `1` 时不自动拉起 API/Vite | 未设置 |

## 验证

```bat
cd apps\desktop
npm run test:paths
```

## 设计文档

- [`docs/superpowers/specs/2026-07-15-electron-desktop-shell-design.md`](../../docs/superpowers/specs/2026-07-15-electron-desktop-shell-design.md)
