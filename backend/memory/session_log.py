"""
Session log reader — returns the last N sessions from jarvis.json session_log.

Used by the read_session_history tool to give Claude continuity across days.
"""

import logging

from backend.memory.jarvis_json import read as read_jarvis

logger = logging.getLogger("jarvis.session_log")


def read(last_n_sessions: int = 3) -> dict:
    """
    Returns the last N sessions from jarvis.json session_log.
    last_n_sessions: 1 = "where did we leave off", 3 = weekly summary
    """
    try:
        j = read_jarvis()
        if "error" in j:
            return j

        sessions = j.get("session_log", [])
        recent = sessions[-last_n_sessions:] if sessions else []

        return {
            "sessions": recent,
            "returned": len(recent),
            "total": len(sessions),
        }
    except Exception as e:
        logger.error(f"session_log.read error: {e}")
        return {"error": str(e)}
