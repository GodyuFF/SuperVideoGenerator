# SuperVideoGenerator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Release](https://img.shields.io/github/v/release/GodyuFF/SuperVideoGenerator?display_name=tag)](https://github.com/GodyuFF/SuperVideoGenerator/releases)

Language: [中文](README.md) | **English**

**From script to final cut — one conversation pipeline.**

Skip the steep tool learning curve: say what you want to make, and multi-agent orchestration carries you through script, storyboard, images, voiceover, and edit. Bring your own API keys; data stays on your machine by default.

**Get started:** [Download installer](https://github.com/GodyuFF/SuperVideoGenerator/releases) · [Quick start](docs/getting-started.en.md) ([中文安装](docs/getting-started.md) · [中文用户手册](docs/user-guide/README.md)) · [Product overview](docs/product-overview.en.md) ([中文](docs/product-overview.md))

## What it looks like

A walkthrough of the real UI (screenshots from the [Chinese user guide](docs/user-guide/README.md)).

### 1. Project list

Manage **My projects** — create a project and open a script from here.

<img src="docs/user-guide/assets/figure-02-project-list.png" alt="Project list" width="720" />

### 2. Chat and execution plan

Drive production in natural language on the left; review the plan on the right. Confirmation cards keep the run from being a black box. See [对话与执行计划](docs/user-guide/03-chat-and-plan.md) (zh).

<img src="docs/user-guide/assets/figure-04-chat.png" alt="Chat and execution plan" width="720" />

### 3. Generation queue

Image, TTS, and other media jobs queue up so you can watch progress.

<img src="docs/user-guide/assets/figure-05-generation-queue.png" alt="Generation queue" width="720" />

### 4. Edit Assistant

Multi-track polish for captions, picture, and narration; export from the top bar. See [剪辑与导出](docs/user-guide/05-edit-and-export.md) (zh).

<img src="docs/user-guide/assets/figure-06-edit-studio.png" alt="Edit Assistant" width="720" />

## Demo

Sample story: Nüwa Mends the Sky (storybook final cut).

| Step | What happens |
|------|----------------|
| Chat | Describe the idea; the lead agent plans the run |
| Storyboard & assets | Editable board; characters / scenes reusable |
| Edit | Edit Assistant multi-track polish for captions, picture, and narration |
| Final cut | Export the storybook video |

**Final cut preview:**

<a href="site/assets/demo-final.mp4">
  <img src="site/assets/demo-final-poster.jpg" alt="Final cut preview — click to open MP4" width="720" />
</a>

> GitHub READMEs cannot embed local video playback; click the poster to open [`demo-final.mp4`](site/assets/demo-final.mp4).

**Matching edit timeline:**

<img src="site/assets/edit-timeline.png" alt="Multi-track edit timeline for the Nüwa project" width="720" />

## How to use (zero to final cut)

First run: prefer **Storybook mode** (LLM + image + TTS only — no video API required). Full steps: [从零到成片](docs/user-guide/01-first-video.md) (zh).

| Step | What to do |
|------|------------|
| 1. Configure AI | Top bar **AI settings**: add LLM / image keys; TTS defaults to edge; storybook can leave the Video tab off |
| 2. Project & script | **My projects** → new project → new script → **Enter script** |
| 3. Chat to produce | Pick Storybook, keep Goal mode off; describe the idea; continue via confirmation cards; watch the plan panel |
| 4. Board polish | Check script / characters / shots; tweak narration and captions |
| 5. Edit & export | **Edit** tab preview → **Edit** opens Edit Assistant → top-bar **Export** for MP4 |

## Video styles

Style locks after the **first send** on a script; switch styles by creating a new script. Details: [视频风格与模式](docs/user-guide/06-modes.md) (zh).

| Style | Best for | AI setup |
|-------|----------|----------|
| **Storybook** | First run; stills + narration | LLM + image + TTS |
| **AI video** | Model-generated motion clips | Also enable **Video** tab + video API key |
| **Image-to-video** | I2V from existing frames | Same; needs video capability and frame assets |

## Highlights

| Area | What you get |
|------|----------------|
| **Chat orchestration** | Lead agent (ReAct) runs script → storyboard → image → TTS → edit; plans are visible and reviewable |
| **Board & assets** | Inspect and edit script, characters, empties, and shots; people / scenes reusable across scripts |
| **Edit Assistant** | Media library + preview + multi-track timeline; export MP4; edits write back to the script |
| **Local-first** | Keys and project data stay on your machine; desktop installer ready, or run the dev shell from source |
| **Multi-provider** | Swap LLM / image / TTS providers per job — no single-vendor lock-in |

## Quick Start

**Day-to-day use:** Download the desktop installer from [Releases](https://github.com/GodyuFF/SuperVideoGenerator/releases) and configure API keys in the app (unsigned-installer warnings are expected).

**From source (desktop shell):** Requires Python 3.11+ and Node.js 18+. After installing dependencies, from the repository root:

```bat
launch-desktop.vbs
```

Full steps: [docs/getting-started.en.md](docs/getting-started.en.md) · [docs/getting-started.md](docs/getting-started.md) (zh). Packaging and dev shell: [apps/desktop/README.md](apps/desktop/README.md).

After launch, follow the [user guide](docs/user-guide/README.md) (zh); FAQ: [07-faq.md](docs/user-guide/07-faq.md).

## Join the community

Curious about workflows, orchestration, or extending the project? Join the group to chat, share cases, and improve the pipeline together.

| Channel | Detail |
|---------|--------|
| QQ group | `829936747` |
| WeChat group | Scan the QR below (it expires; use QQ or email if needed) |
| Email | [312188032@qq.com](mailto:312188032@qq.com) |

<img src="site/assets/wechat-group-qr.png" alt="WeChat group QR code" width="180" />

## Architecture

```
apps/web (Vite + React)  ──HTTP/WS──►  apps/api (FastAPI)
                                            │
                                       core/ (llm · edit · tts · store · …)
```

## Documentation

| Doc | Notes |
|-----|--------|
| [Docs index](docs/README.md) (zh) | Entry and manuals |
| [Product overview](docs/product-overview.en.md) / [中文](docs/product-overview.md) | Positioning and principles |
| [Getting started](docs/getting-started.en.md) / [中文](docs/getting-started.md) | Install and launch |
| [User guide](docs/user-guide/README.md) (zh) | Zero to final cut through FAQ |
| └ [从零到成片](docs/user-guide/01-first-video.md) | First storybook video |
| └ [AI 配置](docs/user-guide/02-ai-config.md) | LLM / image / TTS / video |
| └ [对话与执行计划](docs/user-guide/03-chat-and-plan.md) | Confirmations and plan panel |
| └ [看板与资产](docs/user-guide/04-board-and-assets.md) | Script, characters, shots |
| └ [剪辑与导出](docs/user-guide/05-edit-and-export.md) | Edit Assistant and export |
| [Contributing](CONTRIBUTING.md) (zh) | Issues / PRs |
| [Security](SECURITY.md) (zh) | Private vulnerability reports |
| [Code of Conduct](CODE_OF_CONDUCT.md) (zh) | Community norms |

## License

This project is licensed under the [MIT License](LICENSE).

Edit Assistant–related code is based on **OpenCut**. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [`apps/web/src/editor/opencut/LICENSE`](apps/web/src/editor/opencut/LICENSE).

When using cloud LLM, image, or TTS providers, also follow their respective terms of service.
