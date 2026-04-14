# Project Jarvis

JARVIS is an Electron desktop assistant for developer workflows. The app uses a React renderer, a FastAPI backend, a local WebSocket channel, and Ollama/cloud model routing for responses and proactive surfaces.

## Stack

- Desktop shell: Electron
- Frontend: React + esbuild
- Backend: FastAPI + `websockets`
- AI routing: Gemini, Groq, and Ollama
- Project memory: `jarvis.json`
- Project second brain: Obsidian-compatible `wiki/` + `.obsidian/`

## Run

1. Install Node and Python dependencies.
2. Add any needed API keys to `.env`.
3. Start Ollama if you want local mode available.
4. Run `npm start`.

`npm start` now builds the renderer and launches Electron, and Electron will start the FastAPI backend automatically if it is not already running.

## Useful Commands

- `npm run build`
- `npm run watch`
- `python -m pytest -q`
- `python tests/test_ws_client.py`
- `python tests/test_prompt.py`

## Notes

- WebSocket events are stream-first; the active response event is `jarvis_stream_chunk`.
- Reports are written to `reports/`.
- You can override the Python executable Electron uses with `JARVIS_PYTHON`.
- `VAULT_PATH` is optional; if omitted, JARVIS uses `PROJECT_PATH` when that directory contains `.obsidian/` and `wiki/`.
