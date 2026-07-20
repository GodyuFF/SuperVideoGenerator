# Desktop Full Installer (Win + Mac) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付未签名的完整离线安装包（Electron + 嵌入式 Python/全量依赖含 torch/WhisperX + 生产前端），经 GitHub Actions 产出 Win NSIS 与 Mac DMG/ZIP，并支持 electron-updater 自动更新。

**Architecture:** 打包后 Electron `app.isPackaged` 走 `prodServers.cjs`，从 `resources/runtime/python` 拉起 uvicorn（`127.0.0.1:8000`），FastAPI 经 `desktop_static` 托管 `runtime/web`；用户数据与 `.env` 落在 OS 用户目录。CI 矩阵构建三平台产物上传 GitHub Releases；默认不签名。

**Tech Stack:** Electron 33+、electron-builder、electron-updater、python-build-standalone CPython 3.11、FastAPI StaticFiles、GitHub Actions、PowerShell/Bash 打包脚本。

**Spec:** [`docs/superpowers/specs/2026-07-17-desktop-installer-design.md`](../specs/2026-07-17-desktop-installer-design.md)

## Global Constraints

- 默认**不签名、不公证**；缺少证书不得导致 CI 失败。
- 默认包**必须**含 torch / torchaudio / WhisperX；安装失败即 fail，禁止静默删依赖。
- 生产 API 仅绑 `127.0.0.1:8000`；占用则报错提示，不换端口。
- 健康探测用已有 `GET /health`。
- 嵌入式 Python：python-build-standalone CPython 3.11.x（版本写在 `scripts/packaging/python-version.txt`）。
- Mac：首装 DMG + 更新通道 ZIP（同 arch）。
- 静态挂载：`apps/api/desktop_static.py`，由 `main.py` 条件启用。
- 禁止在 `core/` / `apps/` 写 mock；测试 mock 仅在 `tests/`。
- 新类/函数中文 docstring / JSDoc；完成后同步文档（Task 9）。
- 开发路径（`devServers` + Vite）保持可用；安装包路径与之分支隔离。

## File Structure

| 路径 | 职责 |
|------|------|
| `apps/api/desktop_static.py` | 解析 `SVG_DESKTOP_WEB_ROOT`，挂载 StaticFiles + SPA fallback |
| `apps/api/main.py` | 调用 `mount_desktop_static_if_configured(app)` |
| `apps/desktop/userDataPaths.cjs` | 解析用户 data/logs/.env 根目录 |
| `apps/desktop/prodServers.cjs` | 打包模式拉起/停止嵌入式 API |
| `apps/desktop/main.cjs` | `isPackaged` 分支；updater 注册；DATA_ROOT 指向用户目录 |
| `apps/desktop/preload.cjs` | 暴露 version / checkForUpdates / quitAndInstall |
| `apps/desktop/updater.cjs` | electron-updater 封装 |
| `apps/desktop/electron-builder.yml` | NSIS/DMG/ZIP、extraResources、forceCodeSigning: false |
| `apps/desktop/package.json` | electron-builder / electron-updater 依赖与 scripts |
| `apps/desktop/runtime/` | 构建产物（gitignore，不入库） |
| `scripts/packaging/python-version.txt` | 锁定 python-build-standalone 版本标签 |
| `scripts/packaging/api_boot.py` | 设置 sys.path / 环境后起 uvicorn |
| `scripts/packaging/prepare-runtime.ps1` | Win：下载 Python、pip install、拷贝 web |
| `scripts/packaging/prepare-runtime.sh` | Mac CI 同逻辑 |
| `scripts/packaging/build-desktop.ps1` / `.sh` | prepare + electron-builder |
| `requirements-desktop.txt` | 生产依赖（无 pytest） |
| `.github/workflows/release-desktop.yml` | 矩阵构建 + Release |
| `apps/web/src/pages/AiSettingsPage.tsx` | 桌面「检查更新」区块 |
| `apps/web/src/desktop/types.ts` / `svfDesktop.ts` | 更新相关类型与 helper |
| `tests/unit/test_desktop_static.py` | 静态挂载与 SPA |
| `apps/desktop/prodServers.test.cjs` / `userDataPaths.test.cjs` | Node 单测 |
| `docs/desktop-packaging.md` | 发版与首次打开说明 |

---

### Task 1: FastAPI 生产静态托管

**Files:**
- Create: `apps/api/desktop_static.py`
- Modify: `apps/api/main.py`（在 router 注册之后调用挂载）
- Test: `tests/unit/test_desktop_static.py`

**Interfaces:**
- Produces:
  - `resolve_desktop_web_root(env: Mapping[str, str] | None = None) -> Path | None`
  - `mount_desktop_static_if_configured(app: FastAPI, env: Mapping[str, str] | None = None) -> bool`
- Consumes: 环境变量 `SVG_DESKTOP_WEB_ROOT`（绝对路径，指向含 `index.html` 的目录）

- [ ] **Step 1: 写失败单测**

```python
# tests/unit/test_desktop_static.py
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.desktop_static import (
    mount_desktop_static_if_configured,
    resolve_desktop_web_root,
)


def test_resolve_missing_env_returns_none(monkeypatch, tmp_path):
    monkeypatch.delenv("SVG_DESKTOP_WEB_ROOT", raising=False)
    assert resolve_desktop_web_root({}) is None


def test_mount_serves_index_and_spa_fallback(monkeypatch, tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    (web / "assets").mkdir()
    (web / "assets" / "a.js").write_text("1", encoding="utf-8")
    monkeypatch.setenv("SVG_DESKTOP_WEB_ROOT", str(web))

    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    assert mount_desktop_static_if_configured(app) is True
    client = TestClient(app)
    assert client.get("/api/ping").json() == {"ok": True}
    assert "ok" in client.get("/").text
    assert client.get("/assets/a.js").text == "1"
    # SPA：未知前端路由回 index
    assert "ok" in client.get("/workbench/foo").text
```

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/unit/test_desktop_static.py -v`  
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `desktop_static.py` 并在 `main.py` 挂载**

```python
# apps/api/desktop_static.py
"""桌面生产包：将 Vite dist 挂到 FastAPI 根路径。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
from starlette.routing import Mount


def resolve_desktop_web_root(env: Mapping[str, str] | None = None) -> Path | None:
    """读取 SVG_DESKTOP_WEB_ROOT；目录须含 index.html。"""
    raw = (env or os.environ).get("SVG_DESKTOP_WEB_ROOT", "").strip()
    if not raw:
        return None
    root = Path(raw).resolve()
    if not (root / "index.html").is_file():
        return None
    return root


def mount_desktop_static_if_configured(
    app: FastAPI, env: Mapping[str, str] | None = None
) -> bool:
    """若配置了有效 web 根目录则挂载静态与 SPA fallback。"""
    root = resolve_desktop_web_root(env)
    if root is None:
        return False

    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="desktop_assets")

    index = root / "index.html"

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """非 API 路径回退到 index.html（API 路由优先匹配）。"""
        candidate = root / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    return True
```

在 `apps/api/main.py` 的 `include_router` 全部完成之后、`exception_handler` 之前插入：

```python
from apps.api.desktop_static import mount_desktop_static_if_configured

mount_desktop_static_if_configured(app)
```

注意：SPA catch-all 必须在所有 `/api`、`/ws`、`/health` 路由**之后**注册，否则会抢路由。若 `/{full_path:path}` 与现有路由冲突，改为只在 `mount_desktop_static_if_configured` 内用自定义 `StaticFiles` + 无路由冲突的 middleware；实现时以 TestClient 测 `/health` 仍返回 `{"status":"ok"}` 为准。

- [ ] **Step 4: 跑测通过 + 全量回归**

Run: `pytest tests/unit/test_desktop_static.py -v && pytest tests/ -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/desktop_static.py apps/api/main.py tests/unit/test_desktop_static.py
git commit -m "$(cat <<'EOF'
feat(api): mount Vite dist for packaged desktop

EOF
)"
```

---

### Task 2: 用户数据路径 + `prodServers`

**Files:**
- Create: `apps/desktop/userDataPaths.cjs`
- Create: `apps/desktop/userDataPaths.test.cjs`
- Create: `apps/desktop/prodServers.cjs`
- Create: `apps/desktop/prodServers.test.cjs`
- Modify: `apps/desktop/package.json`（`test:paths` 加入新测试）

**Interfaces:**
- Produces:
  - `resolveUserDataRoot(env, platform, homedir, localAppData) -> string`
  - `resolveRuntimeRoot(resourcesPath) -> string`（`path.join(resourcesPath, "runtime")`）
  - `resolveEmbeddedPython(runtimeRoot, platform) -> string`（Win: `python/python.exe`；Unix: `python/bin/python3`）
  - `ensureProdApi(runtimeRoot, userDataRoot, options?) -> Promise<{ stop, apiReady, logPath, webUrl }>`
  - `webUrl` 固定 `http://127.0.0.1:8000/`
  - probe：`http://127.0.0.1:8000/health`

- [ ] **Step 1: 写失败 Node 测试**

```javascript
// apps/desktop/userDataPaths.test.cjs
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { resolveUserDataRoot } = require("./userDataPaths.cjs");

describe("resolveUserDataRoot", () => {
  it("Windows 使用 LOCALAPPDATA/SuperVideoGenerator", () => {
    const root = resolveUserDataRoot(
      {},
      "win32",
      "C:\\Users\\x",
      "C:\\Users\\x\\AppData\\Local",
    );
    assert.equal(
      root,
      path.join("C:\\Users\\x\\AppData\\Local", "SuperVideoGenerator"),
    );
  });

  it("macOS 使用 Application Support", () => {
    const root = resolveUserDataRoot({}, "darwin", "/Users/x", "");
    assert.equal(
      root,
      path.join("/Users/x", "Library", "Application Support", "SuperVideoGenerator"),
    );
  });
});
```

```javascript
// apps/desktop/prodServers.test.cjs
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const {
  resolveRuntimeRoot,
  resolveEmbeddedPython,
} = require("./prodServers.cjs");

describe("prodServers paths", () => {
  it("runtime 在 resources/runtime", () => {
    assert.equal(
      resolveRuntimeRoot("/app/resources"),
      path.join("/app/resources", "runtime"),
    );
  });

  it("Win python 路径", () => {
    const p = resolveEmbeddedPython(path.join("R", "runtime"), "win32");
    assert.ok(p.endsWith(path.join("python", "python.exe")));
  });
});
```

- [ ] **Step 2: 跑测确认失败**

Run: `cd apps/desktop && node --test userDataPaths.test.cjs prodServers.test.cjs`  
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现路径与 `ensureProdApi`**

`userDataPaths.cjs`：按上表解析；支持 `SVG_USER_DATA_ROOT` 覆盖。

`prodServers.cjs` 要点：

```javascript
/**
 * 打包模式：用嵌入式 Python 启动 API（托管静态前端）。
 * @param {string} runtimeRoot
 * @param {string} userDataRoot
 * @param {{ skip?: boolean }} [options]
 */
async function ensureProdApi(runtimeRoot, userDataRoot, options = {}) {
  const logPath = /* 与 devServers 类似，写 userDataRoot/logs/desktop-servers.log */;
  const dataRoot = path.join(userDataRoot, "data");
  fs.mkdirSync(dataRoot, { recursive: true });
  fs.mkdirSync(path.join(userDataRoot, "logs"), { recursive: true });

  const python = resolveEmbeddedPython(runtimeRoot, process.platform);
  const webRoot = path.join(runtimeRoot, "web");
  const boot = path.join(runtimeRoot, "api_boot.py");
  const env = {
    ...process.env,
    SVG_DATA_ROOT: dataRoot,
    SVG_DESKTOP_WEB_ROOT: webRoot,
    SVG_DESKTOP_PACKAGED: "1",
    // 若用户目录存在 .env，由 api_boot / pydantic 加载；此处不注入密钥
  };
  // 若 8000 已被占用：probe /health 成功则复用且 stop 为空操作；
  // 否则 throw new Error("端口 8000 已被占用...")
  // spawn: python api_boot.py 或 python -m uvicorn，cwd = runtimeRoot 上一级需含 apps/core —
  // **锁定**：runtime 内同时放置 `app_src/` 或把仓库 `apps`+`core` 拷入 runtime/src，
  // PYTHONPATH=runtime/src（prepare-runtime 负责拷贝）。
  // 本任务实现 spawn + probe；拷贝布局在 Task 4 固定为：
  //   runtime/src/{apps,core,...}  PYTHONPATH=runtime/src
}
```

复用 `devServers.cjs` 导出的 `probeUrl` / `waitForAnyUrl` / `spawnHidden`（可从 `devServers` require，避免复制杀进程逻辑）。

- [ ] **Step 4: 跑测通过**

Run: `cd apps/desktop && npm run test:paths`  
Expected: PASS（含新文件）

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/userDataPaths.cjs apps/desktop/userDataPaths.test.cjs \
  apps/desktop/prodServers.cjs apps/desktop/prodServers.test.cjs apps/desktop/package.json
git commit -m "$(cat <<'EOF'
feat(desktop): add packaged API launcher and user data paths

EOF
)"
```

---

### Task 3: `main.cjs` / preload 接入打包模式

**Files:**
- Modify: `apps/desktop/main.cjs`
- Modify: `apps/desktop/preload.cjs`
- Modify: `apps/web/src/desktop/types.ts`
- Modify: `apps/web/src/desktop/svfDesktop.ts`

**Interfaces:**
- Produces: 打包时 `WEB_URL=http://127.0.0.1:8000/`；`DATA_ROOT=userData/data`；IPC `desktop:getInfo` 增加 `packaged: boolean`、`appVersion: string`

- [ ] **Step 1: 改 `main.cjs` boot 分支**

伪代码（写入真实文件时保持现有 splash / errorPage）：

```javascript
const { resolveUserDataRoot } = require("./userDataPaths.cjs");
const { ensureProdApi, resolveRuntimeRoot } = require("./prodServers.cjs");

const USER_DATA_ROOT = resolveUserDataRoot(
  process.env,
  process.platform,
  require("os").homedir(),
  process.env.LOCALAPPDATA || "",
);
const DATA_ROOT = process.env.SVG_DATA_ROOT
  ? path.resolve(process.env.SVG_DATA_ROOT)
  : path.join(USER_DATA_ROOT, "data");

async function boot() {
  registerMediaIpc();
  const win = createWindow();
  void win.loadFile(SPLASH_BOOT_HTML);

  try {
    if (app.isPackaged) {
      const runtimeRoot = resolveRuntimeRoot(process.resourcesPath);
      managedServers = await ensureProdApi(runtimeRoot, USER_DATA_ROOT);
      const url = "http://127.0.0.1:8000/";
      if (!managedServers.apiReady) {
        void win.loadURL(/* errorPage 含 logPath */);
        return;
      }
      void win.loadURL(url);
      return;
    }
    // 现有 ensureDevServers 路径不变
    managedServers = await ensureDevServers(REPO_ROOT, { webUrl: WEB_URL });
    ...
  } catch (err) { ... }
}
```

- [ ] **Step 2: 扩展 preload `getInfo` 类型**

```javascript
// preload.cjs 增加字段（getInfo 仍走 desktop:getInfo）
getVersion: () => ipcRenderer.invoke("desktop:getVersion"),
```

`main.cjs`：

```javascript
ipcMain.handle("desktop:getVersion", async () => app.getVersion());
ipcMain.handle("desktop:getInfo", async () => ({
  isDesktop: true,
  packaged: app.isPackaged,
  dataRoot: DATA_ROOT,
  webUrl: app.isPackaged ? "http://127.0.0.1:8000/" : WEB_URL,
  repoRoot: app.isPackaged ? "" : REPO_ROOT,
  appVersion: app.getVersion(),
}));
```

同步 `apps/web/src/desktop/types.ts` 字段。

- [ ] **Step 3: 开发模式冒烟**

Run: `cd apps/desktop && npm run test:paths`  
手动：`dev-desktop.bat` 仍能打开 Vite 工作台（不回归）。

- [ ] **Step 4: Commit**

```bash
git add apps/desktop/main.cjs apps/desktop/preload.cjs \
  apps/web/src/desktop/types.ts apps/web/src/desktop/svfDesktop.ts
git commit -m "$(cat <<'EOF'
feat(desktop): boot embedded API when Electron is packaged

EOF
)"
```

---

### Task 4: `requirements-desktop` + prepare-runtime + `api_boot`

**Files:**
- Create: `requirements-desktop.txt`
- Create: `scripts/packaging/python-version.txt`
- Create: `scripts/packaging/api_boot.py`
- Create: `scripts/packaging/prepare-runtime.ps1`
- Create: `scripts/packaging/prepare-runtime.sh`
- Modify: `.gitignore`（忽略 `apps/desktop/runtime/`、`apps/desktop/dist/`）

**Interfaces:**
- Produces 目录布局：

```
apps/desktop/runtime/
  python/          # 嵌入式解释器
  web/             # apps/web/dist 拷贝
  src/             # 拷贝 core/、apps/api/、apps/（及 API 所需包路径）
  api_boot.py
  requirements.lock
```

- `PYTHONPATH=<runtime>/src`，工作目录任意；`api_boot` 执行：
  `uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000)`

- [ ] **Step 1: 写 `requirements-desktop.txt`**

从 `requirements.txt` 复制并删除：

```
pytest>=8.0
pytest-asyncio>=0.23
```

保留 torch / torchaudio / whisperx / 其余生产行。

- [ ] **Step 2: 锁定 Python 版本文件**

`scripts/packaging/python-version.txt` 单行示例（实现时查 astral 最新 3.11 install_only 标签并写入真实值）：

```
cpython-3.11.11+20250317
```

注释写在 `prepare-runtime.ps1` 头部：从  
`https://github.com/astral-sh/python-build-standalone/releases/download/<tag>/`  
下载对应 `x86_64-pc-windows-msvc` / `aarch64-apple-darwin` / `x86_64-apple-darwin` 的 `install_only.tar.gz`。

- [ ] **Step 3: 实现 `api_boot.py`**

```python
"""桌面安装包 API 入口：配置路径后启动 uvicorn。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    """将 runtime/src 加入 path 并监听 127.0.0.1:8000。"""
    runtime = Path(__file__).resolve().parent
    src = runtime / "src"
    sys.path.insert(0, str(src))
    os.environ.setdefault("SVG_DESKTOP_PACKAGED", "1")
    web = runtime / "web"
    if web.is_dir():
        os.environ.setdefault("SVG_DESKTOP_WEB_ROOT", str(web))

    import uvicorn

    uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 实现 `prepare-runtime.ps1`（Win）核心步骤**

脚本参数：`-RepoRoot`、`-OutDir`（默认 `apps/desktop/runtime`）、`-SkipTorch` **禁止默认使用**（仅本地快速调试可显式传入；CI 与正式包不得传）。

步骤：
1. 读取 `python-version.txt`，下载并解压到 `$OutDir/python`
2. `$py = Join-Path $OutDir "python/python.exe"`；`& $py -m ensurepip`；升级 pip
3. `pip install -r requirements-desktop.txt`（Win 额外：`pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124` 若主 requirements 未拉到 CUDA wheel——实现时以「能 import whisperx」为准，写进脚本注释）
4. 构建前端：`Push-Location apps/web; npm ci; npm run build; Pop-Location`
5. 拷贝 `apps/web/dist` → `$OutDir/web`
6. 拷贝 `core`、`apps`（至少 `apps/api` 与其导入链；简单做法：**整个 `core/` + `apps/`**）→ `$OutDir/src/`
7. 拷贝 `api_boot.py`；`pip freeze > requirements.lock`

`prepare-runtime.sh` 镜像上述逻辑（Mac 用官方 torch 默认索引）。

- [ ] **Step 5: 更新 `.gitignore`**

```
apps/desktop/runtime/
apps/desktop/dist/
```

- [ ] **Step 6: 本地试跑 prepare（可长时间）**

Run: `powershell -File scripts/packaging/prepare-runtime.ps1`  
Expected: `apps/desktop/runtime/web/index.html` 与 `python/python.exe` 存在；  
`.\apps\desktop\runtime\python\python.exe apps\desktop\runtime\api_boot.py` 后 `curl http://127.0.0.1:8000/health` → `{"status":"ok"}`

- [ ] **Step 7: Commit**

```bash
git add requirements-desktop.txt scripts/packaging/ .gitignore
git commit -m "$(cat <<'EOF'
feat(packaging): add desktop runtime prepare scripts and deps

EOF
)"
```

---

### Task 5: electron-builder 本地 Windows 包（P0/P1）

**Files:**
- Create: `apps/desktop/electron-builder.yml`
- Create: `scripts/packaging/build-desktop.ps1`
- Create: `scripts/packaging/build-desktop.sh`
- Modify: `apps/desktop/package.json`

**Interfaces:**
- `npm run dist` → 调用 electron-builder；产物在 `apps/desktop/dist/`
- `extraResources`：`runtime/**` → 安装后 `resources/runtime`

- [ ] **Step 1: 写 `electron-builder.yml`**

```yaml
appId: com.supervideogenerator.desktop
productName: SuperVideoGenerator
copyright: Copyright © SuperVideoGenerator contributors
directories:
  output: dist
  buildResources: build
files:
  - main.cjs
  - preload.cjs
  - prodServers.cjs
  - userDataPaths.cjs
  - mediaPath.cjs
  - splash-boot.html
  - icon.ico
  - icon.png
  - package.json
extraResources:
  - from: runtime
    to: runtime
    filter:
      - "**/*"
forceCodeSigning: false
win:
  target:
    - target: nsis
      arch:
        - x64
  icon: icon.ico
  artifactName: SuperVideoGenerator-Setup-${version}-x64.${ext}
nsis:
  oneClick: false
  allowToChangeInstallationDirectory: true
  createDesktopShortcut: true
  createStartMenuShortcut: true
  deleteAppDataOnUninstall: false
mac:
  target:
    - target: dmg
      arch:
        - x64
        - arm64
    - target: zip
      arch:
        - x64
        - arm64
  category: public.app-category.video
  identity: null
  hardenedRuntime: false
  gatekeeperAssess: false
  artifactName: SuperVideoGenerator-${version}-${arch}.${ext}
dmg:
  artifactName: SuperVideoGenerator-${version}-${arch}.dmg
publish:
  provider: github
  releaseType: release
```

- [ ] **Step 2: 更新 `package.json`**

```json
{
  "name": "super-video-generator-desktop",
  "version": "0.1.0",
  "main": "main.cjs",
  "scripts": {
    "start": "node start-electron.cjs",
    "ensure-electron": "node ensure-electron.cjs",
    "test:paths": "node --test mediaPath.test.cjs ensure-electron.test.cjs devServers.test.cjs userDataPaths.test.cjs prodServers.test.cjs",
    "pack": "electron-builder --dir",
    "dist": "electron-builder --publish never"
  },
  "devDependencies": {
    "electron": "^33.2.0",
    "electron-builder": "^25.1.8"
  },
  "dependencies": {
    "electron-updater": "^6.3.9"
  }
}
```

（updater 代码在 Task 8 接入；依赖可先装。）

- [ ] **Step 3: `build-desktop.ps1`**

```powershell
# 1) prepare-runtime.ps1
# 2) cd apps/desktop; npm ci; npx electron-builder --win --x64 --publish never
```

- [ ] **Step 4: 本地打 Win 包并冒烟**

Run: `powershell -File scripts/packaging/build-desktop.ps1`  
Expected: `apps/desktop/dist/SuperVideoGenerator-Setup-0.1.0-x64.exe`  
安装到临时目录 → 启动 → `/health` 通 → 工作台 UI 可见（允许 SmartScreen「仍要运行」）。

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/electron-builder.yml apps/desktop/package.json \
  apps/desktop/package-lock.json scripts/packaging/build-desktop.ps1 \
  scripts/packaging/build-desktop.sh
git commit -m "$(cat <<'EOF'
feat(desktop): add electron-builder config for unsigned installers

EOF
)"
```

---

### Task 6: GitHub Actions Release 工作流（P2）

**Files:**
- Create: `.github/workflows/release-desktop.yml`
- Create: `scripts/packaging/export-icns.sh`（Mac 图标；可用 `sips` + `iconutil`，无则 electron-builder 用 png）

**Interfaces:**
- Trigger: `push` tags `v*.*.*`；`workflow_dispatch` inputs: `platform` = `all|windows|macos-x64|macos-arm64`
- Jobs: `build-windows` / `build-macos-x64`（`macos-13`）/ `build-macos-arm64`（`macos-14`）→ artifacts → `publish` 用 `softprops/action-gh-release` 上传

- [ ] **Step 1: 写 workflow（关键片段）**

```yaml
name: Release Desktop
on:
  push:
    tags: ["v*.*.*"]
  workflow_dispatch:
    inputs:
      platform:
        description: Target platform
        default: all
        type: choice
        options: [all, windows, macos-x64, macos-arm64]

jobs:
  build-windows:
    if: ...
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - name: Prepare runtime
        run: powershell -File scripts/packaging/prepare-runtime.ps1
      - name: Build installer
        working-directory: apps/desktop
        env:
          CSC_IDENTITY_AUTO_DISCOVERY: "false"
        run: |
          npm ci
          npx electron-builder --win --x64 --publish never
      - uses: actions/upload-artifact@v4
        with:
          name: win-x64
          path: apps/desktop/dist/*.{exe,yml,yaml,blockmap}

  # macos-x64 / macos-arm64 对称；env CSC_IDENTITY_AUTO_DISCOVERY=false
  # publish job: download artifacts, gh-release files
```

- [ ] **Step 2: 缓存 pip/npm**

对 `~/.cache/pip`、`apps/web/node_modules`、`apps/desktop/node_modules` 加 `actions/cache`。

- [ ] **Step 3: 用 `workflow_dispatch` 跑 windows 验证**

Expected: Artifact 含 Setup exe；无签名错误。若 GitHub Release 单文件超限，按 spec 改上传策略（对象存储）——本任务先记录体积到 job summary。

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release-desktop.yml scripts/packaging/export-icns.sh
git commit -m "$(cat <<'EOF'
ci: add unsigned Win/Mac desktop release workflow

EOF
)"
```

---

### Task 7: electron-updater + 设置页检查更新（P3）

**Files:**
- Create: `apps/desktop/updater.cjs`
- Modify: `apps/desktop/main.cjs`、`preload.cjs`
- Modify: `apps/web/src/desktop/types.ts`、`svfDesktop.ts`
- Modify: `apps/web/src/pages/AiSettingsPage.tsx`（桌面打包时显示「检查更新」）

**Interfaces:**
- Produces IPC：
  - `desktop:checkForUpdates` → `{ status, version?, message? }`
  - `desktop:quitAndInstall` → void
  - `desktop:getUpdateState` → 当前状态
- `autoUpdater.autoDownload = true`；`autoInstallOnAppQuit = true`；**不**调用静默强制重启
- 仅 `app.isPackaged` 时启用；`publish.provider=github`

- [ ] **Step 1: 实现 `updater.cjs`**

```javascript
/** 封装 electron-updater：检查、下载完成提示、退出安装。 */
function initUpdater({ dialog, BrowserWindow }) {
  const { autoUpdater } = require("electron-updater");
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;
  // on update-downloaded → dialog 询问是否立即重启；否：下次退出安装
  return {
    check: () => autoUpdater.checkForUpdates(),
    quitAndInstall: () => autoUpdater.quitAndInstall(false, true),
  };
}
```

- [ ] **Step 2: preload 暴露**

```javascript
checkForUpdates: () => ipcRenderer.invoke("desktop:checkForUpdates"),
quitAndInstall: () => ipcRenderer.invoke("desktop:quitAndInstall"),
onUpdateAvailable: (cb) => { /* ipcRenderer.on 一次性订阅 */ },
```

- [ ] **Step 3: AiSettingsPage 增加区块**

当 `getSvfDesktop()?.isDesktop` 且 `getInfo().packaged` 时渲染：

- 当前版本号
- 按钮「检查更新」
- 文案：仅从 GitHub Releases 更新

- [ ] **Step 4: 双版本升级手工验收清单写入 `docs/desktop-packaging.md`（Task 8 可合并）**

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/updater.cjs apps/desktop/main.cjs apps/desktop/preload.cjs \
  apps/web/src/desktop/ apps/web/src/pages/AiSettingsPage.tsx
git commit -m "$(cat <<'EOF'
feat(desktop): add GitHub Releases auto-update

EOF
)"
```

---

### Task 8: 文档同步与发版说明

**Files:**
- Create: `docs/desktop-packaging.md`
- Modify: `docs/code-design-plan.md`（§2 仓库结构）
- Modify: `docs/product-plan.md`（桌面分发一小段）
- Modify: `apps/desktop/README.md`
- Modify: `README.md`、`CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-07-17-desktop-installer-design.md`（状态保持已确认；链到本 plan）

- [ ] **Step 1: 写 `docs/desktop-packaging.md`**

必须包含：
1. 如何打 tag 发版（`git tag v0.1.0 && git push origin v0.1.0`）
2. Win SmartScreen / Mac Gatekeeper 首次打开步骤
3. 仅从本仓库 Releases 下载的警告
4. 本地 `build-desktop.ps1` 命令
5. 可选签名 Secrets 表（附录，默认不用）

- [ ] **Step 2: 同步 code-design / product / README / CLAUDE / desktop README**

- [ ] **Step 3: 全量测试**

Run: `pytest tests/ -v`  
Run: `cd apps/desktop && npm run test:paths`  
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add docs/ apps/desktop/README.md README.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: desktop packaging and unsigned release guide

EOF
)"
```

---

## Spec Coverage Checklist

| Spec 章节 | Task |
|-----------|------|
| §2 架构 / 启动 | 2, 3 |
| §2.4 静态托管 | 1 |
| §3 prepare-runtime / requirements | 4 |
| §3 electron-builder 产物 | 5 |
| §4 未签名默认 | 5, 6 |
| §5 自动更新 | 7 |
| §7 CI | 6 |
| §8 用户数据 / .env | 2, 3 |
| §9 端口占用 | 2 |
| §11 测试与文档 | 1–8 |
| §12 P0–P3 | Tasks 1–7；文档 Task 8 |
| §15 锁定项 | Global Constraints + Task 4/5 |

## Placeholder / Self-Review Notes

- 无 TBD；python patch 版本在实现 Task 4 时写入真实 `python-version.txt`（查 astral release）。
- SPA 路由若与 FastAPI 冲突，以 Task 1 测试为准调整挂载方式，不改变「同源托管」目标。
- `runtime/src` 拷贝范围：整个 `core/` + `apps/`，避免遗漏导入。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-17-desktop-installer.md`.

**Two execution options:**

1. **Subagent-Driven（推荐）** — 每任务新开子代理，任务间复查  
2. **Inline Execution** — 本会话按 executing-plans 连续做，设检查点  

Which approach?
