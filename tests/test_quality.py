"""Regression corpus for backend/ai/quality.py.

§8.1 requires good/bad pairs. A 'good' response scores at or above
LOW_QUALITY_THRESHOLD; a 'bad' response scores below it.
"""

from backend.ai.quality import LOW_QUALITY_THRESHOLD, is_low_quality, score_response


# ─── Good responses — must NOT be flagged as low quality ────────────────
GOOD_PAIRS = [
    (
        "List the steps to deploy a FastAPI app behind nginx.",
        "Here is a typical deploy flow:\n"
        "1. Package the app with gunicorn + uvicorn workers.\n"
        "2. Configure nginx as a reverse proxy on port 80/443.\n"
        "3. Terminate TLS at nginx with certbot.\n"
        "4. Use systemd for process supervision.\n"
        "5. Rotate logs with logrotate and stream to journald.",
    ),
    (
        "What does Python's contextvars module do?",
        "contextvars provides task-local storage for asyncio. Each ContextVar "
        "holds a value that is scoped to the current execution context, so "
        "concurrent tasks don't see each other's values. You copy the current "
        "context with copy_context() before dispatching to a thread executor "
        "if you want the bindings to propagate.",
    ),
    (
        "Compare SQLite and Postgres for a small side project.",
        "- SQLite: zero setup, single file, great for embedded and single-writer apps.\n"
        "- Postgres: full server, better concurrency, richer feature set (JSONB, FTS).\n"
        "For a small side project with one writer, SQLite usually wins on simplicity.",
    ),
    (
        "write a bash one-liner to delete old log files",
        "`find /var/log -name '*.log' -mtime +30 -delete`",
    ),
]


# ─── Bad responses — must be flagged ────────────────────────────────────
BAD_PAIRS = [
    (
        "Explain how the tool-use loop handles a truncated tool result.",
        "I'm sorry, I can't help with that.",
    ),
    (
        "Summarize the recent git history in three bullets.",
        "Unfortunately, I don't know.",
    ),
    (
        "What's the capital of France?",
        "",
    ),
    (
        "List the steps to deploy a FastAPI app behind nginx.",
        "step step step step step step step step step step step step step step "
        "step step step step step step step step step step step step step step "
        "step step step step step step step step step step step step step step ",
    ),
    (
        "What does contextvars do?",
        'Traceback (most recent call last):\n  File "x.py", line 1\nTypeError: '
        "'NoneType' object is not subscriptable",
    ),
    (
        "Describe the Workspace class and how sessions stay isolated.",
        "ok.",
    ),
]


def test_good_responses_pass():
    failures = []
    for q, r in GOOD_PAIRS:
        score = score_response(q, r)
        if score < LOW_QUALITY_THRESHOLD:
            failures.append((q[:40], score, r[:60]))
    assert not failures, f"Good pairs scored below threshold: {failures}"


def test_bad_responses_flagged():
    failures = []
    for q, r in BAD_PAIRS:
        if not is_low_quality(q, r):
            failures.append((q[:40], score_response(q, r), r[:60]))
    assert not failures, f"Bad pairs passed the quality bar: {failures}"


def test_score_is_bounded():
    assert 0.0 <= score_response("x", "y") <= 1.0
    assert score_response("long query about async", "") == 0.0
    assert score_response("", "perfectly normal response") <= 1.0


def test_empty_and_whitespace_response():
    assert score_response("q", "") == 0.0
    assert score_response("q", "   \n\n\t ") == 0.0


def test_structure_bonus_only_when_asked():
    query_wants_list = "List three reasons to use Postgres."
    bulleted = "- ACID guarantees\n- Rich SQL\n- Mature ecosystem"
    prose = "Postgres is mature, has ACID guarantees, and supports rich SQL."
    assert score_response(query_wants_list, bulleted) >= score_response(
        query_wants_list, prose
    )
