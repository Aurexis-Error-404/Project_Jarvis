import asyncio
import datetime
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
_codebase_ready: asyncio.Event = None  # initialized in ws_handler (needs running loop)


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


async def _load_codebase_map_async():
    """Non-blocking codebase loader — updates global without blocking ws_handler."""
    global _codebase_map
    try:
        _codebase_map = await _load_codebase_map()
    except Exception as e:
        logger.error(f"Async codebase load failed: {e}")
    finally:
        if _codebase_ready is not None:
            _codebase_ready.set()


async def ws_handler(websocket):
    global _current_mode, _codebase_map, _codebase_loaded, _codebase_ready

    if _codebase_ready is None:
        _codebase_ready = asyncio.Event()

    connected_clients.add(websocket)
    session_msg_count = 0
    session_history: list = []  # per-connection conversation memory
    logger.info(f"Client connected. Total: {len(connected_clients)}")

    # Codebase awareness — scan once on first connection (non-blocking)
    async with _codebase_lock:
        if not _codebase_loaded:
            _codebase_loaded = True
            # Fire and forget — don't block the first message
            asyncio.create_task(_load_codebase_map_async())

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
                    session_msg_count += 1
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

                    # Wait for codebase map to load (max 5s)
                    if _codebase_ready and not _codebase_ready.is_set():
                        try:
                            await asyncio.wait_for(_codebase_ready.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            logger.warning("Codebase map not ready after 5s — proceeding without it")

                    response_text = await claude_run(
                        query=query,
                        mode=mode,
                        send_event=send_event,
                        codebase_map=_codebase_map,
                        history=list(session_history),
                    )
                    # Accumulate conversation for session memory (cap at 20 exchanges)
                    session_history.append({"role": "user", "content": query})
                    session_history.append({"role": "assistant", "content": response_text or ""})
                    if len(session_history) > 40:
                        session_history = session_history[-40:]

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

                # ── demo_surface: failsafe trigger for demo ──────────────
                elif event_type == "demo_surface":
                    await send_event({
                        "event": "jarvis_surface",
                        "file": "demo/trigger",
                        "reason": "Demo trigger",
                        "confidence": 1.0,
                        "bullets": [
                            "\u2022 Provider fallback chain verified — Gemini \u2192 Groq \u2192 Ollama",
                            "\u2022 file_watcher debounce active at 5s per-file, 60s global cooldown",
                            "\u2022 jarvis.json decisions tracking 3 locked architectural choices",
                        ],
                    })

                # ── set_project_path: change the watched codebase ────────
                elif event_type == "set_project_path":
                    new_path = data.get("path", "").strip()
                    if not new_path or not os.path.isdir(new_path):
                        await send_event({
                            "event": "jarvis_error",
                            "message": f"Invalid project path: {new_path}",
                            "recoverable": True,
                        })
                        continue
                    # Reload codebase map for new path
                    from backend.tools.codebase_reader import run as read_codebase
                    result = read_codebase(new_path)
                    if "error" not in result:
                        files = result.get("files", [])
                        count = result.get("count", len(files))
                        file_list = "\n".join(f"  {f}" for f in files)
                        _codebase_map = f"Project files ({count} total):\n{file_list}"
                    os.environ["PROJECT_PATH"] = new_path
                    logger.info(f"Project path changed to: {new_path}")
                    await send_event({
                        "event": "project_path_ack",
                        "path": new_path,
                        "files_loaded": result.get("count", 0) if "error" not in result else 0,
                    })

                # ── legacy / no event field: backwards-compat fallback ────
                else:
                    query = data.get("query", "").strip()
                    if query:
                        mode = data.get("mode", _current_mode)
                        logger.warning("Message has no event field — treating as user_query")
                        await send_event({"event": "status_update", "message": "Thinking..."})
                        response_text = await claude_run(
                            query=query,
                            mode=mode,
                            send_event=send_event,
                            codebase_map=_codebase_map,
                            history=list(session_history),
                        )
                        session_history.append({"role": "user", "content": query})
                        session_history.append({"role": "assistant", "content": response_text or ""})
                        if len(session_history) > 40:
                            session_history = session_history[-40:]
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
        # Auto-log session on disconnect
        if session_msg_count > 0:
            try:
                from backend.memory.jarvis_json import update as update_jarvis
                update_jarvis("session_log", "append", {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "messages": session_msg_count,
                    "mode": _current_mode,
                })
            except Exception as e:
                logger.warning(f"Failed to log session: {e}")
        logger.info(f"Client disconnected. Total: {len(connected_clients)}")


async def start_ws_server():
    port = int(os.environ.get("WS_PORT", 8765))
    logger.info(f"WebSocket server starting on ws://localhost:{port}")
    async with websockets.serve(ws_handler, "localhost", port):
        await asyncio.Future()  # run forever


async def _warm_up_gemini():
    """Prime Gemini's internal cache with a minimal call."""
    try:
        from backend.ai.claude_client import _call_with_fallback
        await _call_with_fallback(
            task_type="quick_qa", mode="cloud",
            messages=[
                {"role": "system", "content": "You are JARVIS."},
                {"role": "user", "content": "ready"},
            ],
            max_tokens=5,
        )
        logger.info("Gemini warm-up complete")
    except Exception as e:
        logger.warning(f"Gemini warm-up failed (non-blocking): {e}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ws_task = asyncio.create_task(start_ws_server())
    from backend.context.file_watcher import start as start_watcher
    watcher_task = asyncio.create_task(
        start_watcher(broadcast_event, get_mode=lambda: _current_mode)
    )
    # Non-blocking warm-up for Gemini cache
    asyncio.create_task(_warm_up_gemini())
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
