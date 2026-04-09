# providers.py — JARVIS AI Provider Configuration
#
# MODE LOGIC:
#   mode="cloud" → task-routed between Gemini + Groq
#                  error_diagnosis + research_report → Gemini
#                  everything else                   → Groq
#
#   mode="local" → Ollama only (qwen3.5:cloud or OLLAMA_MODEL from env)
#                  zero bytes leave the machine
#                  this is the SECURE MODE the user toggles in UI

import os


def _build_providers() -> dict:
    """Build provider config lazily so env vars are read after load_dotenv()."""
    return {
        "gemini": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "api_key":  os.getenv("GEMINI_API_KEY"),
            "model":    os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            "context_window": 1_000_000,
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key":  os.getenv("GROQ_API_KEY"),
            "model":    os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "context_window": 128_000,
        },
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "api_key":  "ollama",
            "model":    os.getenv("OLLAMA_MODEL", "qwen3.5:cloud"),  # local secure mode model
            "context_window": 32_000,
        },
    }


# Lazy singleton — populated on first access (after load_dotenv has run)
_providers_cache: dict | None = None


def _get_providers() -> dict:
    global _providers_cache
    if _providers_cache is None:
        _providers_cache = _build_providers()
    return _providers_cache


class _ProvidersProxy:
    """Dict-like proxy that defers env var reads until first access."""
    def __getitem__(self, key):
        return _get_providers()[key]
    def __contains__(self, key):
        return key in _get_providers()
    def get(self, key, default=None):
        return _get_providers().get(key, default)
    def __iter__(self):
        return iter(_get_providers())
    def keys(self):
        return _get_providers().keys()
    def values(self):
        return _get_providers().values()
    def items(self):
        return _get_providers().items()


PROVIDERS = _ProvidersProxy()

# Cloud mode: which tasks go to Gemini vs Groq
CLOUD_TASK_ROUTING = {
    # Gemini — quality-critical only (saves your 20 RPD free limit)
    "error_diagnosis":   "gemini",
    "research_report":   "gemini",

    # Groq — everything else (14,400 RPD, use freely)
    "git_summary":       "groq",
    "commit_message":    "groq",
    "session_summary":   "groq",
    "quick_qa":          "groq",
    "read_codebase":     "groq",
    "read_git_history":  "groq",
    "read_session":      "groq",
    "update_memory":     "groq",
    "proactive_surface": "groq",

    # Proactive gate is ALWAYS Ollama regardless of mode
    # (runs 50+ times/hour — never use cloud for this)
    "proactive_gate":    "ollama",
}

# Fallback chain within cloud mode
CLOUD_FALLBACK = {
    "gemini": "groq",   # Gemini rate-limited → fall to Groq
    "groq":   None,     # Groq fails → surface error (don't fall to Ollama in cloud mode)
}


def get_provider(task_type: str, mode: str) -> str:
    """
    Returns the provider name for a given task and mode.

    mode="local"  → always Ollama (secure mode — user toggled the badge)
    mode="cloud"  → CLOUD_TASK_ROUTING table (Gemini or Groq based on task)
    """
    if mode == "local":
        return "ollama"

    # Cloud mode — proactive_gate always Ollama even here
    return CLOUD_TASK_ROUTING.get(task_type, "groq")  # default to Groq


def get_fallback(provider_name: str, mode: str):
    """
    Returns fallback provider name for cloud mode, or None.
    Local mode has no fallback — Ollama is the only option.
    """
    if mode == "local":
        return None
    return CLOUD_FALLBACK.get(provider_name)
