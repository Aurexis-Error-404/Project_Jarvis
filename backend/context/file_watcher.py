"""
Proactive file watcher — monitors PROJECT_PATH for file changes,
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
from collections import Counter
from pathlib import Path, PurePath
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.ai import ollama_client
from backend.context.project_context import (
    build_runtime_context,
    format_runtime_context,
    get_vault_path,
    invalidate_note_cache,
)
from backend.memory.jarvis_json import read as read_jarvis

logger = logging.getLogger("jarvis.file_watcher")

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "dist", "build", ".agents",
    ".claude", ".obsidian", ".pytest_cache", "raw",
}
DEBOUNCE_SECONDS = 5  # locked — do not reduce
GLOBAL_COOLDOWN = int(os.environ.get("SURFACE_COOLDOWN", "60"))
TEMP_SUFFIXES = {".tmp", ".swp", ".swo", ".bak", ".orig"}
TEMP_NAME_PARTS = (".tmp.",)

# Cap on _last_event dict to prevent unbounded memory growth on long-running servers
_MAX_TRACKED_PATHS = 500


def _classify_signal(path: str) -> str | None:
    pure = PurePath(path)
    suffix = pure.suffix.lower()
    parts = {part.lower() for part in pure.parts}
    if any(skip.lower() in parts for skip in SKIP_DIRS):
        return None
    if suffix in TEMP_SUFFIXES or any(part.endswith(tuple(TEMP_SUFFIXES)) for part in pure.parts):
        return None
    if any(marker in pure.name for marker in TEMP_NAME_PARTS):
        return None
    if "wiki" in parts and suffix == ".md":
        return "wiki_note"
    if suffix == ".md":
        return None
    return "code_change"


def _context_query_for_signal(path: str, signal_type: str) -> str:
    stem = Path(path).stem.replace("-", " ").replace("_", " ")
    if signal_type == "wiki_note":
        return f"{stem} project context"
    return f"{Path(path).name} implementation context"


# Module boundary names used to identify which area of the project is active
_MODULE_ROOTS = {"backend", "src", "wiki", "electron", "tests", "frontend"}


def _derive_activity_focus(recent_paths: list[str]) -> str:
    """Infer the active work area from recently-touched file paths.

    Looks for a common module directory (e.g. backend/context/) among the last
    few files.  Returns a short hint string — or an empty string when the paths
    are too scattered to form a meaningful signal.
    """
    if len(recent_paths) < 2:
        return ""

    modules: list[str] = []
    for p in recent_paths:
        parts = PurePath(p).parts
        for i, part in enumerate(parts):
            if part.lower() in _MODULE_ROOTS:
                # Grab up to two levels: e.g. "backend/context"
                sub = "/".join(parts[i: i + 2]) if i + 1 < len(parts) else part
                modules.append(sub)
                break

    if not modules:
        return ""

    top_module, count = Counter(modules).most_common(1)[0]
    if count >= 2:
        return f"Active area: {top_module}/ ({count} recent edits)"
    return ""


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
        # Per-file surface timestamps for adaptive cooldown
        self._last_surface_by_file: dict[str, float] = {}

    def on_modified(self, event):
        if event.is_directory:
            return
        path = event.src_path
        if _classify_signal(path) is None:
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
            signal_type = _classify_signal(path)
            if signal_type is None:
                return

            # Wiki note saved: flush the 60s cache so context reflects the change
            if signal_type == "wiki_note":
                invalidate_note_cache()

            jarvis = read_jarvis()
            stated_focus = jarvis.get("project", {}).get("current_focus", "")

            # Derive activity focus from recent file edits and combine with stated focus
            recent_paths = list(self._last_event.keys())[-5:]
            activity_hint = _derive_activity_focus(recent_paths)
            combined_focus = f"{stated_focus} | {activity_hint}" if activity_hint else stated_focus

            context_bundle = build_runtime_context(
                query=_context_query_for_signal(path, signal_type)
            )
            context_summary = format_runtime_context(context_bundle)

            ext = PurePath(path).suffix or "unknown"
            last_surfaced_ago = int((time.monotonic() - self._last_surface_time) / 60) if self._last_surface_time else 999
            recent = ", ".join(recent_paths)

            # Build recently-dismissed list for gate feedback loop (30-min window)
            dismissed_entries = jarvis.get("dismissed_surfaces", [])
            cutoff = time.time() - 1800
            recently_dismissed_files = []
            for entry in dismissed_entries[-20:]:
                try:
                    import datetime as _dt
                    ts = _dt.datetime.fromisoformat(entry.get("timestamp", "")).timestamp()
                    if ts > cutoff:
                        recently_dismissed_files.append(entry.get("file", ""))
                except Exception:
                    pass
            recently_dismissed = ", ".join(f for f in recently_dismissed_files if f) or "none"

            result = await ollama_client.gate(
                signal_type, path, combined_focus,
                file_extension=ext,
                last_surfaced_minutes=last_surfaced_ago,
                recent_files=recent,
                context_summary=context_summary,
                recently_dismissed=recently_dismissed,
            )

            should_surface = result.get("should_surface", False)
            confidence = result.get("confidence", 0.0)
            reason = result.get("reason", "File modified — may affect active session")

            logger.debug(
                f"Gate: {path} → surface={should_surface}, confidence={confidence:.2f}"
            )

            if not (should_surface and confidence >= self.threshold):
                return  # gate did not pass — nothing to do

            # Adaptive cooldown: per-file, shaped by confidence and dismissal history
            file_norm = path.replace("\\", "/")
            file_dismissals = sum(
                1 for d in dismissed_entries
                if d.get("file", "").replace("\\", "/") == file_norm
            )
            if file_dismissals >= 2:
                file_cooldown = 300   # 5 min — user kept dismissing this file
            elif confidence > 0.9:
                file_cooldown = 30    # very high confidence — resurface sooner
            else:
                file_cooldown = GLOBAL_COOLDOWN  # standard 60 s

            now_surface = time.monotonic()
            last_for_file = self._last_surface_by_file.get(path, 0.0)
            if now_surface - last_for_file < file_cooldown:
                logger.debug(
                    f"Adaptive cooldown ({file_cooldown}s) active for {path}"
                )
                return

            # Gate passed — generate surface card bullets (lazy import avoids circular deps)
            from backend.ai.surface_generator import generate as generate_surface

            mode = self.get_mode()
            bullets = await generate_surface(
                file_path=path,
                gate_reason=reason,
                mode=mode,
                signal_type=signal_type,
                context_summary=context_summary,
                activity_focus=activity_hint,
            )

            if not bullets:
                logger.warning(
                    f"No bullets generated for {path} — suppressing jarvis_surface event"
                )
                return  # better silent than a broken card

            await self.send_event({
                "event": "jarvis_surface",
                "file": path.replace("\\", "/"),
                "signal_type": signal_type,
                "reason": reason,
                "confidence": confidence,
                "bullets": bullets,
            })

            now_done = time.monotonic()
            self._last_surface_time = now_done
            self._last_surface_by_file[path] = now_done
            # Cap per-file dict to prevent unbounded growth
            if len(self._last_surface_by_file) > _MAX_TRACKED_PATHS:
                oldest = min(self._last_surface_by_file, key=self._last_surface_by_file.__getitem__)
                del self._last_surface_by_file[oldest]

        except Exception as e:
            logger.error(f"File watcher _evaluate error for {path}: {e}")


async def start(send_event: Callable, get_mode: Callable[[], str] = None):
    """
    Start the file watcher. Call from main.py lifespan after WebSocket is up.

    send_event: async callable that fans out events to all connected clients.
    get_mode:   callable returning current AI mode ("local" | "cloud").
                Defaults to reading AI_MODE env var if not provided.
    """
    if get_mode is None:
        def get_mode():
            return os.environ.get("AI_MODE", "local")

    _default_path = str(Path(__file__).parent.parent.parent)
    project_path = os.environ.get("PROJECT_PATH", _default_path)
    os.environ.setdefault("VAULT_PATH", str(get_vault_path()))
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
