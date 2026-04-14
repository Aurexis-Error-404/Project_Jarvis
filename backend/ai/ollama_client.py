"""
Ollama client — local model calls for the proactive gate.
Gate runs 50+ times per hour → must be free and local (never Claude API).

Includes parse_ollama_json() — robust parser for Ollama's sometimes-malformed JSON output.
See prompts/model.md for the gate prompt template and routing rules.
"""

import asyncio
import json
import logging
import os
import re
import time

import httpx

logger = logging.getLogger("jarvis.ollama")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "codellama")
GATE_THRESHOLD = float(os.environ.get("OLLAMA_GATE_THRESHOLD", "0.7"))
GATE_MAX_CONCURRENCY = int(os.environ.get("OLLAMA_GATE_MAX_CONCURRENCY", "1"))
GATE_BACKOFF_SECONDS = float(os.environ.get("OLLAMA_GATE_BACKOFF_SECONDS", "15"))
_gate_backoff_until = 0.0
_gate_semaphore = asyncio.Semaphore(GATE_MAX_CONCURRENCY)

GATE_PROMPT_TEMPLATE = """Respond with ONLY a JSON object. No other text.
No explanation. No code blocks. No markdown. Just JSON.

{{"should_surface": true or false, "confidence": 0.0 to 1.0, "reason": "one sentence max"}}

Rules:
- should_surface true: file is actively being worked on AND relates to current focus
- should_surface false: config file, dependency, test file, file surfaced in last 5 minutes
- should_surface false: file appears in the recently_dismissed list (user already dismissed it)
- confidence above 0.7 required for should_surface true

Signal:
Signal type: {signal_type}
File changed: {file_path}
File type: {file_extension}
Last surfaced: {last_surfaced_minutes} minutes ago
Current project focus: {current_focus}
Recent files touched: {recent_files}
Recently dismissed by user (do not re-surface within 30 min): {recently_dismissed}
Project context hint: {context_summary}

JSON:"""

# Reused across all calls — avoids connection overhead on every gate check
_http = httpx.AsyncClient()


async def close():
    """Close the shared httpx client. Call from app shutdown."""
    await _http.aclose()


def _start_gate_backoff(reason: str) -> None:
    global _gate_backoff_until
    _gate_backoff_until = time.monotonic() + GATE_BACKOFF_SECONDS
    logger.warning(f"Gate backoff active for {int(GATE_BACKOFF_SECONDS)}s: {reason}")


def parse_ollama_json(raw: str) -> dict:
    """
    Robustly parse Ollama gate response — handles markdown code blocks,
    single quotes, trailing commas, and other malformed output.
    """
    # Strip markdown code fences
    raw = re.sub(r"```(?:json)?\n?", "", raw).replace("```", "")
    raw = raw.strip()

    # Find the JSON object
    match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if not match:
        logger.warning(f"No JSON object found in Ollama response: {raw[:200]}")
        return {"should_surface": False, "confidence": 0.0, "reason": "parse failed — no JSON found"}

    json_str = match.group()

    try:
        result = json.loads(json_str)
    except json.JSONDecodeError:
        # Try with single quotes replaced
        try:
            result = json.loads(json_str.replace("'", '"'))
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse Ollama JSON after all attempts: {json_str}")
            return {"should_surface": False, "confidence": 0.0, "reason": "parse failed — invalid JSON"}

    # Clamp confidence to [0.0, 1.0] — CodeLlama can return out-of-range values
    try:
        result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
    except (TypeError, ValueError):
        result["confidence"] = 0.0
    return result


async def gate(signal_type: str, file_path: str, current_focus: str,
               file_extension: str = "", last_surfaced_minutes: int = 999,
               recent_files: str = "", context_summary: str = "",
               recently_dismissed: str = "none") -> dict:
    """
    Run the proactive gate — asks Ollama whether to surface a context card.
    Returns: {"should_surface": bool, "confidence": float, "reason": str}
    """
    if time.monotonic() < _gate_backoff_until:
        return {"should_surface": False, "confidence": 0.0, "reason": "gate backoff active"}

    prompt = GATE_PROMPT_TEMPLATE.format(
        signal_type=signal_type,
        file_path=file_path,
        file_extension=file_extension or os.path.splitext(file_path)[1] or "unknown",
        last_surfaced_minutes=last_surfaced_minutes,
        current_focus=current_focus,
        recent_files=recent_files,
        recently_dismissed=recently_dismissed or "none",
        context_summary=context_summary or "No additional context available.",
    )

    try:
        async with _gate_semaphore:
            r = await _http.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=10.0,
            )
        r.raise_for_status()
        raw_response = r.json().get("response", "")
        result = parse_ollama_json(raw_response)
        logger.debug(f"Gate result for {file_path}: {result}")
        return result

    except httpx.ConnectError:
        logger.warning("Ollama not running — gate defaulting to no-surface")
        return {"should_surface": False, "confidence": 0.0, "reason": "ollama not running"}
    except httpx.TimeoutException as e:
        _start_gate_backoff(f"timeout: {e}")
        return {"should_surface": False, "confidence": 0.0, "reason": "ollama gate timeout"}
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response else "unknown"
        if status_code == 429:
            _start_gate_backoff("ollama rate limited")
            return {"should_surface": False, "confidence": 0.0, "reason": "ollama busy"}
        logger.error(f"Gate HTTP error ({status_code}): {e}")
        return {"should_surface": False, "confidence": 0.0, "reason": f"ollama http error: {status_code}"}
    except Exception as e:
        logger.error(f"Gate error ({type(e).__name__}): {e!r}")
        return {"should_surface": False, "confidence": 0.0, "reason": f"ollama error: {type(e).__name__}"}


async def chat(prompt: str, system: str = "") -> str:
    """
    General-purpose Ollama chat for local/secure mode queries.
    Returns the response text or an error string.
    """
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    if system:
        payload["system"] = system

    try:
        r = await _http.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json().get("response", "")
    except httpx.ConnectError:
        return "Error: Ollama is not running. Start with: ollama serve"
    except Exception as e:
        logger.error(f"Ollama chat error: {e}")
        return f"Error: {e}"
