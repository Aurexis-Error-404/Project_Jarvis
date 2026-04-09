import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import websockets
from dotenv import load_dotenv
from fastapi import FastAPI

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


async def ws_handler(websocket):
    connected_clients.add(websocket)
    logger.info(f"Client connected. Total: {len(connected_clients)}")

    async def send_event(payload: dict):
        try:
            await websocket.send(json.dumps(payload))
        except Exception as e:
            logger.warning(f"Failed to send event: {e}")

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                query = data.get("query", "")
                mode = data.get("mode", os.environ.get("AI_MODE", "local"))

                if not query:
                    await send_event({"event": "error", "message": "Empty query", "recoverable": True})
                    continue

                await send_event({"event": "status_update", "message": "Thinking..."})

                from backend.ai.claude_client import run as claude_run
                await claude_run(query=query, mode=mode, send_event=send_event)

            except json.JSONDecodeError:
                await send_event({"event": "error", "message": "Invalid JSON payload", "recoverable": True})
            except Exception as e:
                logger.exception(f"Error handling message: {e}")
                await send_event({"event": "error", "message": str(e), "recoverable": False})
    finally:
        connected_clients.discard(websocket)
        logger.info(f"Client disconnected. Total: {len(connected_clients)}")


async def start_ws_server():
    port = int(os.environ.get("WS_PORT", 8765))
    logger.info(f"WebSocket server starting on ws://localhost:{port}")
    async with websockets.serve(ws_handler, "localhost", port):
        await asyncio.Future()  # run forever


@asynccontextmanager
async def lifespan(app: FastAPI):
    ws_task = asyncio.create_task(start_ws_server())
    # File watcher started here once Phase 1 is complete:
    # from backend.context.file_watcher import start as start_watcher
    # watcher_task = asyncio.create_task(start_watcher(broadcast_event))
    yield
    ws_task.cancel()


app = FastAPI(title="JARVIS Backend", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "connected_clients": len(connected_clients)}
