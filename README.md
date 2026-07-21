# SuperVideoGenerator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Release](https://img.shields.io/github/v/release/GodyuFF/SuperVideoGenerator?display_name=tag)](https://github.com/GodyuFF/SuperVideoGenerator/releases)

Language: **中文** | [English](README.en.md)

**从剧本到成片，一条对话流水线。**

多 Agent 协作的本地优先 AI 视频工具：用自然语言描述创意，完成剧本、分镜、生图、配音与剪辑；自备 API Key，数据默认留在本机。

**开始使用：** [下载安装包](https://github.com/GodyuFF/SuperVideoGenerator/releases) · [快速开始](docs/getting-started.md) · [产品概览](docs/product-overview.md)

## Demo

示例题材：女娲补天（故事书成片）。

| 步骤 | 说明 |
|------|------|
| 对话 | 自然语言描述创意，主 Agent 编排计划 |
| 分镜与资产 | 看板可见可改，人物 / 场景可复用 |
| 剪辑 | Edit Studio 多轨精修字幕、画面与旁白 |
| 成片 | 导出故事书视频 |

**成片演示：**

<a href="site/assets/demo-final.mp4">
  <img src="site/assets/demo-final-poster.jpg" alt="成片预览 — 点击观看 MP4" width="720" />
</a>

> GitHub README 无法内嵌播放本地视频；点击封面即可打开 [`demo-final.mp4`](site/assets/demo-final.mp4)。

**对应剪辑时间轴：**

<img src="site/assets/edit-timeline.png" alt="女娲补天项目的多轨剪辑时间轴" width="720" />

## Features

- **对话 + 看板**：计划可见可审，再按步骤执行
- **子 Agent 流水线**：剧本 / 分镜 / 生图 / TTS / 剪辑 / AI 视频
- **资产复用**：人物·道具·场景跨剧本共享，降低系列重复劳动
- **Edit Studio**：镜内多轨精修，可写回分镜
- **本地优先**：项目与 API Key 落在本机 `data/`，默认不入 Git
- **桌面分发**：Electron 开发壳 + GitHub Releases 安装包

## Quick Start

需要 Python 3.11+、Node.js 18+（FFmpeg 可选）。

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows；macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cd apps/web && npm install && cd ../..
cp .env.example .env            # 至少配置 LLM API Key
```

**启动（Windows 推荐）：**

```bat
launch-desktop.vbs
```

或浏览器模式：`uvicorn apps.api.main:app --port 8000` + `cd apps/web && npm run dev` → [http://localhost:5173](http://localhost:5173)

完整步骤见 [docs/getting-started.md](docs/getting-started.md)。

## Desktop

- 安装包：[GitHub Releases](https://github.com/GodyuFF/SuperVideoGenerator/releases)（默认未代码签名，Windows SmartScreen / macOS Gatekeeper 可能提示拦截，属预期）
- 开发壳：`launch-desktop.vbs` / `launch-desktop.bat`，或 `cd apps/desktop && npm start`
- 本地打 Windows 包：`.\apps\desktop\packaging\build-desktop.ps1`（见 [apps/desktop/README.md](apps/desktop/README.md)）

## Architecture

```
apps/web (Vite + React)  ──HTTP/WS──►  apps/api (FastAPI)
                                            │
                                       core/ (llm · edit · tts · store · …)
```

## Documentation

| 文档 | 说明 |
|------|------|
| [文档目录](docs/README.md) | 入门与手册导航 |
| [产品概览](docs/product-overview.md) | 定位与原则摘要 |
| [快速开始](docs/getting-started.md) | 安装与启动 |
| [贡献指南](CONTRIBUTING.md) | Issue / PR |
| [安全政策](SECURITY.md) | 漏洞私下报告 |
| [行为准则](CODE_OF_CONDUCT.md) | 社区规范 |

## Contact

| 方式 | 内容 |
|------|------|
| QQ 群 | `829936747` |
| 邮箱 | [312188032@qq.com](mailto:312188032@qq.com) |
| 微信群 | 扫码加入（二维码会过期，失效请用 QQ / 邮箱） |

<img src="site/assets/wechat-group-qr.png" alt="微信交流群二维码" width="180" />

## License

本项目采用 [MIT License](LICENSE)。

剪辑助手（Edit Studio）相关代码基于 **OpenCut**，其版权与许可声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [`apps/web/src/editor/opencut/LICENSE`](apps/web/src/editor/opencut/LICENSE)。

使用各 LLM、生图、TTS 等云服务时，请另行遵守对应服务商条款。
