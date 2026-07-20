# 桌面安装包打包与发版指南

> 更新：2026-07-17  
> 设计规格：[`superpowers/specs/2026-07-17-desktop-installer-design.md`](superpowers/specs/2026-07-17-desktop-installer-design.md)  
> 实现计划：[`superpowers/plans/2026-07-17-desktop-installer.md`](superpowers/plans/2026-07-17-desktop-installer.md)

个人开源项目**默认不代码签名**。正式发版产出**未签名**安装包；用户首次打开需按下方说明绕过系统拦截。维护者日后若取得证书，可按附录启用可选签名。

---

## 1. 从哪里下载（用户必读）

**请仅从本仓库 [GitHub Releases](https://github.com/GodyuFF/SuperVideoGenerator/releases) 下载安装包。**

- 不要从第三方网盘、镜像站或不明来源获取 `.exe` / `.dmg`。
- 应用内自动更新同样只信任官方 GitHub Releases，不支持自定义更新 URL。
- 未签名安装包依赖「来源必须是官方仓库」这一前提；第三方重打包无法保证安全。

---

## 2. 首次安装与打开（绕过系统拦截）

### Windows — SmartScreen「未知发布者」

1. 从官方 Releases 下载 `SuperVideoGenerator-Setup-{version}-x64.exe`。
2. 双击安装程序时若出现 SmartScreen 拦截：
   - 点击 **「更多信息」**
   - 再点击 **「仍要运行」**
3. 按 NSIS 向导完成安装；可从桌面或开始菜单快捷方式启动。

### macOS — Gatekeeper「无法验证开发者」

1. 从官方 Releases 下载对应架构的 DMG（`x64` 或 `arm64`）。
2. 打开 DMG，将应用拖入「应用程序」文件夹。
3. 首次启动若被拦截，任选其一：
   - **右键点击应用 → 打开** → 在对话框中确认打开；或
   - **系统设置 → 隐私与安全性** → 找到被阻止的应用 → **仍要打开**。
4. 若出现「已损坏」类提示且确认下载来源正确，多为 Gatekeeper 对未签名包的误报；仍优先使用 **右键 → 打开**，勿从不可信渠道下载。

---

## 3. 维护者：打 tag 正式发布

版本号与 `apps/desktop/package.json` 的 `version` 字段对齐。

```bash
# 1. 确认 version 已 bump（apps/desktop/package.json）
# 2. 提交并推送主分支
git push origin feat/desktop-installer   # 或你的发版分支

# 3. 打 tag 并推送（触发 Release Desktop 工作流）
git tag v0.1.0
git push origin v0.1.0
```

推送 `v*.*.*` 标签后，[`.github/workflows/release-desktop.yml`](../.github/workflows/release-desktop.yml) 会：

1. 在 Windows / macOS（x64 + arm64）并行构建未签名安装包；
2. 汇总产物并创建 GitHub Release（含 `latest.yml` / `latest-mac.yml` 供 `electron-updater` 使用）。

**调试单平台构建**（不创建 Release）：在 GitHub Actions 中手动运行 **Release Desktop** workflow，选择 `windows` / `macos-x64` / `macos-arm64`。

---

## 4. 本地构建（Windows）

需已安装 Node.js 22+；首次构建会下载嵌入式 Python 与完整 pip 依赖（含 torch，体积大、耗时长）。

```powershell
# 仓库根目录
.\scripts\packaging\build-desktop.ps1
```

常用参数：

| 参数 | 说明 |
|------|------|
| `-SkipPrepare` | 跳过 runtime 准备（仅当 `apps/desktop/runtime` 已完整存在） |
| `-PackOnly` | 只打解压目录（`electron-builder --dir`），用于快速冒烟 |

产物目录：`apps/desktop/dist/`  
Windows 安装包：`SuperVideoGenerator-Setup-{version}-x64.exe`

macOS 本地构建：

```bash
chmod +x scripts/packaging/*.sh
./scripts/packaging/export-icns.sh
./scripts/packaging/build-desktop.sh
```

---

## 5. 开发壳 vs 完整安装包

| 模式 | 适用对象 | 启动方式 |
|------|----------|----------|
| **开发壳** | 仓库贡献者 | `dev-desktop.bat`、`create-desktop-shortcut.bat` 或 `cd apps/desktop && npm start`；依赖本机 Python venv + Node，加载 Vite `:5173` |
| **完整安装包** | 终端用户 | 从 Releases 安装；内置嵌入式 Python + 生产前端，API 与 UI 同源 `http://127.0.0.1:8000` |

详见 [`apps/desktop/README.md`](../apps/desktop/README.md)。

---

## 6. 用户数据与配置

安装包**不包含** API Key 或项目数据。升级与重装默认保留：

| 平台 | 路径 |
|------|------|
| Windows | `%LOCALAPPDATA%\SuperVideoGenerator\`（`data/`、`logs/`、可选 `.env`） |
| macOS | `~/Library/Application Support/SuperVideoGenerator/` |

首次启动可在应用内 **AI 设置** 配置 LLM / 生图 / TTS；打包版另提供 **检查更新**（仅 GitHub Releases）。

---

## 7. 双版本升级手工验收清单

发版前建议用**两个连续版本**验证应用内更新与用户数据保留：

1. 在干净环境（或 VM）安装 **旧版** Release（如 `v0.1.0`），创建测试项目并写入 `data/`。
2. 确认工作台、剪辑 IPC、AI 设置可正常使用后退出。
3. 发布 **新版** tag（如 `v0.1.1`），等待 CI 完成 Release。
4. 在旧版应用中打开 **AI 设置 → 检查更新**，确认检测到新版本并下载。
5. 按提示重启安装；启动后确认版本号已更新。
6. 确认步骤 1 中的项目与 `data/` **仍在**（`%LOCALAPPDATA%\SuperVideoGenerator\data` 或 macOS 等价路径）。
7. 可选：卸载时选择「保留用户数据」，重装后再次确认数据完整。

---

## 附录 A：可选代码签名 Secrets（默认不启用）

本里程碑**不要求**签名。CI 默认 `CSC_IDENTITY_AUTO_DISCOVERY=false`，不因缺少证书而失败。

仅当维护者日后取得证书并在 GitHub 仓库 Settings → Secrets 中配置下列项时，才可在 workflow 中追加签名步骤：

| Secret | 用途 |
|--------|------|
| `WIN_CSC_LINK` | Windows 代码签名证书（.pfx，Base64） |
| `WIN_CSC_KEY_PASSWORD` | 证书密码 |
| `APPLE_API_KEY` | Apple 公证 API Key（.p8 内容） |
| `APPLE_API_KEY_ID` | Key ID |
| `APPLE_API_ISSUER` | Issuer ID |
| `APPLE_TEAM_ID` | Team ID |
| `CSC_NAME` | macOS 钥匙串中的签名身份名称 |

未配置上述 Secrets 时，继续产出并分发**未签名**安装包，行为与当前默认一致。
