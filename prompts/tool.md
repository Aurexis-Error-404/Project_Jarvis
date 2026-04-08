## Core
Tool use is how claude interacts with the outside world.It is a way to give claude the ability to perform actions and retrieve information from external sources. 

It is a conversation loop,not a single call.You send a request with tools,claude decides to use a tool,you execute it and send the result back to claude,then claude responds to the user.

## The full tool_use loop

1.You send: Api calls with messages and tool_definitions

2.Claude decides: Claude thinks, Returns Stop_reason with tool_use block containing name and inputs.

3.You execute: Run the tool with the inputs.Extract tool_usename and tool_use.inputs .

4.You send back: Add the tool result to the conversation as a tool_result message.Append  Claude's response to messages as a message with role: "assistant" and content: tool_result. the tool_use_id must match the tool_use_id of the tool_use message.

5.Claude continues: Claude thinks again and either responds to the user or calls another tool.

6.Repeat: Until Claude returns a response with stop_reason: "end_turn"

## Key points

- Claude never calls tools directly. It only requests them.
- You are responsible for executing the tools and sending the results back.
- The loop continues until Claude decides to stop.
- You can use the same tool multiple times in a row if needed.
- Claude will always tell you which tool it wants to use and what inputs it needs.

## Complete working tool_use loop example

import anthropic, json

client = anthropic.Anthropic()

# Tool definitions — what Claude can call
tools = [{
    "name": "read_git_history",
    "description": "Read recent git commits and diffs",
    "input_schema": {
        "type": "object",
        "properties": {
            "since": {"type": "string", "description": "e.g. '24h' or 'HEAD~3'"},
            "include_diff": {"type": "boolean", "default": False}
        },
        "required": ["since"]
    }
}]

def execute_tool(name: str, inputs: dict) -> str:
    # Your actual tool implementations live here
    try:
        if name == "read_git_history":
            result = git_interface.read_history(**inputs)
            return json.dumps(result)
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        # NEVER let tools raise unhandled exceptions
        # Always return an error dict so Claude can handle it gracefully
        return json.dumps({"error": str(e), "tool": name})

def call_claude_with_tools(user_query: str, system_prompt: str) -> str:
    messages = [{"role": "user", "content": user_query}]

    while True:  # loop until end_turn
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=[{"type": "text", "text": system_prompt,
                     "cache_control": {"type": "ephemeral"}}],
            tools=tools,
            messages=messages
        )

        if response.stop_reason == "end_turn":
            # Done! Extract text response
            for block in response.content:
                if block.type == "text":
                    return block.text
            return ""

        if response.stop_reason == "tool_use":
            # Step 1: Append Claude's response to message history
            messages.append({
                "role": "assistant",
                "content": response.content  # include the full content list
            })

            # Step 2: Execute ALL tool calls in this response
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id"
: block.id,  # MUST match — critical
                        "content": result
                    })

            # Step 3: Send results back as user message
            messages.append({
                "role": "user",
                "content": tool_results
            })
            # Loop continues — Claude will read the results and decide what to do next
    


## Mistake to be never be done
 If tool_use_id in your tool_result doesn't exactly match the id from Claude's tool_use block, Claude either ignores the result entirely or throws an API error. Always use block.id directly — never construct the ID yourself.


## Safety Addition You Should Make

    max_iterations = 10
iteration = 0

while True:
    iteration += 1
    if iteration > max_iterations:
        return "Error: max tool iterations reached"
    # ... rest of loop


## JARVIS-specific insight:
 Claude can call multiple tools in one response. When you ask "What changed in my code and why is my training loop crashing?" — Claude may call read_git_history AND read_codebase in the same response. Your loop must handle all tool_use blocks in the content array, not just the first one. The code above handles this with the inner for loop.

 