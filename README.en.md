# SuperVideoGenerator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Release](https://img.shields.io/github/v/release/GodyuFF/SuperVideoGenerator?display_name=tag)](https://github.com/GodyuFF/SuperVideoGenerator/releases)

Language: [中文](README.md) | **English**

**From script to final cut — one conversation pipeline.**

Skip the steep tool learning curve: say what you want to make, and multi-agent orchestration carries you through script, storyboard, images, voiceover, and edit. Bring your own API keys; data stays on your machine by default.

**Get started:** [Download installer](https://github.com/GodyuFF/SuperVideoGenerator/releases) · [Quick start](docs/getting-started.en.md) ([中文](docs/getting-started.md)) · [Product overview](docs/product-overview.md) (zh)

## Demo

Sample story: Nüwa Mends the Sky (storybook final cut).

| Step | What happens |
|------|----------------|
| Chat | Describe the idea; the lead agent plans the run |
| Storyboard & assets | Editable board; characters / scenes reusable |
| Edit | Multi-track polish for captions, picture, and narration |
| Final cut | Export the storybook video |

**Final cut preview:**

<a href="site/assets/demo-final.mp4">
  <img src="site/assets/demo-final-poster.jpg" alt="Final cut preview — click to open MP4" width="720" />
</a>

> GitHub READMEs cannot embed local video playback; click the poster to open [`demo-final.mp4`](site/assets/demo-final.mp4).

**Matching edit timeline:**

<img src="site/assets/edit-timeline.png" alt="Multi-track edit timeline for the Nüwa project" width="720" />

## Features

- **Make video by chatting**: Describe the idea in natural language and push toward a final cut — less tool friction, more time for the story
- **Multi-agent you can see**: Reviewable steps, rich logs, and customizable flows — ship videos today, or learn agents and extend the system
- **One entry, many providers**: Chat and generation across multiple LLM / image / TTS services — pick the right model per job, no single-vendor lock-in
- **A clear path, not a maze**: Script → storyboard → final cut without complex canvas node graphs — fast to learn, easier to control
- **Polish without losing the plot**: Board edits for plans and shots, Edit Studio for multi-track polish, reusable characters and scenes; keys stay local, desktop install ready to go

## Join the community

Curious about workflows, orchestration, or extending the project? Join the group to chat, share cases, and improve the pipeline together.

| Channel | Detail |
|---------|--------|
| QQ group | `829936747` |
| WeChat group | Scan the QR below (it expires; use QQ or email if needed) |
| Email | [312188032@qq.com](mailto:312188032@qq.com) |

<img src="site/assets/wechat-group-qr.png" alt="WeChat group QR code" width="180" />

## Quick Start

**Day-to-day use:** Download the desktop installer from [Releases](https://github.com/GodyuFF/SuperVideoGenerator/releases) and configure API keys in the app (unsigned-installer warnings are expected).

**From source (desktop shell):** Requires Python 3.11+ and Node.js 18+. After installing dependencies, from the repository root:

```bat
launch-desktop.vbs
```

Full steps: [docs/getting-started.en.md](docs/getting-started.en.md) · [docs/getting-started.md](docs/getting-started.md) (zh). Packaging and dev shell: [apps/desktop/README.md](apps/desktop/README.md).

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
| [Product overview](docs/product-overview.md) (zh) | Positioning and principles |
| [Getting started](docs/getting-started.en.md) / [中文](docs/getting-started.md) | Desktop install and launch |
| [Contributing](CONTRIBUTING.md) (zh) | Issues / PRs |
| [Security](SECURITY.md) (zh) | Private vulnerability reports |
| [Code of Conduct](CODE_OF_CONDUCT.md) (zh) | Community norms |

## License

This project is licensed under the [MIT License](LICENSE).

Edit Studio–related code is based on **OpenCut**. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [`apps/web/src/editor/opencut/LICENSE`](apps/web/src/editor/opencut/LICENSE).

When using cloud LLM, image, or TTS providers, also follow their respective terms of service.
