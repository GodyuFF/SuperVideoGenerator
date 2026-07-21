# 快速开始

> 更新日期：2026-07-20

## 环境要求

- Python 3.11+
- Node.js 18+（前端）
- FFmpeg（可选；遗留导出路径需要，需在 PATH 中）

## 安装

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
cd apps/web && npm install && cd ../..
cp .env.example .env
# 编辑 .env，至少配置 LLM API Key（默认 DeepSeek）
```

也可在 Web **AI 设置页** 配置 LLM / 生图 / TTS，持久化至 `data/ai_config.json`（仅本机）。

## 启动

**桌面（推荐，仓库根目录）：**

```bat
launch-desktop.vbs
launch-desktop.bat
```

**浏览器模式：**

```bash
.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
cd apps/web && npm run dev
```

打开 [http://localhost:5173](http://localhost:5173)。

## 桌面安装包

从 [GitHub Releases](https://github.com/GodyuFF/SuperVideoGenerator/releases) 下载。安装包默认**未代码签名**，Windows SmartScreen / macOS Gatekeeper 可能提示拦截，属预期；详见 [apps/desktop/README.md](../apps/desktop/README.md)。

维护者本地打 Windows 包：

```powershell
.\apps\desktop\packaging\build-desktop.ps1
```

更多说明见 [apps/desktop/README.md](../apps/desktop/README.md)。

## 本地数据（勿提交）

| 路径 | 内容 |
|------|------|
| `data/` | 项目、剧本、媒体、对话、AI 配置 |
| `.env` | 环境变量与 API Key |

更多见仓库根 [README.md](../README.md)（英文：[README.en.md](../README.en.md)）与 [文档目录](README.md)。
