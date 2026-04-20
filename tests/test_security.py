"""Positive + negative regression corpus for backend/ai/security.py.

Per JARVIS_IMPLEMENTATION_PLAN.md §15 and §9.3, the redaction regex must
fire on real-world secrets and stay quiet on similar-but-benign strings
(commit hashes, package hashes, base64 blobs, dotted identifiers).
"""

from backend.ai.security import REDACTED, redact_keys, sanitize_for_logging

# ─── Positive corpus — MUST be redacted ──────────────────────────────────
POSITIVE = [
    # Google / Gemini
    "AIzaSyD-abcdefghij0123456789klmnopqrstuvw",
    "Here is my key: AIzaSyA0000000000000000000000000000000Z",
    "GEMINI_API_KEY=AIzaSy1111111111111111111111111111111aa",
    # Anthropic
    "sk-ant-api03-" + "a" * 85,
    "Authorization: Bearer sk-ant-api03-" + "x" * 90,
    # OpenAI
    "sk-proj-" + "A" * 40,
    "sk-" + "9" * 50,
    # Groq
    "gsk_" + "q" * 50,
    "GROQ_API_KEY=gsk_" + "a" * 45,
    # GitHub
    "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "github_pat_11AAAAA0A" + "b" * 60,
    # AWS
    "AKIAIOSFODNN7EXAMPLE",
    "aws creds: AKIA0123456789ABCDEF",
    # JWT
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    # Assignment-style
    "api_key: 'abcdef1234567890abcdef'",
    'API_KEY="secret_value_goes_here_xyz"',
    "token = my_super_secret_token_value",
    "password: hunter2hunter2hunter2",
    "Bearer: ExampleBearerToken1234567890",
    "authorization=abcdef0123456789abcdef",
    # Mixed in free text
    "the key AIzaSyD-abcdefghij0123456789klmnopqrstuvw was leaked",
    "curl -H 'Authorization: Bearer sk-proj-" + "k" * 30 + "' https://api",
    # Multiple keys in one string
    "AIzaSyD-abcdefghij0123456789klmnopqrstuvw and gsk_" + "z" * 45,
    # In a traceback-like log line
    "ERROR: request failed with key=AIzaSyXYZabcdefghij0123456789klmnopqrstu",
    # Inside JSON
    '{"api_key": "AIzaSyDabcdefghij0123456789klmnopqrstuvwZ"}',
    # Long-form OpenAI keys
    "sk-" + "a" * 48,
    # Slack (fits the sk- / generic assignment shape variants)
    "token=xoxb-" + "1" * 20,  # hits assignment rule
    # Low-entropy still-triggers on shape
    "ghp_" + "A" * 36,
    "github_pat_" + "0" * 60 + "abc",
    # JWT inside a log
    "response: eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyIjoiam9obiJ9.abc1234567",
    # OpenAI project key inside a dict value
    "{'key': 'sk-proj-" + "p" * 35 + "'}",
]


# ─── Negative corpus — MUST NOT be redacted ──────────────────────────────
NEGATIVE = [
    # Git commit hashes (short + long)
    "5592777",
    "5592777a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e",
    "f94062ac0d8c8e1c3f8d6e9a7b5c4d2e1f0a9b8c",
    "abc123def456 abc123def456",
    # npm package hashes
    "sha256-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789+/AbCd=",
    "sha512-" + "A" * 88 + "==",
    # Python package wheel hashes
    "hashes: --hash=sha256:deadbeefcafe1234567890abcdef",
    # UUIDs
    "550e8400-e29b-41d4-a716-446655440000",
    "019dab1b-c888-7e81-81dd-ef2fd7b027b6",
    # Plain English
    "this is a test",
    "the function read_codebase returns a dict",
    "running query (mode=local, task=quick_qa): what is jarvis",
    # Package names / dotted identifiers (no assignment)
    "backend.ai.claude_client",
    "react.useState.useEffect",
    "com.example.AppName",
    # Version strings
    "v1.2.3",
    "python==3.14.0",
    "react@18.2.0",
    # File paths
    "/usr/local/bin/python",
    "C:\\Users\\dev\\.env",
    "backend/ai/security.py",
    # URLs without keys
    "https://github.com/anthropics/claude-code",
    "https://docs.python.org/3/library/re.html",
    # Short strings that resemble key prefixes but are too short
    "AIza",
    "sk-",
    "ghp_",
    # JSON-like structure without secrets
    '{"name": "jarvis", "version": "1.0"}',
    # Base64 text that is not a JWT
    "aGVsbG8gd29ybGQ=",  # "hello world"
    # Looks-like-bearer but no assignment
    "The bearer of this letter is trustworthy",
    # SQL
    "SELECT token FROM users WHERE id = 1",
    # Function call
    "redact_keys('some text')",
    # Class name
    "AwsClient",  # shares AWS prefix but not AKIA format
    # File hash mentions
    "SHA256 checksum: abcdef0123456789",  # assignment would fire if rule too loose; "checksum" is not in list
]


def test_positive_corpus_all_redacted():
    failures = []
    for s in POSITIVE:
        redacted = redact_keys(s)
        if REDACTED not in redacted:
            failures.append(s)
    assert not failures, (
        f"{len(failures)} strings were NOT redacted but should have been:\n"
        + "\n".join(f"  - {s!r}" for s in failures)
    )


def test_negative_corpus_untouched():
    failures = []
    for s in NEGATIVE:
        redacted = redact_keys(s)
        if redacted != s:
            failures.append((s, redacted))
    assert not failures, (
        f"{len(failures)} strings were mangled but should have been left alone:\n"
        + "\n".join(f"  - {s!r} -> {r!r}" for s, r in failures)
    )


def test_positive_corpus_size_sanity():
    assert len(POSITIVE) >= 30, "§15 requires ≥30 positive cases"


def test_negative_corpus_size_sanity():
    assert len(NEGATIVE) >= 30, "§15 requires ≥30 negative cases"


def test_sanitize_structure_walks_dicts_and_lists():
    inp = {
        "user_query": "AIzaSyD-abcdefghij0123456789klmnopqrstuvw",
        "mode": "local",
        "history": [
            {"role": "user", "content": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"},
            {"role": "assistant", "content": "fine"},
        ],
        "count": 42,
    }
    out = sanitize_for_logging(inp)
    assert REDACTED in out["user_query"]
    assert out["mode"] == "local"
    assert REDACTED in out["history"][0]["content"]
    assert out["history"][1]["content"] == "fine"
    assert out["count"] == 42
    # Dict keys untouched
    assert "user_query" in out


def test_redact_handles_empty_and_non_strings():
    assert redact_keys("") == ""
    assert redact_keys(None) is None  # type: ignore[arg-type]
    assert redact_keys(42) == 42  # type: ignore[arg-type]


def test_redact_is_idempotent():
    original = "leak AIzaSyD-abcdefghij0123456789klmnopqrstuvw here"
    once = redact_keys(original)
    twice = redact_keys(once)
    assert once == twice
