"""Tier 3 computer automation — pyautogui wrapper (§7.2).

Off by default: `COMPUTER_AUTOMATION_ENABLED=1` to opt in. Every call is
expected to already have consent from the dispatcher's `_pre_tool_check`
hook — the tool itself does not re-prompt. If `pyautogui` is not
installed the tool fails closed (returns an error dict, never raises).

Linux/Wayland caveat: pyautogui is flaky outside X11. Document on first
failure; never silently fall back.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger("jarvis.computer_automation")

COMPUTER_AUTOMATION_ENABLED: bool = os.environ.get("COMPUTER_AUTOMATION_ENABLED", "0").lower() in (
    "1", "true", "yes",
)

_ALLOWED_ACTIONS = {"screenshot", "click", "type", "key", "move"}

try:
    import pyautogui  # type: ignore
    _PYAUTOGUI_OK = True
except Exception as _e:  # noqa: BLE001
    pyautogui = None  # type: ignore[assignment]
    _PYAUTOGUI_OK = False
    _IMPORT_ERROR = str(_e)


def _screenshot_path() -> str:
    from backend.context.workspace import current_path
    out = os.path.join(current_path(), ".claude", "temp", "screenshots")
    os.makedirs(out, exist_ok=True)
    return os.path.join(out, f"shot_{int(time.time() * 1000)}.png")


def run(action: str, **kwargs) -> dict:
    """Synchronous entry point; dispatcher runs it in a thread."""
    if not COMPUTER_AUTOMATION_ENABLED:
        return {"error": "computer automation disabled (set COMPUTER_AUTOMATION_ENABLED=1 to enable)"}
    if not _PYAUTOGUI_OK:
        return {"error": f"pyautogui unavailable: {_IMPORT_ERROR}"}
    if action not in _ALLOWED_ACTIONS:
        return {"error": f"unsupported action: {action!r}"}

    try:
        if action == "screenshot":
            path = _screenshot_path()
            pyautogui.screenshot(path)
            return {"ok": True, "path": path}

        if action == "click":
            x = int(kwargs["x"]); y = int(kwargs["y"])
            button = kwargs.get("button", "left")
            pyautogui.click(x=x, y=y, button=button)
            return {"ok": True, "clicked": {"x": x, "y": y, "button": button}}

        if action == "type":
            text = str(kwargs.get("text", ""))
            interval = float(kwargs.get("interval", 0.02))
            pyautogui.typewrite(text, interval=interval)
            return {"ok": True, "typed_chars": len(text)}

        if action == "key":
            key = str(kwargs["key"])
            pyautogui.press(key)
            return {"ok": True, "key": key}

        if action == "move":
            x = int(kwargs["x"]); y = int(kwargs["y"])
            duration = float(kwargs.get("duration", 0.15))
            pyautogui.moveTo(x, y, duration=duration)
            return {"ok": True, "moved_to": {"x": x, "y": y}}

    except KeyError as e:
        return {"error": f"missing required parameter: {e}"}
    except Exception as e:
        logger.exception("computer_automation failed")
        return {"error": f"{action} failed: {e}"}

    return {"error": "unreachable"}
