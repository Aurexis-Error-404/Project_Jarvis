import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import websockets
from dotenv import load_dotenv
from fastapi import FastAPI

from backend.ai.claude_client import run as claude_run

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent / "logs" / "error.log"),
    ],
)
logger = logging.getLogger("jarvis.main")

connected_clients: set = set()

# Persists for the process lifetime; updated on mode_change events.
_current_mode: str = os.environ.get("AI_MODE", "local")

# Populated once when the first client connects (codebase awareness).
_codebase_map: str = "Codebase not yet read. Call read_codebase('.') to load."
_codebase_loaded: bool = False
_codebase_lock = asyncio.Lock()


async def broadcast_event(payload: dict):
    """Send an event to ALL currently connected WebSocket clients."""
    if not connected_clients:
        return
    message = json.dumps(payload)
    dead: set = set()
    for ws in connected_clients:
        try:
            await ws.send(message)
        except Exception as e:
            logger.warning(f"broadcast_event failed for a client: {e}")
            dead.add(ws)
    connected_clients.difference_update(dead)


async def _load_codebase_map() -> str:
    """
    Scan the project directory at session start for codebase awareness.
    Uses codebase_reader — no AI call, just file listing.
    """
    from backend.tools.codebase_reader import run as read_codebase
    result = read_codebase(".")
    if "error" in result:
        logger.warning(f"Codebase scan failed: {result['error']}")
        return "Codebase scan failed. Call read_codebase('.') to retry."
    files = result.get("files", [])
    count = result.get("count", len(files))
    file_list = "\n".join(f"  {f}" for f in files)
    logger.info(f"Codebase map loaded: {count} files")
    return f"Project files ({count} total):\n{file_list}"


async def ws_handler(websocket):
    global _current_mode, _codebase_map, _codebase_loaded

    connected_clients.add(websocket)
    logger.info(f"Client connected. Total: {len(connected_clients)}")

    # Codebase awareness — scan once on first connection (guarded against races)
    async with _codebase_lock:
        if not _codebase_loaded:
            _codebase_loaded = True
            _codebase_map = await _load_codebase_map()

    async def send_event(payload: dict):
        try:
            await websocket.send(json.dumps(payload))
        except Exception as e:
            logger.warning(f"Failed to send event: {e}")

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                event_type = data.get("event", "")

                # ── user_query: route to AI ───────────────────────────────
                if event_type == "user_query":
                    query = data.get("query", "").strip()
                    mode = data.get("mode", _current_mode)

                    if not query:
                        await send_event({
                            "event": "jarvis_error",
                            "message": "Empty query",
                            "recoverable": True,
                        })
                        continue

                    await send_event({"event": "status_update", "message": "Thinking..."})

                    await claude_run(
                        query=query,
                        mode=mode,
                        send_event=send_event,
                        codebase_map=_codebase_map,
                    )

                # ── mode_change: update global mode, acknowledge ──────────
                elif event_type == "mode_change":
                    new_mode = data.get("mode", "").strip()
                    if new_mode not in ("local", "cloud"):
                        await send_event({
                            "event": "jarvis_error",
                            "message": f"Invalid mode '{new_mode}'. Expected 'local' or 'cloud'.",
                            "recoverable": True,
                        })
                        continue
                    _current_mode = new_mode
                    logger.info(f"Mode changed to: {_current_mode}")
                    await send_event({"event": "jarvis_mode_ack", "mode": _current_mode})

                # ── surface_dismissed: log only ───────────────────────────
                elif event_type == "surface_dismissed":
                    logger.info(f"Surface dismissed: {data.get('file', 'unknown')}")

                # ── legacy / no event field: backwards-compat fallback ────
                else:
                    query = data.get("query", "").strip()
                    if query:
                        mode = data.get("mode", _current_mode)
                        logger.warning("Message has no event field — treating as user_query")
                        await send_event({"event": "status_update", "message": "Thinking..."})
                        await claude_run(
                            query=query,
                            mode=mode,
                            send_event=send_event,
                            codebase_map=_codebase_map,
                        )
                    else:
                        await send_event({
                            "event": "jarvis_error",
                            "message": f"Unrecognised event: '{event_type}'",
                            "recoverable": True,
                        })

            except json.JSONDecodeError:
                await send_event({
                    "event": "jarvis_error",
                    "message": "Invalid JSON payload",
                    "recoverable": True,
                })
            except Exception as e:
                logger.exception(f"Error handling message: {e}")
                await send_event({
                    "event": "jarvis_error",
                    "message": str(e),
                    "recoverable": False,
                })
    finally:
        connected_clients.discard(websocket)
        logger.info(f"Client disconnected. Total: {len(connected_clients)}")


async def start_ws_server():
    port = int(os.environ.get("WS_PORT", 8765))
    logger.info(f"WebSocket server starting on ws://localhost:{port}")
    async with websockets.serve(ws_handler, "localhost", port):
        await asyncio.Future()  # run forever


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ws_task = asyncio.create_task(start_ws_server())
    from backend.context.file_watcher import start as start_watcher
    watcher_task = asyncio.create_task(
        start_watcher(broadcast_event, get_mode=lambda: _current_mode)
    )
    yield
    watcher_task.cancel()
    ws_task.cancel()
    from backend.ai.ollama_client import close as close_ollama
    await close_ollama()


app = FastAPI(title="JARVIS Backend", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "connected_clients": len(connected_clients),
        "mode": _current_mode,
        "codebase_loaded": _codebase_loaded,
    }
