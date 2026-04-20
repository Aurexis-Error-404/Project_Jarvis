"""Regression coverage for the JarvisAgent harness."""

from types import SimpleNamespace

import pytest

from backend.ai.agent import JarvisAgent


def _response(finish_reason, content="", tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    choice = SimpleNamespace(finish_reason=finish_reason, message=message)
    return SimpleNamespace(choices=[choice])


def _tool_call(name="read_codebase", arguments="{}"):
    fn = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id="tool-1", function=fn)


def _agent(responses, *, execute_tool):
    queue = list(responses)
    streamed = []
    events = []

    async def call_with_fallback(**_kwargs):
        return queue.pop(0)

    async def stream_final_response(*_args, **_kwargs):
        return None

    async def stream_text(text, _send_event):
        streamed.append(text)

    async def send_event(payload):
        events.append(payload)

    agent = JarvisAgent(
        messages=[{"role": "system", "content": "You are JARVIS."}],
        task_type="quick_qa",
        mode="local",
        params={"temperature": 0.4, "max_tokens": 256},
        send_event=send_event,
        call_with_fallback=call_with_fallback,
        stream_final_response=stream_final_response,
        stream_text=stream_text,
        execute_tool=execute_tool,
        trim_history=lambda messages: messages,
        tool_schemas=[],
        max_iterations=3,
    )
    return agent, streamed, events


@pytest.mark.asyncio
async def test_agent_final_response_no_tools():
    async def execute_tool(*_args, **_kwargs):
        raise AssertionError("execute_tool should not be called")

    agent, streamed, _events = _agent(
        [_response("stop", content="hello world")],
        execute_tool=execute_tool,
    )

    result = await agent.run()

    assert result == "hello world"
    assert streamed == ["hello world"]


@pytest.mark.asyncio
async def test_agent_one_tool_call_then_final():
    async def execute_tool(tc, messages, _send_event, **_kwargs):
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": '{"ok": true}',
        })

    agent, streamed, _events = _agent(
        [
            _response("tool_calls", tool_calls=[_tool_call()]),
            _response("stop", content="done"),
        ],
        execute_tool=execute_tool,
    )

    result = await agent.run()

    assert result == "done"
    assert streamed == ["done"]
    assert any(m.get("role") == "assistant" and "tool_calls" in m for m in agent.messages)
    assert any(m.get("role") == "tool" for m in agent.messages)


@pytest.mark.asyncio
async def test_agent_max_iterations_returns_loop_error():
    async def execute_tool(tc, messages, _send_event, **_kwargs):
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": '{"ok": true}',
        })

    agent, _streamed, events = _agent(
        [_response("tool_calls", tool_calls=[_tool_call()]) for _ in range(3)],
        execute_tool=execute_tool,
    )
    agent.max_iterations = 1

    result = await agent.run()

    assert "loop" in result.lower()
    assert any(e.get("event") == "jarvis_error" for e in events)


@pytest.mark.asyncio
async def test_agent_pre_tool_check_can_block():
    async def execute_tool(tc, messages, _send_event, pre_tool_check=None, **_kwargs):
        blocked = await pre_tool_check(tc.function.name, {"path": "."})
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": str(blocked),
        })

    agent, _streamed, _events = _agent(
        [
            _response("tool_calls", tool_calls=[_tool_call()]),
            _response("stop", content="done"),
        ],
        execute_tool=execute_tool,
    )

    async def pre_tool_check(_tool_name, _tool_input):
        return {"error": "blocked"}

    agent._pre_tool_check = pre_tool_check

    await agent.run()

    assert any("blocked" in m.get("content", "") for m in agent.messages if m.get("role") == "tool")


@pytest.mark.asyncio
async def test_agent_post_tool_check_can_rewrite_result():
    async def execute_tool(tc, messages, _send_event, post_tool_check=None, **_kwargs):
        rewritten = await post_tool_check(tc.function.name, {"ok": True})
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": str(rewritten),
        })

    agent, _streamed, _events = _agent(
        [
            _response("tool_calls", tool_calls=[_tool_call()]),
            _response("stop", content="done"),
        ],
        execute_tool=execute_tool,
    )

    async def post_tool_check(_tool_name, result):
        result["patched"] = True
        return result

    agent._post_tool_check = post_tool_check

    await agent.run()

    assert any("patched" in m.get("content", "") for m in agent.messages if m.get("role") == "tool")
