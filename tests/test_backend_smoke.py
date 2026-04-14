from backend.ai.claude_client import MAX_TOOL_OUTPUT_CHARS, _serialize_tool_result
from backend.ai.ollama_client import parse_ollama_json
from backend.ai.prompts import build_system_prompt


def test_build_system_prompt_includes_project_context():
    prompt = build_system_prompt()

    assert "Project: JARVIS" in prompt
    assert "<project_context>" in prompt
    assert "<recent_sessions>" in prompt
    assert "<runtime_context>" in prompt
    assert "read_project_context" in prompt


def test_parse_ollama_json_handles_code_fences():
    parsed = parse_ollama_json(
        """```json
{"should_surface": true, "confidence": 0.8, "reason": "hot path changed"}
```"""
    )

    assert parsed["should_surface"] is True
    assert parsed["confidence"] == 0.8


def test_serialize_tool_result_keeps_valid_json_when_truncated():
    payload = {"content": "x" * (MAX_TOOL_OUTPUT_CHARS + 100)}

    serialized = _serialize_tool_result(payload)

    assert '"truncated": true' in serialized
    assert '"preview"' in serialized
