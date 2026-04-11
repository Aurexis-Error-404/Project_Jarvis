# JARVIS Advanced Features Implementation Guide

This guide covers 8 advanced capabilities to evolve JARVIS beyond its Phase 1 (48-hour sprint) scope. Each section explains the concept, maps it to JARVIS's existing architecture, and provides concrete implementation steps.

**Do not execute this guide yet.** This is a design reference for post-sprint development.

---

## Table of Contents

1. [Advanced System Prompts (CLAUDE.md Pattern)](#1-advanced-system-prompts)
2. [Agent Harnesses](#2-agent-harnesses)
3. [Parallelization, Sub-agents & Agent Teams](#3-parallelization-sub-agents--agent-teams)
4. [Context & Workspace Management](#4-context--workspace-management)
5. [Auto Research](#5-auto-research)
6. [Internet & Computer Automation](#6-internet--computer-automation)
7. [Handling Performance Fluctuations](#7-handling-performance-fluctuations)
8. [Security Fundamentals](#8-security-fundamentals)

---

## 1. Advanced System Prompts

### Concept

System prompts are the most cost-effective way to control AI behavior. Instead of sending examples or instructions every turn, you compress knowledge into a persistent system prompt that:
- Declares capabilities and constraints upfront
- Sets user preferences once (never repeated)
- Maintains a failure/success log to avoid repeating mistakes
- Reduces token usage by 30-60% across a conversation

### Current State in JARVIS

**File:** `backend/ai/prompts.py`

JARVIS already has a two-block system prompt:
- **Static Block** (lines 16-106): Identity, tool rules, error diagnosis rules, response quality rules
- **Dynamic Block** (lines 109-157): Project context from `jarvis.json`, codebase map, session history

**Current token budget:** ~5,000 tokens (stated at line 10)

### Implementation Plan

#### Step 1: Create a `.claude/` directory for prompt engineering

```
.claude/
  system_prompt.md       # Global system prompt (loaded for every query)
  user_preferences.md    # User-specific preferences (response style, verbosity)
  failure_log.md         # Auto-maintained: what went wrong and the fix
  success_log.md         # Auto-maintained: validated approaches
  capability_map.md      # What JARVIS can and cannot do (prevents hallucinated tools)
```

#### Step 2: Knowledge Compression

The key insight: instead of sending full context every turn, compress knowledge into assertions.

**Before (wastes tokens every turn):**
```
The project uses Electron + React for the frontend, Python FastAPI for the backend,
WebSocket on port 8765, Gemini for error diagnosis, Groq for summaries...
```

**After (compressed to schema reference):**
```
<knowledge ref="jarvis.json" fields="project,decisions,ai_config"/>
```

**Implementation in `prompts.py`:**

```python
def build_system_prompt(
    jarvis_json_path: str = "jarvis.json",
    codebase_map: str = "",
    session_history: str = "",
    user_prefs: dict = None,       # NEW
    failure_log: list = None,      # NEW
) -> str:
    # ... existing static + dynamic blocks ...

    # User preferences block (loaded from .claude/user_preferences.md)
    prefs_block = ""
    if user_prefs:
        prefs_block = f"""<user_preferences>
Response style: {user_prefs.get('style', 'concise')}
Verbosity: {user_prefs.get('verbosity', 'medium')}
Code format: {user_prefs.get('code_format', 'with line numbers')}
Avoid: {', '.join(user_prefs.get('avoid', []))}
</user_preferences>"""

    # Failure log block (prevents repeating mistakes)
    failure_block = ""
    if failure_log:
        entries = "\n".join(
            f"- [{f['date']}] {f['what_failed']}: {f['fix']}"
            for f in failure_log[-10:]  # Last 10 failures only
        )
        failure_block = f"""<failure_log>
Known issues — do NOT repeat these patterns:
{entries}
</failure_log>"""

    return STATIC_SYSTEM_PROMPT + "\n\n" + dynamic_block + "\n\n" + prefs_block + "\n\n" + failure_block
```

#### Step 3: Auto-Maintain Failure/Success Logs

Add a post-query hook in `claude_client.py` that detects:
- Tool call errors (already tracked in the tool loop)
- User corrections ("no, that's wrong", "actually...")
- Repeated questions (user asked the same thing twice = first answer was bad)

**New file:** `backend/memory/prompt_log.py`

```python
import json
from pathlib import Path

LOG_PATH = Path(__file__).parent.parent.parent / ".claude"

def log_failure(what_failed: str, fix: str):
    """Append a failure entry to .claude/failure_log.md"""
    path = LOG_PATH / "failure_log.md"
    path.parent.mkdir(exist_ok=True)
    entry = f"- [{_today()}] {what_failed}: {fix}\n"
    with open(path, "a") as f:
        f.write(entry)

def log_success(approach: str, context: str):
    """Append a validated approach to .claude/success_log.md"""
    path = LOG_PATH / "success_log.md"
    path.parent.mkdir(exist_ok=True)
    entry = f"- [{_today()}] {approach} (context: {context})\n"
    with open(path, "a") as f:
        f.write(entry)

def read_failures(last_n: int = 10) -> list:
    path = LOG_PATH / "failure_log.md"
    if not path.exists():
        return []
    lines = path.read_text().strip().split("\n")
    return [{"raw": l} for l in lines[-last_n:]]
```

#### Step 4: Capability Declaration

Instead of the AI hallucinating tools it doesn't have, declare capabilities explicitly:

```markdown
# .claude/capability_map.md

## Tools Available
- read_codebase: Read file contents (up to 500 lines) or list files
- read_git_history: Git log with optional diffs (max 50 commits)
- web_research: DuckDuckGo search + page scraping (max 8 results)
- generate_html_report: Create HTML reports from sections
- update_project_memory: Write to jarvis.json (decisions, focus, etc.)
- read_session_history: Read past session metadata

## Tools NOT Available (do not suggest these)
- File writing/editing (cannot modify source code)
- Terminal command execution
- Database access
- Email/Slack/notification sending
- Image generation or analysis
- Package installation
```

Inject this into the system prompt's `<tool_rules>` block.

#### Key Files to Modify
- `backend/ai/prompts.py` — add new prompt blocks
- `backend/ai/claude_client.py` — add post-query hook for failure detection
- New: `backend/memory/prompt_log.py` — failure/success log manager
- New: `.claude/` directory with prompt files

---

## 2. Agent Harnesses

### Concept

An agent harness is the framework wrapping the LLM that gives it:
- **Tools** — functions the LLM can call
- **Memory** — persistent state across turns
- **Guardrails** — limits on what the LLM can do
- **Observation loop** — the cycle of: prompt → LLM response → tool execution → observation → next prompt

JARVIS already has a basic harness. This section describes how to formalize and extend it.

### Current Harness in JARVIS

```
┌─────────────────────────────────────────┐
│  JARVIS Agent Harness (claude_client.py) │
├─────────────────────────────────────────┤
│  System Prompt (prompts.py)             │
│  ↓                                       │
│  Tool-Use Loop (max 10 iterations)       │
│    ├── LLM call → response               │
│    ├── If tool_calls: dispatch + collect  │
│    ├── Append results to messages         │
│    └── Loop until finish_reason="stop"    │
│  ↓                                       │
│  Stream response to frontend             │
├─────────────────────────────────────────┤
│  Tools:     6 registered tools           │
│  Memory:    jarvis.json + session_history │
│  Guardrails: MAX_TOOL_ITERATIONS (10)    │
│             MAX_TOOL_OUTPUT_CHARS (12K)   │
│             HISTORY_TOKEN_BUDGET (30K)    │
└─────────────────────────────────────────┘
```

### Implementation Plan

#### Step 1: Formalize the Harness as a Class

Extract the procedural `run()` function into a class:

**New file:** `backend/ai/agent.py`

```python
class JarvisAgent:
    """Stateful agent harness wrapping the LLM tool-use loop."""

    def __init__(self, mode: str, send_event, codebase_map: str, history: list):
        self.mode = mode
        self.send_event = send_event
        self.codebase_map = codebase_map
        self.history = history or []
        self.messages = []
        self.tool_calls_made = []
        self.iteration = 0
        self.max_iterations = MAX_TOOL_ITERATIONS

    async def run(self, query: str) -> str:
        """Execute the full agent loop for a query."""
        self._build_messages(query)
        while self.iteration < self.max_iterations:
            response = await self._call_llm()
            if self._is_final(response):
                return await self._stream_response(response)
            await self._execute_tools(response)
            self.iteration += 1
        return self._handle_max_iterations()

    def _build_messages(self, query: str):
        """Construct initial message array with system prompt + history + query."""
        ...

    async def _call_llm(self):
        """Call the LLM with current messages and tools."""
        ...

    def _is_final(self, response) -> bool:
        """Check if response is a final text answer (no more tool calls)."""
        ...

    async def _execute_tools(self, response):
        """Dispatch tool calls, collect results, append to messages."""
        ...

    async def _stream_response(self, response) -> str:
        """Stream final response text to frontend."""
        ...
```

#### Step 2: Add Guardrail Hooks

```python
class JarvisAgent:
    # ... existing code ...

    async def _pre_tool_check(self, tool_name: str, tool_input: dict) -> bool:
        """Guardrail: validate tool call before execution."""
        # Block dangerous operations
        if tool_name == "update_project_memory":
            if tool_input.get("field") == "ai_config":
                await self.send_event({
                    "event": "jarvis_error",
                    "message": "Cannot modify ai_config — locked by architecture decision",
                })
                return False
        return True

    async def _post_tool_check(self, tool_name: str, result: dict) -> dict:
        """Guardrail: validate tool result before passing to LLM."""
        if "error" in result:
            self._log_failure(tool_name, result["error"])
        return result
```

#### Step 3: Add Observation Memory

After each tool call, the harness stores what it learned:

```python
class JarvisAgent:
    def __init__(self, ...):
        self.observations = []  # What the agent learned this session

    async def _execute_tools(self, response):
        for tc in response.choices[0].message.tool_calls:
            result = await dispatch_tool(tc.function.name, ...)
            self.observations.append({
                "tool": tc.function.name,
                "input_summary": str(tc.function.arguments)[:100],
                "result_summary": str(result)[:200],
                "timestamp": time.time(),
            })
```

#### Key Files to Modify
- New: `backend/ai/agent.py` — agent class
- `backend/ai/claude_client.py` — refactor `run()` to use `JarvisAgent`
- `backend/tools/tool_dispatcher.py` — add pre/post hooks

---

## 3. Parallelization, Sub-agents & Agent Teams

### Concept

Single-agent architectures hit two walls:
1. **Stochasticity** — the same prompt can produce different quality answers
2. **Context degradation** — after 10+ tool calls, the model loses focus

Solutions:
- **Fan-out/Fan-in**: Send the same query to N agents, merge results
- **Stochastic Consensus**: Run N agents, take majority vote on the answer
- **Debate**: Two agents argue opposing positions, a judge picks the winner
- **Sequential Pipeline**: Agent A does research, passes structured output to Agent B for analysis

### Current State

JARVIS runs a single agent per query. No parallelization exists.

### Implementation Plan

#### Strategy 1: Fan-Out/Fan-In Research

For research reports, spawn 3 parallel sub-agents with different search queries:

```python
# In claude_client.py or a new orchestrator.py

async def fan_out_research(query: str, mode: str, send_event) -> list:
    """Spawn 3 sub-agents with different search angles."""
    sub_queries = await _generate_search_variants(query)  # LLM generates 3 variants

    tasks = [
        _run_sub_agent(sq, mode, send_event=None)  # Silent — no streaming
        for sq in sub_queries
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge: deduplicate findings, rank by relevance
    merged = _merge_research_results(results)
    return merged
```

**Architecture:**
```
User Query: "Research WebSocket alternatives"
      │
      ├─→ Sub-Agent 1: "WebSocket vs SSE performance benchmarks 2025"
      ├─→ Sub-Agent 2: "gRPC-Web streaming vs WebSocket Python FastAPI"
      └─→ Sub-Agent 3: "WebSocket scaling patterns async Python production"
           │
           ▼
      Merge: deduplicate, rank, combine citations
           │
           ▼
      Main Agent: generate_html_report with merged data
```

#### Strategy 2: Stochastic Consensus for Error Diagnosis

Run the same error diagnosis 3 times with temperature=0.3, take the majority:

```python
async def consensus_diagnosis(query: str, mode: str) -> str:
    """Run 3 diagnosis attempts, return the one agreed upon by majority."""
    tasks = [
        _run_diagnosis(query, mode, temperature=0.3 + i * 0.1)
        for i in range(3)
    ]
    results = await asyncio.gather(*tasks)

    # Extract CAUSE lines, find majority agreement
    causes = [_extract_cause(r) for r in results]
    majority_cause = Counter(causes).most_common(1)[0][0]

    # Return the full response that matches the majority cause
    for r in results:
        if _extract_cause(r) == majority_cause:
            return r
    return results[0]
```

#### Strategy 3: Sequential Pipeline

```
Stage 1 (Groq - fast):     Classify query type, extract key entities
         │
Stage 2 (Gemini - deep):   Research with codebase context
         │
Stage 3 (Groq - fast):     Format into structured response
```

```python
async def pipeline_query(query: str, mode: str, send_event):
    # Stage 1: Classification (Groq — fast, cheap)
    classification = await _call_with_fallback(
        task_type="quick_qa", mode="cloud",
        messages=[{"role": "user", "content": f"Classify this query: {query}"}],
        max_tokens=100,
    )

    # Stage 2: Deep research (Gemini — quality)
    research = await _call_with_fallback(
        task_type="research_report", mode="cloud",
        messages=[
            {"role": "system", "content": f"Query type: {classification}"},
            {"role": "user", "content": query},
        ],
        tools=OAI_TOOL_SCHEMAS,
    )

    # Stage 3: Format (Groq — structured output)
    formatted = await _call_with_fallback(
        task_type="git_summary", mode="cloud",
        messages=[
            {"role": "user", "content": f"Format this research for a developer:\n{research}"},
        ],
        max_tokens=2048,
    )
    return formatted
```

#### Key Files to Modify
- New: `backend/ai/orchestrator.py` — fan-out/fan-in, consensus, pipeline
- `backend/ai/claude_client.py` — route complex queries to orchestrator
- `backend/ai/providers.py` — may need concurrent connection pools

---

## 4. Context & Workspace Management

### Concept

AI agents generate artifacts (logs, temp files, caches). Without structure, these pollute the project root. The solution: dedicated directories with clear separation.

### Recommended Structure

```
Project_Jarvis/
  .claude/                    # AI agent workspace (gitignored)
    system_prompt.md          # Global system prompt overrides
    user_preferences.md       # User-specific settings
    failure_log.md            # Auto-maintained failure log
    success_log.md            # Auto-maintained success log
    capability_map.md         # Declared capabilities
    cache/                    # LLM response cache
      prompt_cache.json       # Cached prompt → response pairs
    temp/                     # Scratch space for agent work
  .env                        # API keys + config (gitignored)
  .env.example                # Template (committed)
  jarvis.json                 # Project memory (committed)
  backend/
    logs/                     # Backend logs (gitignored)
      error.log
    memory/                   # Memory management code
  reports/                    # Generated reports (gitignored)
```

### Implementation Plan

#### Step 1: Create `.claude/` workspace

Add to `.gitignore`:
```
.claude/cache/
.claude/temp/
.claude/failure_log.md
.claude/success_log.md
```

Keep committed:
```
.claude/system_prompt.md
.claude/user_preferences.md
.claude/capability_map.md
```

#### Step 2: Multi-Workspace Support

For users working across multiple projects, JARVIS needs workspace isolation:

```python
# backend/context/workspace.py

class Workspace:
    """Manages context isolation between different project workspaces."""

    def __init__(self, project_path: str):
        self.root = Path(project_path)
        self.claude_dir = self.root / ".claude"
        self.cache_dir = self.claude_dir / "cache"
        self.temp_dir = self.claude_dir / "temp"

    def ensure_dirs(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def get_system_prompt_override(self) -> str:
        path = self.claude_dir / "system_prompt.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def get_user_prefs(self) -> dict:
        path = self.claude_dir / "user_preferences.md"
        if path.exists():
            # Parse YAML frontmatter or simple key: value format
            ...
        return {}
```

#### Step 3: Safe File Spaces

The `active/` pattern for in-progress work:

```
.claude/
  active/                     # Currently being worked on
    research_websocket.md     # Active research notes
    diagnosis_bug_42.md       # Active bug investigation
  archive/                    # Completed work
    2026-04-11_research.md
```

Tools can read/write to `active/` but never to project source files.

#### Key Files to Modify
- New: `backend/context/workspace.py` — workspace manager
- `.gitignore` — add `.claude/cache/`, `.claude/temp/`
- `backend/ai/prompts.py` — load workspace overrides
- `backend/ai/claude_client.py` — pass workspace context

---

## 5. Auto Research

### Concept

Based on Andrej Karpathy's autonomous research framework: create a loop that:
1. Runs a test or assessment
2. Evaluates the result against a target metric
3. Makes an improvement
4. Repeats until the metric is met or a budget is exhausted

Example: continuously improving a website's Lighthouse score.

### Implementation Plan

#### Core Loop

```python
# backend/ai/auto_research.py

class AutoResearchLoop:
    """Iterative test-assess-optimize loop."""

    def __init__(self, target_metric: str, threshold: float, max_iterations: int = 10):
        self.target_metric = target_metric
        self.threshold = threshold
        self.max_iterations = max_iterations
        self.history = []

    async def run(self, initial_query: str, send_event) -> dict:
        query = initial_query
        for i in range(self.max_iterations):
            # Step 1: Research
            result = await self._research(query)

            # Step 2: Assess
            score = await self._assess(result)
            self.history.append({"iteration": i, "score": score, "query": query})

            await send_event({
                "event": "jarvis_stream_chunk",
                "text": f"\n**Iteration {i+1}**: Score = {score:.2f} (target: {self.threshold})\n",
                "done": False,
            })

            # Step 3: Check threshold
            if score >= self.threshold:
                return {"status": "success", "iterations": i+1, "final_score": score}

            # Step 4: Generate improved query based on what was missing
            query = await self._improve(query, result, score)

        return {"status": "budget_exhausted", "iterations": self.max_iterations, "best_score": max(h["score"] for h in self.history)}

    async def _research(self, query: str) -> str:
        """Call web_research tool with the query."""
        from backend.tools.web_research import run as web_research
        return await web_research(query=query, max_results=5)

    async def _assess(self, result: str) -> float:
        """Use LLM to score the research quality against the target metric."""
        prompt = f"Score this research from 0-1 on: {self.target_metric}\n\n{result}"
        # Call LLM, extract float score
        ...

    async def _improve(self, query: str, result: str, score: float) -> str:
        """Use LLM to generate a better search query based on gaps."""
        prompt = f"Previous query: {query}\nScore: {score}\nGaps: What's missing?\nGenerate a better search query."
        # Call LLM, extract improved query
        ...
```

#### Use Case: Lighthouse Score Optimization

```python
class LighthouseOptimizer(AutoResearchLoop):
    """Iteratively research and suggest improvements for web performance."""

    async def _assess(self, suggestions: str) -> float:
        """Run Lighthouse (via MCP or CLI) and return performance score."""
        # Option 1: Call Lighthouse CLI
        result = await asyncio.create_subprocess_shell(
            "npx lighthouse http://localhost:3000 --output=json --quiet",
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await result.communicate()
        data = json.loads(stdout)
        return data["categories"]["performance"]["score"]
```

#### Key Files
- New: `backend/ai/auto_research.py` — auto research loop
- `backend/ai/claude_client.py` — detect "optimize" or "improve" queries, route to auto loop
- `backend/tools/__init__.py` — optional: add `run_lighthouse` tool schema

---

## 6. Internet & Computer Automation

### Concept

Three tiers of automation, each with different speed/reliability tradeoffs:

| Tier | Method | Speed | Reliability | Use Case |
|------|--------|-------|-------------|----------|
| 1 | HTTP requests | Fast | Fragile (API changes break it) | API calls, JSON endpoints |
| 2 | Browser automation | Medium | Medium (DOM changes break it) | Web scraping, form filling |
| 3 | Computer automation | Slow | Robust (visual, no DOM dependency) | Desktop apps, any UI |

### Current State

JARVIS has **Tier 1 only**: `web_research.py` does HTTP requests to DuckDuckGo + page scraping.

### Implementation Plan

#### Tier 2: Browser Automation via Chrome DevTools Protocol

```python
# backend/tools/browser_automation.py

import asyncio
from playwright.async_api import async_playwright

async def run(url: str, action: str = "read", selector: str = None, value: str = None) -> dict:
    """
    Browser automation tool.
    action: "read" (get page content), "click" (click element), "fill" (fill input),
            "screenshot" (capture page), "evaluate" (run JS)
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=30000)

        if action == "read":
            content = await page.content()
            text = await page.evaluate("document.body.innerText")
            return {"url": url, "text": text[:5000], "title": await page.title()}

        elif action == "click":
            await page.click(selector, timeout=5000)
            await page.wait_for_load_state("networkidle")
            return {"url": page.url, "clicked": selector}

        elif action == "fill":
            await page.fill(selector, value, timeout=5000)
            return {"filled": selector, "value": value}

        elif action == "screenshot":
            path = f"reports/screenshot_{int(time.time())}.png"
            await page.screenshot(path=path, full_page=True)
            return {"path": path}

        elif action == "evaluate":
            result = await page.evaluate(value)  # value is JS code
            return {"result": str(result)[:3000]}

        await browser.close()
```

**Tool Schema:**
```python
{
    "name": "browser_automation",
    "description": "Automate browser actions: read pages, click, fill forms, take screenshots.",
    "input_schema": {
        "properties": {
            "url": {"type": "string"},
            "action": {"type": "string", "enum": ["read", "click", "fill", "screenshot", "evaluate"]},
            "selector": {"type": "string", "description": "CSS selector for click/fill"},
            "value": {"type": "string", "description": "Value for fill or JS for evaluate"},
        },
        "required": ["url", "action"],
    },
}
```

#### Tier 3: Desktop Automation (Computer Use)

This requires Claude's Computer Use API or a mouse/keyboard automation library:

```python
# backend/tools/computer_automation.py
# WARNING: Requires explicit user consent — this controls mouse and keyboard

import pyautogui

async def run(action: str, x: int = None, y: int = None, text: str = None) -> dict:
    """
    Desktop automation. Actions: click, type, screenshot, move, scroll.
    REQUIRES: User must approve via UI confirmation dialog before execution.
    """
    if action == "screenshot":
        path = f"reports/desktop_{int(time.time())}.png"
        pyautogui.screenshot(path)
        return {"path": path}

    elif action == "click":
        pyautogui.click(x, y)
        return {"clicked": f"({x}, {y})"}

    elif action == "type":
        pyautogui.typewrite(text, interval=0.02)
        return {"typed": text[:50]}

    # ... etc
```

**Security:** Computer automation MUST require user confirmation via a modal dialog before every action. Add a guardrail in the agent harness.

#### Key Files
- New: `backend/tools/browser_automation.py` — Playwright-based browser control
- New: `backend/tools/computer_automation.py` — pyautogui desktop control
- `backend/tools/__init__.py` — add tool schemas
- `backend/tools/tool_dispatcher.py` — register new tools
- `requirements.txt` — add `playwright`, `pyautogui`
- `preload.js` — add IPC handler for user consent dialog

---

## 7. Handling Performance Fluctuations

### Concept

LLM performance varies due to:
- **Provider load**: Gemini/Groq rate limits or degraded responses under load
- **Temperature variance**: Same prompt, different quality responses
- **Context length**: Quality degrades as context grows beyond 4K tokens
- **Model updates**: Provider silently updates model, behavior changes

### Implementation Plan

#### Strategy 1: Quality Scoring

Add a lightweight quality check after every response:

```python
# backend/ai/quality.py

def score_response(query: str, response: str, task_type: str) -> float:
    """Heuristic quality score (0-1) without an LLM call."""
    score = 1.0

    # Penalty: response is too short for the query
    if len(response) < 50 and len(query) > 100:
        score -= 0.3

    # Penalty: response contains hedging language
    hedges = ["i'm not sure", "i think", "possibly", "maybe", "it might"]
    hedge_count = sum(1 for h in hedges if h in response.lower())
    score -= hedge_count * 0.1

    # Penalty: response doesn't reference project-specific terms
    project_terms = ["jarvis", "electron", "fastapi", "websocket", "ollama"]
    if task_type in ("error_diagnosis", "quick_qa"):
        term_hits = sum(1 for t in project_terms if t in response.lower())
        if term_hits == 0:
            score -= 0.2  # Generic answer, not grounded

    # Penalty: error diagnosis without CAUSE/FIX format
    if task_type == "error_diagnosis":
        if "CAUSE:" not in response or "FIX:" not in response:
            score -= 0.4

    return max(0.0, min(1.0, score))
```

#### Strategy 2: Automatic Retry on Low Quality

```python
# In claude_client.py run() function

response_text = await _stream_text(text, send_event)
quality = score_response(query, response_text, task_type)

if quality < 0.5 and iteration == 0:
    logger.warning(f"Low quality response ({quality:.2f}), retrying with higher temperature")
    # Retry with slightly different parameters
    response_text = await _retry_with_params(
        query, mode, messages, send_event,
        temperature=params["temperature"] + 0.1,
    )
```

#### Strategy 3: Provider Health Tracking

```python
# backend/ai/provider_health.py

class ProviderHealth:
    """Track provider reliability and latency."""

    def __init__(self):
        self.stats = {}  # provider_name -> {successes, failures, avg_latency, last_error}

    def record(self, provider: str, success: bool, latency_ms: int, error: str = None):
        if provider not in self.stats:
            self.stats[provider] = {"successes": 0, "failures": 0, "total_latency": 0, "calls": 0}
        s = self.stats[provider]
        s["calls"] += 1
        s["total_latency"] += latency_ms
        if success:
            s["successes"] += 1
        else:
            s["failures"] += 1
            s["last_error"] = error

    def get_reliability(self, provider: str) -> float:
        s = self.stats.get(provider, {"successes": 0, "calls": 1})
        return s["successes"] / max(s["calls"], 1)

    def get_avg_latency(self, provider: str) -> float:
        s = self.stats.get(provider, {"total_latency": 0, "calls": 1})
        return s["total_latency"] / max(s["calls"], 1)
```

#### Strategy 4: Context Window Management

```python
def _trim_history(messages: list) -> list:
    """Smart trimming: keep system + first user message + last N exchanges."""
    if len(messages) <= 4:
        return messages

    system = messages[0]
    first_user = messages[1]
    recent = messages[-6:]  # Keep last 3 exchanges

    # Summarize dropped messages
    dropped = messages[2:-6]
    if dropped:
        summary = f"[{len(dropped)} earlier messages summarized: discussed {_extract_topics(dropped)}]"
        return [system, first_user, {"role": "user", "content": summary}] + recent

    return messages
```

#### Key Files
- New: `backend/ai/quality.py` — response quality scoring
- New: `backend/ai/provider_health.py` — provider reliability tracking
- `backend/ai/claude_client.py` — integrate quality checks and retries

---

## 8. Security Fundamentals

### Concept

80/20 security: the 20% of practices that prevent 80% of vulnerabilities.

### Critical Issues in JARVIS

#### Issue 1: API Keys in Chat History

**Risk:** Chat history is stored in memory and potentially in localStorage. API keys could be exposed if a user pastes a `.env` file or error log containing keys.

**Current state:**
- `session_history` in `main.py` stores raw conversation content
- localStorage stores conversations (after our fix) in plain text
- Backend logs to `error.log` which may contain API calls with keys

**Fix:**

```python
# backend/ai/security.py

import re

# Patterns that match common API key formats
_KEY_PATTERNS = [
    re.compile(r'(AIza[A-Za-z0-9_-]{35})'),           # Google/Gemini
    re.compile(r'(gsk_[A-Za-z0-9]{48,})'),              # Groq
    re.compile(r'(sk-[A-Za-z0-9]{32,})'),               # OpenAI
    re.compile(r'(ghp_[A-Za-z0-9]{36})'),               # GitHub
    re.compile(r'(AKIA[A-Z0-9]{16})'),                   # AWS
]

def redact_keys(text: str) -> str:
    """Replace API keys with [REDACTED] in any text."""
    for pattern in _KEY_PATTERNS:
        text = pattern.sub('[REDACTED]', text)
    return text

def sanitize_for_logging(text: str) -> str:
    """Redact keys and truncate for safe logging."""
    return redact_keys(text)[:500]
```

**Apply in:**
- `claude_client.py` — redact query and response before logging
- `main.py` — redact session_history before saving to jarvis.json
- Frontend — redact before saving to localStorage

#### Issue 2: Hallucinated NPM Packages

**Risk:** When the AI suggests installing packages, it may hallucinate package names that don't exist on npm. Malicious actors publish typosquat packages that steal credentials.

**Fix:** Add a guardrail in the system prompt:

```
<security_rules>
NEVER suggest installing a package you have not verified exists.
When recommending npm packages:
1. Only recommend packages you are confident exist (widely known, part of major frameworks)
2. If uncertain, tell the user to verify on npmjs.com before installing
3. NEVER suggest packages with names you are constructing by combining words
</security_rules>
```

#### Issue 3: Row-Level Security for Multi-User

**Current state:** JARVIS is single-user. If extended to multi-user:

```python
# backend/middleware/auth.py

class UserContext:
    """Enforce user-scoped access to project memory."""

    def __init__(self, user_id: str):
        self.user_id = user_id

    def can_read(self, resource: str) -> bool:
        """Check if user has read access to a resource."""
        # For now, all authenticated users can read
        return True

    def can_write(self, resource: str) -> bool:
        """Check if user has write access to a resource."""
        # Only project owners can modify jarvis.json
        return resource != "jarvis.json" or self._is_owner()
```

#### Issue 4: URL Exposure Prevention

**Risk:** Report generation creates HTML files in `reports/`. If the backend serves static files, these could be publicly accessible.

**Fix:**
- Reports are opened via Electron's `shell.openPath()` (local only)
- Backend does NOT serve `reports/` directory as static files
- Ensure `reports/` is in `.gitignore` (it already is)
- Add a check in preload.js to verify reports aren't accessed from network

#### Issue 5: Sandbox & CSP

**Current state:** `main.js` line 58: `sandbox: false` — preload has full Node.js access.

**Recommended improvement:**
```javascript
// main.js — Content Security Policy
mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
    callback({
        responseHeaders: {
            ...details.responseHeaders,
            'Content-Security-Policy': [
                "default-src 'self'; " +
                "script-src 'self'; " +
                "style-src 'self' 'unsafe-inline'; " +  // Needed for styled-components
                "connect-src 'self' ws://localhost:8765; " +  // WebSocket only
                "img-src 'self' data:; "
            ]
        }
    });
});
```

#### Security Checklist

| # | Practice | Status | Priority |
|---|----------|--------|----------|
| 1 | API keys not in chat history | Not implemented | HIGH |
| 2 | API keys not in localStorage | Not implemented | HIGH |
| 3 | API keys not in error logs | Not implemented | HIGH |
| 4 | Hallucinated package guard | Not implemented | MEDIUM |
| 5 | CSP headers set | Not implemented | MEDIUM |
| 6 | Report files not served over network | Already safe | OK |
| 7 | `.env` in `.gitignore` | Already done | OK |
| 8 | Preload validates file paths | Already done | OK |
| 9 | DOMPurify sanitizes markdown | Already done | OK |
| 10 | WebSocket local-only (localhost) | Already done | OK |

#### Key Files
- New: `backend/ai/security.py` — key redaction, sanitization
- `backend/ai/claude_client.py` — apply redaction to logging
- `backend/main.py` — redact session history
- `backend/ai/prompts.py` — add `<security_rules>` block
- `main.js` — add CSP headers
- `preload.js` — tighten path validation

---

## Implementation Priority

| Phase | Feature | Effort | Impact | Dependencies |
|-------|---------|--------|--------|-------------|
| **Now** | Security: API key redaction | 2 hrs | Critical | None |
| **Now** | System prompt: failure log | 3 hrs | High | `.claude/` directory |
| **Week 1** | Agent harness class | 4 hrs | High | None |
| **Week 1** | Context & workspace management | 3 hrs | Medium | `.claude/` directory |
| **Week 1** | Performance: quality scoring | 2 hrs | Medium | None |
| **Week 2** | Fan-out research | 6 hrs | High | Agent harness |
| **Week 2** | Browser automation (Tier 2) | 4 hrs | Medium | Playwright |
| **Month 1** | Auto research loop | 8 hrs | High | Quality scoring |
| **Month 1** | Computer automation (Tier 3) | 6 hrs | Low | User consent UI |
| **Month 1** | Provider health tracking | 3 hrs | Medium | None |
