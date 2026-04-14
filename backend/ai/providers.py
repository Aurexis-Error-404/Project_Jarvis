# providers.py - JARVIS AI Provider Configuration
#
# MODE LOGIC:
#   mode="cloud" -> task-routed between Gemini + Groq
#                  error_diagnosis + research_report -> Gemini
#                  everything else                   -> Groq
#
#   mode="local" -> Ollama only (codellama or OLLAMA_MODEL from env)
#                  zero bytes leave the machine
#                  this is the SECURE MODE the user toggles in UI

import os


def _build_providers() -> dict:
    """Build provider config lazily so env vars are read after load_dotenv()."""
    return {
        "gemini": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "api_key": os.getenv("GEMINI_API_KEY"),
            "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash-preview-04-17"),
            "context_window": 1_000_000,
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": os.getenv("GROQ_API_KEY"),
            "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "context_window": 128_000,
        },
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "api_key": "ollama",
            "model": os.getenv("OLLAMA_MODEL", "codellama"),
            "context_window": 32_000,
        },
    }


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

CLOUD_TASK_ROUTING = {
    "error_diagnosis": "gemini",
    "research_report": "gemini",
    "git_summary": "groq",
    "commit_message": "groq",
    "session_summary": "groq",
    "quick_qa": "groq",
    "read_codebase": "groq",
    "read_git_history": "groq",
    "read_session": "groq",
    "update_memory": "groq",
    "proactive_surface": "groq",
    "proactive_gate": "ollama",
}

CLOUD_FALLBACK = {
    "gemini": "groq",
    "groq": None,
}


def get_provider(task_type: str, mode: str) -> str:
    if mode == "local":
        return "ollama"
    return CLOUD_TASK_ROUTING.get(task_type, "groq")


def get_fallback(provider_name: str, mode: str):
    if mode == "local":
        return None
    return CLOUD_FALLBACK.get(provider_name)


def validate_providers() -> None:
    import logging

    logger = logging.getLogger("jarvis.providers")
    cloud_providers = ("gemini", "groq")
    missing = [name for name in cloud_providers if not _get_providers()[name]["api_key"]]

    if not missing:
        logger.info("Provider validation passed - Gemini and Groq API keys present")
        return

    for name in missing:
        env_var = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY"}[name]
        logger.warning(
            f"Provider '{name}' has no API key - set {env_var} in .env. "
            f"Cloud mode will skip {name} and use its fallback."
        )
