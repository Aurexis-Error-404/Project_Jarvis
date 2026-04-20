"""
Proactive file watcher — monitors the active project path for file changes,
runs the Ollama gate, and sends jarvis_surface events to the frontend
when the gate confidence meets the threshold.

Highest-risk feature in Phase 1. Build last. Keep the gate call minimal.

Debounce: 5 seconds minimum between events for the same file (locked rule).
Threshold: OLLAMA_GATE_THRESHOLD env var (default 0.7).
"""

import asyncio
import logging
import os
import time
from pathlib import Path, PurePath
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.ai import ollama_client
from backend.memory.jarvis_json import read as read_jarvis

logger = logging.getLogger("jarvis.file_watcher")

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "dist", "build", ".agents", ".claude"}
DEBOUNCE_SECONDS = 5  # locked — do not reduce
GLOBAL_COOLDOWN = int(os.environ.get("SURFACE_COOLDOWN", "60"))

# Cap on _last_event dict to prevent unbounded memory growth on long-running servers
_MAX_TRACKED_PATHS = 500


class JarvisHandler(FileSystemEventHandler):
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        send_event: Callable,
        get_mode: Callable[[], str],
        threshold: float,
    ):
        super().__init__()
        self.loop = loop
        self.send_event = send_event
        self.get_mode = get_mode          # callable: () -> "local" | "cloud"
        self.threshold = threshold        # cached at startup — avoids env lookup per event
        self._last_event: dict = {}
        self._last_surface_time: float = 0.0

    def on_modified(self, event):
        if event.is_directory:
            return
        path = event.src_path
        if any(skip in PurePath(path).parts for skip in SKIP_DIRS):
            return

        now = time.monotonic()
        if now - self._last_event.get(path, 0) < DEBOUNCE_SECONDS:
            return  # debounce — skip this event
        self._last_event[path] = now

        # Evict oldest entries if dict grows too large
        if len(self._last_event) > _MAX_TRACKED_PATHS:
            oldest = min(self._last_event, key=self._last_event.__getitem__)
            del self._last_event[oldest]

        asyncio.run_coroutine_threadsafe(self._evaluate(path), self.loop)

    on_created = on_modified  # surface on new files too

    async def _evaluate(self, path: str):
        try:
            jarvis = read_jarvis()
            focus = jarvis.get("project", {}).get("current_focus", "")

            ext = PurePath(path).suffix or "unknown"
            last_surfaced_ago = int((time.monotonic() - self._last_surface_time) / 60) if self._last_surface_time else 999
            recent = ", ".join(list(self._last_event.keys())[-5:])

            result = await ollama_client.gate(
                "file_modified", path, focus,
                file_extension=ext,
                last_surfaced_minutes=last_surfaced_ago,
                recent_files=recent,
            )

            should_surface = result.get("should_surface", False)
            confidence = result.get("confidence", 0.0)
            reason = result.get("reason", "File modified — may affect active session")

            logger.debug(
                f"Gate: {path} → surface={should_surface}, confidence={confidence:.2f}"
            )

            if not (should_surface and confidence >= self.threshold):
                return  # gate did not pass — nothing to do

            # Global cooldown — prevent surface card storms
            now_surface = time.monotonic()
            if now_surface - self._last_surface_time < GLOBAL_COOLDOWN:
                logger.debug(f"Global cooldown active — skipping surface for {path}")
                return

            # Gate passed — generate surface card bullets (lazy import avoids circular deps)
            from backend.ai.surface_generator import generate as generate_surface

            mode = self.get_mode()
            bullets = await generate_surface(
                file_path=path,
                gate_reason=reason,
                mode=mode,
            )

            if not bullets:
                logger.warning(
                    f"No bullets generated for {path} — suppressing jarvis_surface event"
                )
                return  # better silent than a broken card

            await self.send_event({
                "event": "jarvis_surface",
                "file": path.replace("\\", "/"),
                "reason": reason,
                "confidence": confidence,
                "bullets": bullets,
            })
            self._last_surface_time = time.monotonic()

        except Exception as e:
            logger.error(f"File watcher _evaluate error for {path}: {e}")


async def start(send_event: Callable, get_mode: Callable[[], str] = None,
                get_project_path: Callable[[], str] = None):
    """
    Start the file watcher. Call from main.py lifespan after WebSocket is up.

    send_event: async callable that fans out events to all connected clients.
    get_mode:   callable returning current AI mode ("local" | "cloud").
                Defaults to reading AI_MODE env var if not provided.
    get_project_path:
                callable returning the project root to watch. Defaults to the
                repo root (or PROJECT_PATH env var if provided).
    """
    if get_mode is None:
        def get_mode():
            return os.environ.get("AI_MODE", "local")
    if get_project_path is None:
        def get_project_path():
            return os.environ.get("PROJECT_PATH", str(Path(__file__).parent.parent.parent))

    project_path = str(Path(get_project_path()).resolve())
    threshold = float(os.environ.get("OLLAMA_GATE_THRESHOLD", "0.7"))
    loop = asyncio.get_running_loop()  # get_event_loop() deprecated in Python 3.10+

    handler = JarvisHandler(
        loop=loop,
        send_event=send_event,
        get_mode=get_mode,
        threshold=threshold,
    )
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
