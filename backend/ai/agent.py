"""JarvisAgent — encapsulates the Claude/OpenAI tool-use loop state."""

from __future__ import annotations

import logging

logger = logging.getLogger("jarvis.agent")


class JarvisAgent:
    """Stateful wrapper around one query's tool-use loop."""

    def __init__(
        self,
        *,
        messages: list,
        task_type: str,
        mode: str,
        params: dict,
        send_event,
        call_with_fallback,
        stream_final_response,
        stream_text,
        execute_tool,
        trim_history,
        tool_schemas: list,
        max_iterations: int,
    ):
        self.messages = messages
        self.task_type = task_type
        self.mode = mode
        self.params = params
        self.send_event = send_event
        self._call_with_fallback = call_with_fallback
        self._stream_final_response = stream_final_response
        self._stream_text = stream_text
        self._execute_tool = execute_tool
        self._trim_history_fn = trim_history
        self.tool_schemas = tool_schemas
        self.max_iterations = max_iterations
        self.observations: list[dict] = []
        # Count of tool calls dispatched during this run — consumed by the
        # quality-retry guard to skip retries when side-effecting tools fired.
        self.tools_used: int = 0

    async def run(self) -> str:
        for iteration in range(self.max_iterations):
            self._trim_history()

            try:
                response = await self._call_llm()
            except RuntimeError as e:
                err = str(e)
                logger.error(err)
                is_ollama = "ollama" in err.lower() or "connection" in err.lower()
                await self.send_event({
                    "event": "jarvis_error",
                    "message": "Ollama is not running. Start with: ollama serve" if is_ollama else err,
                    "recoverable": is_ollama,
                })
                return f"API error: {e}"

            choice = response.choices[0]

            if self._is_final(choice):
                text = choice.message.content or ""
                return await self._stream_response(text, iteration)

            if choice.finish_reason == "tool_calls":
                await self._execute_tools(
                    choice.message.tool_calls or [],
                    assistant_content=choice.message.content,
                )
                continue

            logger.warning(f"Unexpected finish_reason: {choice.finish_reason}")
            break

        logger.warning("Max tool iterations reached")
        await self.send_event({
            "event": "jarvis_error",
            "message": "Reached max tool iterations. Please ask a more specific question.",
            "recoverable": True,
        })
        return "I ran into a loop. Please try a more specific question."

    async def _call_llm(self):
        return await self._call_with_fallback(
            task_type=self.task_type,
            mode=self.mode,
            messages=self.messages,
            tools=self.tool_schemas,
            **self.params,
        )

    def _trim_history(self):
        self._trim_history_fn(self.messages)

    def _is_final(self, choice) -> bool:
        return choice.finish_reason == "stop"

    async def _stream_response(self, text: str, iteration: int) -> str:
        if iteration > 0 and self.mode == "cloud":
            streamed = await self._stream_final_response(
                self.task_type, self.mode, self.messages, self.send_event,
            )
            if streamed is not None:
                return streamed
        await self._stream_text(text, self.send_event)
        return text

    async def _execute_tools(self, tool_calls: list, assistant_content=None) -> None:
        self.messages.append({
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            self.tools_used += 1
            await self._execute_tool(
                tc,
                self.messages,
                self.send_event,
                pre_tool_check=self._pre_tool_check,
                post_tool_check=self._post_tool_check,
            )

    async def _pre_tool_check(self, _tool_name: str, _tool_input: dict):
        return None

    async def _post_tool_check(self, _tool_name: str, result: dict):
        return result
