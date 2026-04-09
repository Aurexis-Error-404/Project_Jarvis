"""
Proactive file watcher — monitors PROJECT_PATH for file changes,
runs the Ollama gate, and sends context_surface events to the frontend
when the gate confidence meets the threshold.

Highest-risk feature in Phase 1. Build last. Keep the gate call minimal.

Debounce: 5 seconds minimum between events for the same file (locked rule).
Threshold: OLLAMA_GATE_THRESHOLD env var (default 0.7).
"""

import asyncio
import logging
import os
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.ai import ollama_client
from backend.memory.jarvis_json import read as read_jarvis

logger = logging.getLogger("jarvis.file_watcher")

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "dist", "build"}
DEBOUNCE_SECONDS = 5  # locked — do not reduce


class JarvisHandler(FileSystemEventHandler):
    def __init__(self, loop: asyncio.AbstractEventLoop, send_event):
        super().__init__()
        self.loop = loop
        self.send_event = send_event
        self._last_event: dict[str, float] = {}

    def on_modified(self, event):
        if event.is_directory:
            return
        path = event.src_path
        if any(skip in path for skip in SKIP_DIRS):
            return

        now = time.monotonic()
        if now - self._last_event.get(path, 0) < DEBOUNCE_SECONDS:
            return  # debounce — skip this event
        self._last_event[path] = now

        asyncio.run_coroutine_threadsafe(self._evaluate(path), self.loop)

    on_created = on_modified  # surface on new files too

    async def _evaluate(self, path: str):
        try:
            jarvis = read_jarvis()
            focus = jarvis.get("project", {}).get("current_focus", "")
            threshold = float(os.environ.get("OLLAMA_GATE_THRESHOLD", "0.7"))

            result = await ollama_client.gate("file_modified", path, focus)

            should_surface = result.get("should_surface", False)
            confidence = result.get("confidence", 0.0)

            logger.debug(f"Gate: {path} → surface={should_surface}, confidence={confidence:.2f}")

            if should_surface and confidence >= threshold:
                await self.send_event(
                    {
                        "event": "context_surface",
                        "file": path.replace("\\", "/"),
                        "reason": result.get("reason", "File modified — may affect active session"),
                        "confidence": confidence,
                    }
                )

        except Exception as e:
            logger.error(f"File watcher _evaluate error for {path}: {e}")


async def start(send_event):
    """
    Start the file watcher. Call from main.py lifespan after WebSocket is up.
    send_event: async callable that sends events to connected WebSocket clients.
    """
    project_path = os.environ.get("PROJECT_PATH", ".")
    loop = asyncio.get_event_loop()

    handler = JarvisHandler(loop=loop, send_event=send_event)
    observer = Observer()
    observer.schedule(handler, path=project_path, recursive=True)
    observer.start()
    logger.info(f"File watcher started on: {project_path}")

    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("File watcher stopping...")
    finally:
        observer.stop()
        observer.join()
        logger.info("File watcher stopped.")
