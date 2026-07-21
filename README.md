# SuperVideoGenerator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Release](https://img.shields.io/github/v/release/GodyuFF/SuperVideoGenerator?display_name=tag)](https://github.com/GodyuFF/SuperVideoGenerator/releases)

Language: **中文** | [English](README.en.md)

**从剧本到成片，一条对话流水线。**

不用先学复杂工具：说清楚你想拍什么，多 Agent 帮你走完剧本、分镜、生图、配音与剪辑。自备 API Key，数据默认留在本机。

**开始使用：** [下载安装包](https://github.com/GodyuFF/SuperVideoGenerator/releases)（[EN](docs/getting-started.en.md)） · [快速开始](docs/getting-started.md)（[EN](docs/getting-started.en.md)） · [产品概览](docs/product-overview.md)（[EN](docs/product-overview.en.md)）

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

- **开口就能做视频**：像聊天一样描述创意，就能推进到成片——少踩工具坑，把精力留在故事本身
- **看得见的多 Agent 编排**：步骤可审、日志齐全、流程可改；既适合直接出片，也适合学 AI Agent、做二次定制
- **一家入口，多家能力**：对话与生成可对接多套 LLM / 生图 / TTS，按场景选最合适的模型，不必锁死单一平台
- **流程稳、界面不绕**：剧本 → 分镜 → 成片一条清晰主线，告别复杂画布节点，上手快、结果可控
- **精修不丢主线**：看板改计划与分镜，Edit Studio 多轨打磨，人物·场景可复用；数据与 Key 留在本机，桌面安装即用

## 一起交流

对产品用法、编排思路或二次开发感兴趣？欢迎加群探讨——问题反馈、案例分享、一起打磨工作流。

| 方式 | 内容 |
|------|------|
| QQ 群 | `829936747` |
| 微信群 | 扫下方二维码（会过期；失效请用 QQ 或邮件） |
| 邮箱 | [312188032@qq.com](mailto:312188032@qq.com) |

<img src="site/assets/wechat-group-qr.png" alt="微信交流群二维码" width="180" />

## Quick Start

**日常使用：** 从 [Releases](https://github.com/GodyuFF/SuperVideoGenerator/releases) 下载桌面安装包，在应用内配置 API Key 即可（未签名提示属预期）。

**从源码开发（桌面壳）：** 需 Python 3.11+、Node.js 18+。安装依赖后在仓库根目录运行：

```bat
launch-desktop.vbs
```

完整步骤（中/英）：[docs/getting-started.md](docs/getting-started.md) · [docs/getting-started.en.md](docs/getting-started.en.md)。打包与开发壳细节见 [apps/desktop/README.md](apps/desktop/README.md)。

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
| [产品概览](docs/product-overview.md) / [EN](docs/product-overview.en.md) | 定位与原则摘要 |
| [快速开始](docs/getting-started.md) / [EN](docs/getting-started.en.md) | 桌面安装与启动 |
| [贡献指南](CONTRIBUTING.md) | Issue / PR |
| [安全政策](SECURITY.md) | 漏洞私下报告 |
| [行为准则](CODE_OF_CONDUCT.md) | 社区规范 |

## License

本项目采用 [MIT License](LICENSE)。

剪辑助手（Edit Studio）相关代码基于 **OpenCut**，其版权与许可声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [`apps/web/src/editor/opencut/LICENSE`](apps/web/src/editor/opencut/LICENSE)。

使用各 LLM、生图、TTS 等云服务时，请另行遵守对应服务商条款。
