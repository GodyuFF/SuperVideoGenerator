# 桌面完整安装包（Win + Mac）设计

> 日期：2026-07-17  
> 状态：已确认（含默认不签名）  
> 实现计划：[`../plans/2026-07-17-desktop-installer.md`](../plans/2026-07-17-desktop-installer.md)  
> 用户发版与安装说明：[`../../desktop-packaging.md`](../../desktop-packaging.md)  
> 前置：[`2026-07-15-electron-desktop-shell-design.md`](./2026-07-15-electron-desktop-shell-design.md)（开发期桌面壳已落地；完整安装包为其后续里程碑）

## 1. 目标与已确认决策

### 1.1 目标

交付**完整离线安装包**：用户安装后双击即可使用，无需本机预装 Python / Node / 仓库克隆。

### 1.2 已确认决策

| 项 | 选择 |
|----|------|
| 安装包范围 | **A** 完整离线：Electron + 生产前端 + 嵌入式 Python/API + 全量生产依赖 |
| 构建与分发 | **C** GitHub Actions CI 分别打 Win + Mac，本机可不装 Mac |
| 代码签名 | **不签（默认）**：个人开源不采购证书；CI 正式发版产出**未签名**安装包。签名/公证仅作可选后续，Secrets 就绪后可打开 |
| 证书 | **不采购**（本里程碑）；§4 仅保留「以后若要签」的可选附录 |
| 自动更新 | **A** `electron-updater` + GitHub Releases（未签名包同样可更新；依赖 GitHub 渠道信任） |
| 默认依赖 | **完整带上** torch / torchaudio / WhisperX（及现有生产依赖），不提供「精简默认包」 |

### 1.3 非目标

- 不重写 `core/` 领域逻辑；桌面仍走本机 HTTP/WebSocket API
- 不做 Tauri / 原生 UI 重写
- 不做 Windows Store / Mac App Store 上架（可后续另开）
- 不做 Linux 安装包（本里程碑）
- **不要求**代码签名 / Apple 公证（个人开源默认路径）
- 不在本里程碑实现差分增量更新以外的私有 CDN（默认 GitHub Releases；体积过大时可后续换对象存储）

---

## 2. 总体架构

### 2.1 交付物

| 平台 | 产物 | 架构 |
|------|------|------|
| Windows | **未签名** NSIS 安装程序 `SuperVideoGenerator-Setup-{version}-x64.exe` | x64 |
| macOS | **未签名** DMG | **分架构**：`x64` 与 `arm64` 各一份（控体积；不做 Universal 胖包） |

版本号与 `apps/desktop/package.json` 的 `version` 对齐；打 tag `vX.Y.Z` 触发正式发布。

### 2.2 运行时组成（安装目录）

```
SuperVideoGenerator.app / 安装目录
├── Electron 壳（main / preload / 图标）
├── resources/
│   └── runtime/                 # extraResources，不进 asar
│       ├── python/              # 嵌入式解释器 + site-packages（含 torch/WhisperX）
│       ├── web/                 # apps/web 生产构建（dist）
│       ├── api_boot.py          # 薄启动脚本：设置路径、挂载静态、起 uvicorn
│       └── requirements.lock    # 构建时锁定的依赖清单（审计用）
└──（Electron 自有文件）
```

用户可写数据（升级不覆盖）：

| 平台 | 路径 |
|------|------|
| Windows | `%LOCALAPPDATA%\SuperVideoGenerator\`（含 `data/`、`logs/`、可选 `.env`） |
| macOS | `~/Library/Application Support/SuperVideoGenerator/` |

环境变量：`SVG_DATA_ROOT` 指向上述 `data/`；API Key 等敏感配置放用户目录 `.env`（或首次启动引导写入），**不打进安装包**。

### 2.3 启动与退出

```
Electron ready
  → 展示 splash（现有 splash-boot.html）
  → spawn 嵌入式 python -m uvicorn（或 api_boot）绑定 127.0.0.1:8000
  → 轮询健康检查（如 GET /api/... 或 /health）
  → 成功：loadURL http://127.0.0.1:8000/
  → 失败：窗口内错误页 + 日志路径
窗口关闭 / before-quit
  → 结束本进程拉起的 API 子进程
  → 不杀用户自行启动的外部服务
```

**开发 vs 生产：**

| 模式 | 前端 | 后端 |
|------|------|------|
| 开发（现有） | Vite `:5173` | 本机 venv / `uvicorn` |
| 生产安装包 | FastAPI 托管 `runtime/web` | 嵌入式 Python |

生产模式由 `SVG_DESKTOP_PACKAGED=1`（或 `app.isPackaged`）切换；`devServers.cjs` 仅开发路径使用，生产走 `prodServers.cjs`（新建）。

### 2.4 前端托管

`apps/api` 在桌面生产模式下：

- `StaticFiles` 挂载 `runtime/web` 到 `/`
- SPA fallback：非 `/api`、`/ws` 路径回退 `index.html`
- CORS 保持对本机 origin 友好（或同源后可收紧）

开发模式行为不变（Vite 独立端口）。

---

## 3. 打包目录与构建流水线

### 3.1 仓库布局

```
apps/desktop/
  package.json                 # 增加 electron-builder、electron-updater；build 脚本
  electron-builder.yml
  main.cjs                     # 生产启动路径
  prodServers.cjs              # 嵌入式 API 拉起/停止
  preload.cjs                  # 可暴露 checkForUpdates 等白名单 IPC
  icon.ico / icon.png / （Mac .icns 由构建生成）
scripts/packaging/
  prepare-runtime.ps1          # Windows：嵌入式 Python + pip + 拷贝 web
  prepare-runtime.sh           # macOS CI
  build-desktop.ps1 / .sh      # 调用 electron-builder
  export-icns.sh               # 从 icon.png 生成 .icns（Mac CI）
requirements-desktop.txt       # 生产依赖 = 现 requirements 去掉 pytest*；显式含 torch/WhisperX
.github/workflows/
  release-desktop.yml          # 矩阵构建 + Release（默认不签名）
docs/desktop-packaging.md      # 用户向：安装、首次打开绕过系统拦截、发版步骤（实现时同步）
```

`runtime/` 构建产物 **不入库**（`.gitignore`）。

### 3.2 `requirements-desktop.txt` 策略

- 以当前 `requirements.txt` 为源，**移除** `pytest` / `pytest-asyncio`
- **保留** `torch`、`torchaudio`、`whisperx`、`imageio-ffmpeg` 等生产依赖
- 平台差异用 CI 中的 pip 索引/额外参数处理：
  - **Windows**：优先安装带 CUDA 的官方/PyTorch 索引 wheel（无 GPU 机器仍可装 CUDA 包，体积大但行为与现开发环境一致；运行时 WhisperX 无 GPU 则沿用现有回退逻辑）
  - **macOS**：安装 macOS 可用的 torch（CPU/MPS）；WhisperX 按上游支持矩阵安装，失败时 CI 必须失败并明确日志（不静默去掉）

构建结束写入 `runtime/requirements.lock`（`pip freeze`）便于复现。

### 3.3 单平台构建步骤

1. Checkout（含 LFS 若有）
2. Setup Node LTS → `apps/web`：`npm ci && npm run build`
3. 准备嵌入式 Python（推荐 [python-build-standalone](https://github.com/astral-sh/python-build-standalone) 或官方 embeddable + get-pip，版本与项目 3.11+ 对齐）
4. 创建 venv/前缀于 `runtime/python`，`pip install -r requirements-desktop.txt`
5. 拷贝 `apps/web/dist` → `runtime/web`；写入 `api_boot.py`
6. `electron-builder`：
   - Win：`nsis` target，自定义安装目录、桌面快捷方式、卸载保留用户数据选项默认「保留」
   - Mac：`dmg` target；**默认不签名、不公证**（`forceCodeSigning: false` / 不配置 CSC）
7. 上传 Release 资产 + updater 元数据（`latest.yml` / `latest-mac.yml`）

### 3.4 体积与 CI 资源

- 预期单平台安装包 **约 2–6GB+**（torch + WhisperX 主导）
- Actions：使用较大磁盘 runner 或构建后清理缓存；对 Python/torch wheel **缓存** `~/.cache/pip`
- GitHub Releases 单文件有大小限制风险；若触顶：
  1. 优先改用分卷或外链对象存储（R2/S3）+ updater 自定义 `provider`
  2. 本设计默认先走 GitHub；实现期用一次真实构建验证体积，超限则按上述切换（不改变架构）

### 3.5 本地验证（开发者）

- Windows：`scripts/packaging/build-desktop.ps1` 产出未签名安装包，本机安装冒烟
- Mac：仅在 `macos-*` runner 或开发者 Mac 上构建

---

## 4. 未签名分发与用户说明（默认）

个人开源**可以且本里程碑默认不签证书**。合法、常见；代价是系统会多一步警告。

### 4.1 用户侧体验（需写进 README / 安装说明）

| 平台 | 常见提示 | 用户怎么开 |
|------|----------|------------|
| Windows | SmartScreen「未知发布者」 | 「更多信息」→「仍要运行」 |
| macOS | 「无法验证开发者」/ 已损坏类提示 | 系统设置 → 隐私与安全性 → 仍要打开；或首次 **右键 → 打开** |

文档必须写清：安装包只从 **本仓库 GitHub Releases** 下载，勿信第三方镜像。

### 4.2 CI 行为（默认）

- tag / `workflow_dispatch`：**始终**产出未签名工件并上传 Release
- **不因缺少证书而失败**
- `electron-builder` 明确关闭强制签名，避免 CI 误等 CSC 环境变量

### 4.3 可选：以后若要签名（非本里程碑必做）

仅当维护者日后取得证书时启用；配置方式预留即可，不阻塞发版：

| Secret（可选） | 用途 |
|----------------|------|
| `WIN_CSC_LINK` / `WIN_CSC_KEY_PASSWORD` | Windows 代码签名 |
| `APPLE_API_KEY` / `APPLE_API_KEY_ID` / `APPLE_API_ISSUER` / `APPLE_TEAM_ID` / `CSC_NAME` | Mac 签名 + 公证 |

启用条件：上述 Secrets 存在时，workflow 才跑签名步骤；否则跳过。采购与 Apple Developer 年费**不在本里程碑范围**。

---

## 5. 自动更新

### 5.1 机制

- 依赖：`electron-updater`
- Provider：`github`（owner/repo 与当前仓库一致）
- 检查时机：应用启动后空闲时检查 + 设置页「检查更新」
- 策略：**下载完成后提示重启安装**（不强制静默重启，避免打断生成任务）
- 生成任务进行中：仅提示「有更新」，推迟到空闲或用户确认

### 5.2 产物元数据

- Windows：`latest.yml` + Setup exe
- macOS：`latest-mac.yml` + 对应 arch 的 DMG/ZIP（electron-builder 默认；若 DMG 更新不稳可改用 `zip` 作为更新通道、DMG 仅首装）

### 5.3 版本与通道

- 正式通道：GitHub Release（非 prerelease）
- 可选 beta：prerelease + 设置中「参与预览」开关（本里程碑可只做正式通道，预留配置项）

### 5.4 安全（未签名前提）

- 更新 URL **固定**为官方 GitHub Releases，不允许用户配置任意 URL
- 校验 Release 资产名与版本元数据（`latest.yml`）；不依赖平台代码签名作为硬前提
- README 强调：只信任本仓库 Release；自动更新不降低「来源必须是官方仓库」的要求

---

## 6. 桌面壳代码变更要点

| 文件 | 变更 |
|------|------|
| `main.cjs` | `app.isPackaged` 时用 `prodServers`；`WEB_URL` 指向 `http://127.0.0.1:8000`；注册 updater |
| `prodServers.cjs` | 解析 `process.resourcesPath/runtime`，spawn 嵌入式 Python，日志写入用户目录 |
| `devServers.cjs` | 保持开发行为；打包模式不调用 |
| `preload.cjs` | 可选暴露 `getVersion` / `checkForUpdates` / `quitAndInstall` |
| `apps/api/main.py`（或薄包装） | 生产环境挂载静态前端 + SPA fallback |
| `apps/web` | 生产 `base` 与 API 同源；桌面检测逻辑保持 |
| `mediaPath` / IPC | `DATA_ROOT` 改为用户数据目录下的 `data/` |

开发期桌面快捷方式改由 `scripts/update_desktop_shortcut.ps1` 生成（2026-07-20 清理后根目录不再保留 `create-desktop-shortcut.bat`）；与安装包并行：开发者用仓库 `launch-desktop.vbs` / `.bat` 启动；最终用户用安装包。

---

## 7. CI 工作流设计

### 7.1 触发

- `push` tags：`v*.*.*` → 正式发布（未签名制品）
- `workflow_dispatch`：可选指定 platform，便于调试单平台构建

### 7.2 Job 矩阵

| job | runner | 产物 |
|-----|--------|------|
| `build-windows` | `windows-latest` | NSIS exe + `latest.yml` |
| `build-macos-x64` | `macos-13` 或 `macos-14` x64 | DMG + updater 元数据 |
| `build-macos-arm64` | `macos-14` arm64 | DMG + updater 元数据 |
| `publish` | `ubuntu-latest` | 汇总上传同一 GitHub Release |

并行构建；全部成功后发布。签名步骤默认跳过，不作为发布门禁。

### 7.3 缓存

- npm：`apps/web` + `apps/desktop`
- pip：torch 等大 wheel
- electron 缓存目录

---

## 8. 配置、密钥与首次启动

1. 安装完成后首次启动：若用户目录无 `.env` 且缺少必要 Key，应用内提示前往设置页填写（与现有配置模型对齐），写入用户目录，不写安装目录。
2. `data/` 在首次启动创建。
3. 卸载（Windows）：默认保留用户数据；高级选项可清除。
4. 日志：`.../logs/desktop-servers.log` 与 API 日志分离或同目录分文件。

---

## 9. 错误处理

| 场景 | 行为 |
|------|------|
| API 子进程启动失败 | splash/错误页展示原因摘要 + 日志路径；不白屏退出 |
| 端口 8000 被占用 | 尝试探测是否已是本应用；否则选备用端口（写进临时文件供渲染进程/壳读取）或明确报错「请关闭占用进程」——**实现选定：优先固定 8000，占用则报错并提示**（简单可测） |
| 更新下载失败 | 非阻塞 toast/对话框，可重试 |
| 用户因 SmartScreen / Gatekeeper 打不开 | 错误页或 README 链到「首次打开说明」；不视为构建失败 |
| WhisperX/CUDA 运行失败 | 保持现有运行时回退（字数比例切分等），不导致应用无法启动 |

---

## 10. 安全

- 保持 `contextIsolation: true`、`nodeIntegration: false`、IPC 白名单
- `media:readLocal` 仍限制在 `SVG_DATA_ROOT` 内
- API 仅绑定 `127.0.0.1`
- 默认未签名：安全模型依赖「仅从官方 GitHub Releases 获取」+ 应用内更新 URL 固定
- 可选签名相关 Secrets 永不入库、不进日志

---

## 11. 测试与验收

### 11.1 自动化

- 现有 `apps/desktop` 的 `node --test` 扩展：`prodServers` 路径解析、打包模式下资源路径
- API：静态挂载与 SPA fallback 的单元/API 测试（`tests/`）
- `pytest tests/ -v` 全量通过；禁止在非测试代码中新增 mock
- packaging 脚本：在 CI 中至少跑到「组装 runtime + dry-run electron-builder 配置解析」（完整打包含 torch 的 job 以 release 工作流为准）

### 11.2 手工验收

1. 干净 Windows 机（无 Python/Node）：按文档绕过 SmartScreen → 安装 → 启动 → 工作台可用
2. 干净 Mac：按文档绕过 Gatekeeper → 启动 → 工作台可用（arm64 / x64 制品抽测）
3. 剪辑媒体水合仍走 IPC（不回归 HTTP 大文件拷贝）
4. 发布两个版本：应用内检测到更新并成功升级，用户 `data/` 保留
5. 卸载后重装：用户数据按选项保留/清除符合预期
6. 无 GPU 机器：应用可启动；WhisperX 路径按现有逻辑降级

### 11.3 文档同步（实现阶段）

- `docs/code-design-plan.md` §2 仓库结构：packaging / workflow
- `docs/product-plan.md`：桌面分发与自动更新简述
- `apps/desktop/README.md`：开发壳 vs 安装包
- [`docs/desktop-packaging.md`](../../desktop-packaging.md)：发版步骤、首次打开绕过说明、双版本升级验收、可选签名附录
- `README.md` / `CLAUDE.md`：发版命令摘要

---

## 12. 实现分期建议

| 阶段 | 内容 | 可交付 |
|------|------|--------|
| P0 | 生产静态托管 + `prodServers` + 本地 Windows 未签名包 | 本机可装可跑 |
| P1 | `requirements-desktop` 完整依赖进 runtime；体积与启动冒烟 | 完整离线 Win 包 |
| P2 | GitHub Actions 矩阵；Win + Mac 未签名制品 + tag 发版 | CI 双平台 Release |
| P3 | `electron-updater` + 设置页检查更新 + 跨版本升级验收 | 自动更新闭环 |
| P4（可选） | 若日后有证书：打开签名/公证开关 | 签名安装包 |

本里程碑 **DoD 止于 P3**；P4 非必须。

---

## 13. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 包体过大，Release 上传失败 | 实测体积；必要时对象存储 + 自定义 updater provider |
| WhisperX/torch 在 Mac CI 安装失败 | 锁定已知可用版本；失败即 fail，不静默删依赖 |
| SmartScreen / Gatekeeper 阻拦 | README 与安装说明写清绕过步骤；只从官方 Release 下载 |
| Electron 杀毒误报 | 稳定发布渠道 + 文档说明；日后可选签名 |
| 嵌入式 Python 路径过长 / 空格 | 安装路径默认短路径；测试含空格用户名 |
| 生成任务中强制更新 | 更新策略避开强制重启（§5.1） |

---

## 14. 成功标准（Definition of Done）

1. 用户在无开发环境的 Win/Mac 上，按文档完成首次信任后，可安装并完成主路径使用  
2. CI 可由 tag 一键产出双平台**未签名**制品并发布 Release  
3. 应用内可检测并安装新版本，用户数据保留  
4. 发版与「首次打开」说明文档齐全  
5. 相关测试与文档同步完成；无非测试 mock  

---

## 15. 已锁定的实现细节

| 项 | 决定 |
|----|------|
| 嵌入式 Python | [python-build-standalone](https://github.com/astral-sh/python-build-standalone) **CPython 3.11.x** install_only 发行包（具体 patch 版本在 `scripts/packaging/python-version.txt` 锁定） |
| Mac 产物 | 首装用 **DMG**；自动更新通道用 **ZIP**（同 arch） |
| 静态前端挂载 | 独立模块 `apps/api/desktop_static.py`，由 `main.py` 条件挂载 |
| 健康检查 | 复用已有 `GET /health`（不新增端点） |
| 生产 API 绑定 | `127.0.0.1:8000`；占用则失败并提示 |

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-07-17 | 初稿：完整离线包 + CI 双平台 + 全量依赖含 torch/WhisperX + 签名公证 + 自动更新 + 证书采购清单 |
| 2026-07-17 | 修订：个人开源默认**不签名**；签名改为可选后续；补充 SmartScreen/Gatekeeper 用户说明 |
