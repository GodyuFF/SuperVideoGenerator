# SuperVideoGenerator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Release](https://img.shields.io/github/v/release/GodyuFF/SuperVideoGenerator?display_name=tag)](https://github.com/GodyuFF/SuperVideoGenerator/releases)

Language: [中文](README.md) | **English**

**From script to final cut — one conversation pipeline.**

A local-first, multi-agent AI video tool: describe your idea in natural language to produce script, storyboard, images, voiceover, and edit. Bring your own API keys; project data stays on your machine by default.

**Get started:** [Download installer](https://github.com/GodyuFF/SuperVideoGenerator/releases) · [Quick start](docs/getting-started.md) (zh) · [Product overview](docs/product-overview.md) (zh)

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

- **Chat + board**: Plans are visible and reviewable before execution
- **Sub-agent pipeline**: Script / storyboard / image / TTS / edit / AI video
- **Asset reuse**: Characters, props, and scenes shared across scripts
- **Edit Studio**: In-shot multi-track polish with write-back to shots
- **Local-first**: Projects and API keys live under `data/` (not in Git by default)
- **Desktop distribution**: Electron shell + installers on GitHub Releases

## Quick Start

Requires Python 3.11+ and Node.js 18+ (FFmpeg optional).

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows; macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cd apps/web && npm install && cd ../..
cp .env.example .env            # set at least an LLM API key
```

**Launch (Windows recommended):**

```bat
launch-desktop.vbs
```

Or browser mode: `uvicorn apps.api.main:app --port 8000` + `cd apps/web && npm run dev` → [http://localhost:5173](http://localhost:5173)

Full steps: [docs/getting-started.md](docs/getting-started.md) (zh).

## Desktop

- Installers: [GitHub Releases](https://github.com/GodyuFF/SuperVideoGenerator/releases) (unsigned by default — Windows SmartScreen / macOS Gatekeeper warnings are expected)
- Dev shell: `launch-desktop.vbs` / `launch-desktop.bat`, or `cd apps/desktop && npm start`
- Build Windows package locally: `.\apps\desktop\packaging\build-desktop.ps1` (see [apps/desktop/README.md](apps/desktop/README.md))

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
| [Getting started](docs/getting-started.md) (zh) | Install and launch |
| [Contributing](CONTRIBUTING.md) (zh) | Issues / PRs |
| [Security](SECURITY.md) (zh) | Private vulnerability reports |
| [Code of Conduct](CODE_OF_CONDUCT.md) (zh) | Community norms |

## Contact

| Channel | Detail |
|---------|--------|
| QQ group | `829936747` |
| Email | [312188032@qq.com](mailto:312188032@qq.com) |
| WeChat group | Scan the QR code (it expires; use QQ / email if needed) |

<img src="site/assets/wechat-group-qr.png" alt="WeChat group QR code" width="180" />

## License

This project is licensed under the [MIT License](LICENSE).

Edit Studio–related code is based on **OpenCut**. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [`apps/web/src/editor/opencut/LICENSE`](apps/web/src/editor/opencut/LICENSE).

When using cloud LLM, image, or TTS providers, also follow their respective terms of service.
