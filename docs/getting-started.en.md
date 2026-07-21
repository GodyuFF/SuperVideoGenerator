# Getting Started

> Updated: 2026-07-21

Language: [中文](getting-started.md) | **English**

Prefer the **desktop app**. Most people only need the installer; contributors who clone the repo should use the desktop launch scripts at the repository root. After the app is running, jump to **[First use: zero to final cut](#first-use-zero-to-final-cut)**.

## Path 1: Download the desktop installer (recommended)

For day-to-day use — no need to install Python or Node yourself.

1. Open [GitHub Releases](https://github.com/GodyuFF/SuperVideoGenerator/releases) and download the package for your platform.
2. Install and launch the app following the system prompts.
3. Continue with **First use** below; enter API keys in **AI Settings** (bring your own keys; they stay on this machine).

Installers are **unsigned** by default. Windows SmartScreen or macOS Gatekeeper may warn you — that is expected; allow the app when prompted. More detail: [apps/desktop/README.md](../apps/desktop/README.md).

## Path 2: Desktop dev shell from the repo

For contributors or anyone changing the code. Requires **Python 3.11+** and **Node.js 18+** locally (FFmpeg optional).

The virtualenv (`.venv`) is **not** shipped via Git — recreate it after cloning.

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

## First use: zero to final cut

Assumes the app is already open. For the first video, use **Storybook** mode (the default): you only need LLM + image generation + TTS — no AI video API.

### 1. Configure AI (minimum)

1. In the top bar, open **AI Settings**.
2. **LLM**: pick provider and model, enter an API key, enable LLM ReAct, confirm status shows LLM configured.
3. **Image**: keep AI image generation enabled and enter the provider API key.
4. **TTS**: leave the default **edge** (usually no key required).
5. **Video**: leave off for the first run (storybook uses stills; no video model needed).
6. Click **Save and return**.

If keys are missing, the workbench prompts you to configure AI. You can also put keys in a root `.env` (see `.env.example`).

### 2. Create a project and a script

1. On the home page under **My projects**, click **+ New project** to open the project board.
2. Enter a title and click **＋ New script**, then **Open script**.
3. Once inside a script, the left **Chat** panel appears (chat is hidden at project-only level).

### 3. Produce the first video via chat

1. Above the chat: set **视频风格 / Video style** to **故事书模式** (storybook — the default); leave **目标模式** (goal mode: AI runs without confirmation cards) unchecked.
2. Optionally set image style and target duration; **style locks after the first send**.
3. Describe your idea in natural language (topic, audience, length, look) and click **Send**.
4. When a confirmation card appears, choose continue / regenerate / abort; the input stays locked until you answer.
5. Watch **Execution plan** on the right for agent steps: script → storyboard → images → TTS → edit planning.

Goal mode is for batch runs after you know the flow. Leave it off for the first video.

### 4. Review the board and export

1. Use the right-hand tabs (script detail, characters / scenes, storyboard, …) to inspect assets; open a shot to tweak narration or captions.
2. When the plan finishes, open the **Edit** tab to preview the timeline; use **Edit timeline** / **剪辑修改** for multi-track polish.
3. Click **Export** in the Edit tab or studio top bar, pick options, and download the MP4.

Next: try **AI video** or **frame-to-video** after enabling the **Video** tab and adding a video API key.

## Local data (do not commit)

| Path | Contents |
|------|----------|
| `data/` | Projects, scripts, media, chat, AI config |
| `.env` | Environment variables and API keys (if used) |
| `.venv/` | Local Python virtualenv (not in Git — do not commit) |

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
