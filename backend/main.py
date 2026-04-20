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

# Process-wide default only — NEVER mutated by handlers. Each WebSocket connection
# owns its own mode in a local variable threaded through _handle_* callables.
# See JARVIS_IMPLEMENTATION_PLAN.md §5.5 (per-session state) and §13.0 (R-5).
_default_mode: str = os.environ.get("AI_MODE", "local")
_default_project_path: str = str(Path(os.environ.get("PROJECT_PATH", ".")).resolve())

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


async def _load_codebase_map(project_path: str | None = None) -> str:
    """
    Scan the project directory at session start for codebase awareness.
    Uses codebase_reader — no AI call, just file listing.
    """
    from backend.tools.codebase_reader import run as read_codebase
    result = read_codebase(".", project_path=project_path)
    if "error" in result:
        logger.warning(f"Codebase scan failed: {result['error']}")
        return "Codebase scan failed. Call read_codebase('.') to retry."
    files = result.get("files", [])
    count = result.get("count", len(files))
    file_list = "\n".join(f"  {f}" for f in files)
    logger.info(f"Codebase map loaded: {count} files")
    return f"Project files ({count} total):\n{file_list}"


async def _load_codebase_map_async(project_path: str | None = None):
    """Non-blocking codebase loader — updates global without blocking ws_handler."""
    global _codebase_map
    try:
        _codebase_map = await _load_codebase_map(project_path=project_path)
    except Exception as e:
        logger.error(f"Async codebase load failed: {e}")
    finally:
        if _codebase_ready is not None:
            _codebase_ready.set()


# ── Per-event handlers (extracted for testability) ───────────────────────────

async def _handle_user_query(data: dict, send_event, session_history: list,
                             session_mode: str, session_project_path: str,
                             session_codebase_map: str | None) -> tuple[list, str]:
    """Handle user_query event. Returns updated session_history + codebase_map."""
    global _codebase_map, _codebase_ready
    query = data.get("query", "").strip()
    mode = data.get("mode", session_mode)

    if not query:
        await send_event({"event": "jarvis_error", "message": "Empty query", "recoverable": True})
        return session_history, (session_codebase_map or _codebase_map)

    await send_event({"event": "status_update", "message": "Thinking..."})

    if _codebase_ready and not _codebase_ready.is_set():
        try:
            await asyncio.wait_for(_codebase_ready.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Codebase map not ready after 5s — proceeding without it")

    if session_codebase_map is None:
        if session_project_path == _default_project_path:
            session_codebase_map = _codebase_map
        else:
            session_codebase_map = await _load_codebase_map(project_path=session_project_path)

    response_text = await claude_run(
        query=query, mode=mode, send_event=send_event,
        codebase_map=session_codebase_map, history=list(session_history),
        project_path=session_project_path,
    )
    session_history.append({"role": "user", "content": query})
    session_history.append({"role": "assistant", "content": response_text or ""})
    if len(session_history) > 40:
        session_history = session_history[-40:]
    return session_history, session_codebase_map


async def _handle_mode_change(data: dict, send_event) -> str | None:
    """Handle mode_change event. Returns the new mode if valid, None on error.

    Per-session: the caller owns the mode variable and assigns from the return value.
    NO process-global mutation — see R-5 (JARVIS_IMPLEMENTATION_PLAN.md §13.0).
    """
    new_mode = data.get("mode", "").strip()
    if new_mode not in ("local", "cloud"):
        await send_event({
            "event": "jarvis_error",
            "message": f"Invalid mode '{new_mode}'. Expected 'local' or 'cloud'.",
            "recoverable": True,
        })
        return None
    logger.info(f"Session mode changed to: {new_mode}")
    await send_event({"event": "jarvis_mode_ack", "mode": new_mode})
    return new_mode


async def _handle_set_project_path(data: dict, send_event) -> tuple[str, str] | None:
    """Handle set_project_path event — return the new project_path + codebase_map."""
    new_path = data.get("path", "").strip()
    if not new_path or not os.path.isdir(new_path):
        await send_event({
            "event": "jarvis_error",
            "message": f"Invalid project path: {new_path}",
            "recoverable": True,
        })
        return None
    resolved_path = str(Path(new_path).resolve())
    from backend.tools.codebase_reader import run as read_codebase
    result = read_codebase(".", project_path=resolved_path)
    codebase_map = _codebase_map
    if "error" not in result:
        files = result.get("files", [])
        count = result.get("count", len(files))
        codebase_map = f"Project files ({count} total):\n" + "\n".join(f"  {f}" for f in files)
    logger.info(f"Session project path changed to: {resolved_path}")
    await send_event({
        "event": "project_path_ack",
        "path": resolved_path,
        "files_loaded": result.get("count", 0) if "error" not in result else 0,
    })
    return resolved_path, codebase_map


async def ws_handler(websocket):
    global _codebase_map, _codebase_loaded, _codebase_ready

    if _codebase_ready is None:
        _codebase_ready = asyncio.Event()

    connected_clients.add(websocket)
    session_msg_count = 0
    session_history: list = []
    # Per-connection mode — seeded from the process default, never written back to it.
    session_mode: str = _default_mode
    session_project_path: str = _default_project_path
    session_codebase_map: str | None = None
    logger.info(f"Client connected. Total: {len(connected_clients)}")

    async with _codebase_lock:
        if not _codebase_loaded:
            _codebase_loaded = True
            asyncio.create_task(_load_codebase_map_async(project_path=_default_project_path))

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

                if event_type == "user_query":
                    session_msg_count += 1
                    session_history, session_codebase_map = await _handle_user_query(
                        data, send_event, session_history, session_mode,
                        session_project_path, session_codebase_map,
                    )

                elif event_type == "mode_change":
                    new_mode = await _handle_mode_change(data, send_event)
                    if new_mode is not None:
                        session_mode = new_mode

                elif event_type == "surface_dismissed":
                    logger.info(f"Surface dismissed: {data.get('file', 'unknown')}")

                elif event_type == "demo_surface":
                    await send_event({
                        "event": "jarvis_surface", "file": "demo/trigger",
                        "reason": "Demo trigger", "confidence": 1.0,
                        "bullets": [
                            "\u2022 Provider fallback chain verified — Gemini \u2192 Groq \u2192 Ollama",
                            "\u2022 file_watcher debounce active at 5s per-file, 60s global cooldown",
                            "\u2022 jarvis.json decisions tracking 3 locked architectural choices",
                        ],
                    })

                elif event_type == "set_project_path":
                    project_state = await _handle_set_project_path(data, send_event)
                    if project_state is not None:
                        session_project_path, session_codebase_map = project_state

                else:
                    query = data.get("query", "").strip()
                    if query:
                        logger.warning("Message has no event field — treating as user_query")
                        session_msg_count += 1
                        data["event"] = "user_query"
                        session_history, session_codebase_map = await _handle_user_query(
                            data, send_event, session_history, session_mode,
                            session_project_path, session_codebase_map,
                        )
                    else:
                        await send_event({
                            "event": "jarvis_error",
                            "message": f"Unrecognised event: '{event_type}'",
                            "recoverable": True,
                        })

            except json.JSONDecodeError:
                await send_event({"event": "jarvis_error", "message": "Invalid JSON payload", "recoverable": True})
            except Exception as e:
                logger.exception(f"Error handling message: {e}")
                await send_event({"event": "jarvis_error", "message": str(e), "recoverable": False})
    finally:
        connected_clients.discard(websocket)
        if session_msg_count > 0:
            try:
                from backend.memory.jarvis_json import update as update_jarvis
                update_jarvis("session_log", "append", {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "messages": session_msg_count,
                    "mode": session_mode,
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
    from backend.ai.providers import validate_providers
    validate_providers()
    ws_task = asyncio.create_task(start_ws_server())
    from backend.context.file_watcher import start as start_watcher
    watcher_task = asyncio.create_task(
        start_watcher(
            broadcast_event,
            get_mode=lambda: _default_mode,
            get_project_path=lambda: _default_project_path,
        )
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
        "default_mode": _default_mode,
        "codebase_loaded": _codebase_loaded,
    }
