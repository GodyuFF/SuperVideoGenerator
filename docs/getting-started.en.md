# Getting Started

> Updated: 2026-07-21

Language: [中文](getting-started.md) | **English**

Prefer the **desktop app**. Most people only need the installer; contributors who clone the repo should use the desktop launch scripts at the repository root.

## Path 1: Download the desktop installer (recommended)

For day-to-day use — no need to install Python or Node yourself.

1. Open [GitHub Releases](https://github.com/GodyuFF/SuperVideoGenerator/releases) and download the package for your platform.
2. Install and launch the app following the system prompts.
3. In **AI Settings**, configure API keys for LLM / image / TTS (bring your own keys; settings stay on this machine).

Installers are **unsigned** by default. Windows SmartScreen or macOS Gatekeeper may warn you — that is expected; allow the app when prompted. More detail: [apps/desktop/README.md](../apps/desktop/README.md).

## Path 2: Desktop dev shell from the repo

For contributors or anyone changing the code. Requires **Python 3.11+** and **Node.js 18+** locally (FFmpeg optional).

### One-time setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows; macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cd apps/web && npm install && cd ../..
cp .env.example .env            # optional — you can also set keys later in AI Settings
```

You can also configure keys in the app **AI Settings** page; they persist to `data/ai_config.json` (local only).

### Launch desktop (recommended)

From the repository root:

```bat
launch-desktop.vbs
```

Or with a console log: `launch-desktop.bat`. Alternatively: `cd apps/desktop && npm start`.

The dev shell starts the local API + frontend and opens an Electron window. It does **not** bundle Python/Node — it relies on the environment above. Details: [apps/desktop/README.md](../apps/desktop/README.md).

## Local data (do not commit)

| Path | Contents |
|------|----------|
| `data/` | Projects, scripts, media, chat, AI config |
| `.env` | Environment variables and API keys (if used) |

## Optional: browser dev mode

Only when debugging the Web/API without Electron:

```bash
.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
cd apps/web && npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

## Maintainers: build the installer locally

```powershell
.\apps\desktop\packaging\build-desktop.ps1
```

Artifacts and release flow: [apps/desktop/README.md](../apps/desktop/README.md).

---

Back to [docs index](README.md) · Project intro [README.md](../README.md) / [README.en.md](../README.en.md)
