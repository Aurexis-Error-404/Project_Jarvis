"""Secret-redaction helpers for logs, persisted memory, and local storage.

One source of truth for the regex list. Mirror any change here in
`src/hooks/useConversations.js::REDACTION_PATTERNS` (the frontend applies the
same patterns before writing to localStorage).

Design rules — see JARVIS_IMPLEMENTATION_PLAN.md §9:
- Patterns target high-signal prefixes (provider-scoped) before catch-alls.
- Negative corpus covers commit hashes and other base64/hex strings that look
  key-shaped so redaction does not mangle legitimate content.
- `redact_keys` works on a string. `sanitize_for_logging` recursively walks
  dicts/lists so structured log records stay structured.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

# Ordered: provider-specific first, broad last.
# Each entry: (compiled regex, replacement).
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Google / Gemini API keys — start with 'AIza', typically 39 chars total.
    # Use a range to tolerate minor variants across Google services.
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,48}\b"), REDACTED),
    # Anthropic / Claude keys.
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{80,}\b"), REDACTED),
    # OpenAI keys (classic and project-scoped).
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}\b"), REDACTED),
    # Groq keys.
    (re.compile(r"\bgsk_[A-Za-z0-9]{40,}\b"), REDACTED),
    # GitHub personal / fine-grained / app tokens.
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), REDACTED),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b"), REDACTED),
    # AWS access key ID.
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), REDACTED),
    # JWT — three base64url segments joined by dots; require header prefix
    # to avoid eating random.dotted.identifiers.
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"), REDACTED),
    # Generic "KEY=value" / "api_key: value" / "token: value" envs.
    # Only matches when the assignment syntax is present — avoids false
    # positives on bare hex blobs (commit hashes, package hashes, etc.).
    (re.compile(
        r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|authorization|bearer)"
        r"\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{12,})['\"]?"
    ), lambda m: m.group(0).replace(m.group(1), REDACTED)),  # type: ignore[list-item]
]


def redact_keys(text: str) -> str:
    """Replace known key shapes in `text` with `[REDACTED]`.

    Safe on arbitrary input including non-string-convertible junk (caller
    handles `str()` conversion beforehand). Returns text unchanged when no
    pattern fires — the common case stays a no-op.
    """
    if not text or not isinstance(text, str):
        return text
    out = text
    for pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    return out


def sanitize_for_logging(value: Any) -> Any:
    """Recursively walk a structure (dict / list / str / scalar) and redact
    any string leaf. Dict keys are left untouched; only values are scrubbed.
    """
    if isinstance(value, str):
        return redact_keys(value)
    if isinstance(value, dict):
        return {k: sanitize_for_logging(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        cleaned = [sanitize_for_logging(v) for v in value]
        return cleaned if isinstance(value, list) else tuple(cleaned)
    return value
