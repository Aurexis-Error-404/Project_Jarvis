# JARVIS — Advanced Features Implementation Plan

**Date:** 2026-04-20
**Branch:** `merged` (commit `5592777`)
**Scope:** Execute the 8 features in [JARVIS_ADVANCED_FEATURES_GUIDE.md](./JARVIS_ADVANCED_FEATURES_GUIDE.md), plus three new asks:
1. Boot-time **JARVIS assembling animation** on the splash screen.
2. **Professional per-report-type templates** (Overleaf-style).
3. **Voice integration guide** (delivered separately at [JARVIS_VOICE_INTEGRATION_GUIDE.md](./JARVIS_VOICE_INTEGRATION_GUIDE.md)).

**Mode:** this is a plan for review. **Do not implement yet.** After the plan passes adversarial review, work is split into tickets and shipped in the order in §14.

---

## Table of Contents

1. [Guiding principles](#1-guiding-principles)
2. [Feature 1 — Advanced System Prompts](#2-feature-1--advanced-system-prompts)
3. [Feature 2 — Agent Harness class](#3-feature-2--agent-harness-class)
4. [Feature 3 — Parallelization & sub-agents](#4-feature-3--parallelization--sub-agents)
5. [Feature 4 — Context & workspace management](#5-feature-4--context--workspace-management)
6. [Feature 5 — Auto research loop](#6-feature-5--auto-research-loop)
7. [Feature 6 — Internet & computer automation](#7-feature-6--internet--computer-automation)
8. [Feature 7 — Performance fluctuation handling](#8-feature-7--performance-fluctuation-handling)
9. [Feature 8 — Security fundamentals](#9-feature-8--security-fundamentals)
10. [New — Boot assembling animation](#10-new--boot-assembling-animation)
11. [New — Per-report-type professional templates](#11-new--per-report-type-professional-templates)
12. [Voice integration](#12-voice-integration-cross-reference)
13. [Refactoring opportunities (report only, no changes yet)](#13-refactoring-opportunities-report-only-no-changes-yet)
14. [Sequenced implementation order & gates](#14-sequenced-implementation-order--gates)
15. [Verification matrix](#15-verification-matrix)
16. [Open questions for the user](#16-open-questions-for-the-user)
17. [Review history](#17-review-history)

---

## 1. Guiding principles

- **Never break the happy path.** Every feature ships behind an env flag or a runtime guard so the plain chat workflow always works, even with an unconfigured machine.
- **Local-first mode is sacred.** Any new cloud call must be explicitly gated on `mode === 'cloud'`. No silent leaks.
- **Additive only.** No refactor bundled with a feature. Refactor opportunities are listed in §13 and executed in separate tickets.
- **Measurable.** Every feature has a concrete verification step in §15 before it's called done.
- **Locked artifacts are locked.** Per CLAUDE.md, WebSocket event names, port 8765, and the `jarvis.json` schema can only change with explicit decisions in `jarvis.json`.
- **Foundational correctness first.** Any audit-level defect on a code path a new feature will touch is a blocker, not a follow-up. Enumerated in §13.0.

---

## 2. Feature 1 — Advanced System Prompts

### 2.1 Target state
- `.claude/` directory with human-editable prompt overrides.
- System prompt builder consumes optional user preferences, failure log, success log, and capability map.
- Post-query hook appends to failure/success logs when heuristics fire.

### 2.2 Files to create
- `.claude/user_preferences.md` (committed, default content).
- `.claude/capability_map.md` (committed, mirrors the current tool roster in `backend/tools/__init__.py`).
- `.claude/failure_log.md`, `.claude/success_log.md` (gitignored, auto-maintained).
- `backend/memory/prompt_log.py` — read/write helpers for the four files.

### 2.3 Files to modify
- `backend/ai/prompts.py` — extend `build_system_prompt(...)` with `user_prefs`, `failure_log`, `capability_map` args; append new blocks to the dynamic block **only when non-empty** so token budget stays ≤5k.
- `backend/ai/claude_client.py` — inside `run()`, load prompts and pass them; after finish, call `prompt_log.post_query_hook(query, response, tool_calls_made)`.
- `.gitignore` — add `.claude/failure_log.md`, `.claude/success_log.md`, `.claude/cache/`, `.claude/temp/`.

### 2.4 Guardrails
- **Budget:** a unit test fails if the assembled prompt exceeds 6k tokens (using tiktoken or a char/4 estimate). Keep last-10 failures only; truncate.
- **Silent failure:** if `.claude/` files are missing/malformed, builder logs a warning and falls back to the current behaviour — never raises.
- **Not a chatty log.** Heuristic must be tight (explicit user correction phrases + repeat-question detection). Noisy logs poison the next prompt.

### 2.5 Known pitfall to avoid
The guide shows `open(path)` with no encoding. Use `encoding="utf-8"` and wrap in try/except — this was audit issue **CRIT-2 / MED-1**.

---

## 3. Feature 2 — Agent Harness class

### 3.1 Target state
- `JarvisAgent` class owns the tool-use loop state that is currently held in `_run_tool_loop` locals.
- `claude_client.run()` becomes a thin wrapper that instantiates and drives the agent.
- Pre-tool and post-tool guardrail hooks exist but default to no-ops.

### 3.2 Files to create
- `backend/ai/agent.py` with `JarvisAgent` — constructor + `run`, `_build_messages`, `_call_llm`, `_is_final`, `_execute_tools`, `_stream_response`, `_pre_tool_check`, `_post_tool_check`, `observations: list[dict]`.

### 3.3 Files to modify
- `backend/ai/claude_client.py` — `run()` delegates to `JarvisAgent`. Keep `_stream_final_response`, `_stream_text`, `_call_with_fallback`, `_task_type` helpers where they are; the agent calls them.
- `backend/tools/tool_dispatcher.py` — accept optional `pre_hook`, `post_hook` arguments so the agent can inject without globals.

### 3.4 Guardrails
- The class must **not** introduce new global state. Current module-level caches (`_clients`) stay module-level.
- **Identical behavior** in the default path — any observable change (streaming timing, error payload shape, event order) is a bug, not a feature.
- Keep `MAX_TOOL_ITERATIONS`, `MAX_TOOL_OUTPUT_CHARS`, `HISTORY_TOKEN_BUDGET` as module constants — don't move them into the class.

### 3.5 Tests to add
- `tests/test_agent.py` — covers: final-response-no-tools, one-tool-call-then-final, max-iterations, pre-hook-blocks, post-hook-rewrites-result, tool-timeout.

---

## 4. Feature 3 — Parallelization & sub-agents

### 4.1 Target state
- `backend/ai/orchestrator.py` with three strategies:
  - `fan_out_research(query, mode, send_event)` — 3 parallel sub-queries, merged.
  - `consensus_diagnosis(query, mode)` — 3 parallel diagnoses, majority vote on the `CAUSE:` line.
  - `pipeline_query(query, mode, send_event)` — classify → deep → format.
- `claude_client.run()` routes to orchestrator when the task type + query signals indicate a complex flow (e.g., "research AND compare", "why is X failing").

### 4.2 Concurrency constraints
- Use `asyncio.gather(..., return_exceptions=True)`. Any sub-agent failure yields a degraded-but-valid result, never a top-level exception.
- **Rate limits matter.** Gemini free tier is 15 req/min. 3 parallel = 3 req; if followed by a merge call that's 4. A second parallel query within 60 s would exceed limits. Add a token-bucket in `provider_health.py` (see §8) before enabling fan-out by default.
- Tool-using sub-agents are cheap to run but costly to log. Stream tool-call events **only from the merge agent**, not from sub-agents (`send_event=None` for sub-agents) — the guide already shows this.

### 4.3 Files to create
- `backend/ai/orchestrator.py`.

### 4.4 Files to modify
- `backend/ai/claude_client.py` — feature flag `PARALLEL_AGENTS_ENABLED` gate; otherwise single-agent path is unchanged.

### 4.5 Open risk
The guide's `_generate_search_variants` is hand-waved. Detail the prompt it uses; otherwise the three variants will be near-duplicates and the fan-out delivers no value. Include the variant-generation prompt in the ticket.

---

## 5. Feature 4 — Context & workspace management

### 5.1 Target state
- `Workspace` class wraps the project directory's `.claude/` subtree.
- Multi-project isolation: JARVIS reads the PROJECT_PATH-scoped `.claude/` rather than the JARVIS repo's `.claude/`.
- `active/` and `archive/` subdirectories for in-flight agent work.

### 5.2 Files to create
- `backend/context/workspace.py`.

### 5.3 Files to modify
- `backend/ai/prompts.py` — accept a `workspace: Workspace` arg, merge its `system_prompt.md` into the static block.
- `backend/ai/claude_client.py` / `backend/main.py` — thread a `project_path: str` parameter down from the WebSocket session through `claude_run(...)` and into `JarvisAgent`. The ws handler stores `project_path` on a per-connection dict (alongside `session_history`). `PROJECT_PATH` env var becomes a **default only**, consulted when the session has not set one. `set_project_path` updates session state, not `os.environ`.
- `.gitignore` at repo root — document the convention (already covers `.claude/cache/` etc.).

### 5.4 Guardrails
- A workspace **must never** be allowed to escape the session's `project_path`. Validate that resolved paths stay inside the root, like the existing preload path check.
- A missing `.claude/` inside the session `project_path` is normal — do not auto-create it without the user opting in (avoid polluting their repo silently).
- **Concurrent-session safety:** two Electron windows, each pointing to a different project, must produce completely disjoint reads and writes under `.claude/`, `reports/`, and log output. A regression test (§15) exercises two live ws connections simultaneously.

### 5.5 Concurrency requirement

The `_current_mode` global and any session-scoped state (`project_path`, `session_history`) must be **per-WebSocket-connection** — no process-global writes from handlers. Mode change on one ws must not flip the mode on a concurrent ws. This is the same trust boundary as R-5 (§13.0) and is non-negotiable for multi-window support. Enforcement lands in Phase 2A.0 before §5's `Workspace` class is built on top of session state.

---

## 6. Feature 5 — Auto research loop

### 6.1 Target state
- `AutoResearchLoop` runs a test→assess→improve cycle up to N iterations or until a threshold is hit.
- Reachable via a new query heuristic: phrases like "keep improving", "iterate on", "optimize until".
- Each iteration streams a status update to the frontend.

### 6.2 Files to create
- `backend/ai/auto_research.py`.
- `src/components/AutoResearchProgress.jsx` — small card showing iteration count, current score, best score.

### 6.3 Files to modify
- `backend/ai/claude_client.py` — intent detection → orchestrator routing.
- `src/hooks/useJarvisEvents.js` — handle new `auto_research_progress` event.
- `src/constants/wsEvents.js` — add `RECV.AUTO_RESEARCH_PROGRESS`.

### 6.4 Guardrails
- Hard cap: `AUTO_RESEARCH_MAX_ITERATIONS` default 5 (not 10 as the guide shows — cost runaway risk).
- Budget cap: each loop stores `total_cost_usd` (estimated from token counts) and halts if it exceeds `AUTO_RESEARCH_MAX_COST_USD` (default 0.25).
- Never auto-start. User must trigger with an explicit keyword match or a button.

---

## 7. Feature 6 — Internet & computer automation

### 7.1 Tier 2 — Browser automation (Playwright) — DEFERRED

**Deferred to Phase 2E alongside Tier 3.** Browser automation cannot ship before the per-action consent + audit framework required for computer automation is in place. Even with domain allowlisting, an authenticated session on an allowed domain can leak page content into chat history and reports (the AI can still read DOM + take screenshots on a logged-in page). The consent framework (§7.2's `ConsentDialog` + `_pre_tool_check` pattern) is a prerequisite for both tools. The original design notes are preserved in §7.6 as a design appendix so the implementation is ready to lift once consent lands.

### 7.2 Tier 3 — Computer automation (pyautogui)

Accept the guide's design, with a hard requirement:
- **Every call requires a user confirmation dialog** via a new IPC handler (`preload.js::requestComputerActionConsent(payload)`). No exceptions.
- Guardrail lives in the agent (`_pre_tool_check`), not in the tool — so the dialog fires before `dispatch_tool` ever runs.
- Default state is **off** (`COMPUTER_AUTOMATION_ENABLED=false`). Documented risk in the settings UI.

### 7.3 Files to create
- `backend/tools/browser_automation.py`.
- `backend/tools/computer_automation.py`.
- `src/components/ConsentDialog.jsx`.

### 7.4 Files to modify
- `backend/tools/__init__.py` — conditional tool registration.
- `backend/tools/tool_dispatcher.py` — no structural change, but the dispatcher must surface consent events.
- `electron/preload.js` — `requestComputerActionConsent(payload)` IPC.
- `electron/main.js` — register consent dialog.
- `requirements.txt` — add `playwright==1.49.0`, `pyautogui==0.9.54` (both optional — see §13 for the gating convention).

### 7.5 Open risk
pyautogui on Wayland/Linux is flaky. Document the Linux caveat in the ticket; do not silently fall back.

### 7.6 Design appendix — browser automation (lifts when §7.1 unblocks)

Original Tier 2 design, ready to ship once the consent framework in §7.2 lands:
- Register `browser_automation` tool in `backend/tools/__init__.py` **only when** `pip show playwright` succeeds — fail-closed if not installed.
- Add a per-domain allowlist env var `BROWSER_ALLOW_DOMAINS="github.com,stackoverflow.com,docs.python.org"` so the AI can't fetch arbitrary URLs silently.
- Screenshots go to `.claude/temp/browser/` (inside workspace), not `reports/`. Reports are for user-facing deliverables only.
- **Unblock precondition:** every navigation, DOM read, and screenshot routes through the same `ConsentDialog` + audit log used by computer automation. No per-tool bypass.

---

## 8. Feature 7 — Performance fluctuation handling

### 8.1 Target state
- `quality.py::score_response` heuristic scorer with unit tests.
- `provider_health.py` tracks per-provider success/failure/latency.
- Low-quality responses auto-retry once, with bumped temperature. Only on first iteration, never inside the tool loop.
- `provider_health` informs `_call_with_fallback` — a provider with <60% success over the last 20 calls drops to the back of the chain for 5 min.

### 8.2 Files to create
- `backend/ai/quality.py`.
- `backend/ai/provider_health.py`.

### 8.3 Files to modify
- `backend/ai/claude_client.py` — integrate scorer and retry.
- `backend/ai/providers.py` — consult `provider_health` when building the fallback chain.

### 8.4 Guardrails
- Quality scoring is **heuristic and cheap** (regex, no LLM). The guide's version is a good starting point; keep it under 20 ms.
- `_trim_history` smart-trim: keep system + first user + last 3 exchanges; summarize the middle. **Do not** call an LLM to summarize synchronously — store a pre-computed summary field on each dropped message, or just bullet the tool names.
- **Race condition risk:** `ProviderHealth.stats` is shared across WS handlers. Wrap mutations with `asyncio.Lock` — audit issue HIGH-1 pattern.

---

## 9. Feature 8 — Security fundamentals

### 9.1 Mandatory (ship with Phase 2 start)
- `backend/ai/security.py::redact_keys` + `sanitize_for_logging`.
- Apply redaction in three places:
  - `claude_client.py` before any `logger.info(query)` / `logger.info(response)`.
  - `backend/memory/session_log.py` before persisting to `jarvis.json`.
  - Frontend `src/hooks/useConversations.js` before `localStorage.setItem` — mirror the regex list.
- `<security_rules>` block in `prompts.py` (hallucinated-package guard).
- Electron CSP headers in `electron/main.js` — exact CSP from the guide.
- Remove `sandbox: false` where it is no longer justified; if it stays, document why in a code comment.

### 9.2 Deferred (ship with voice)
- Multi-user row-level security. JARVIS is single-user today; no benefit paying this cost until voice/wake-word opens remote-access surface.

### 9.3 Known regression risk
The redaction regex is a cross-cutting concern. Mis-regex can mangle legitimate content (e.g., a commit hash that matches `AIza...`). Unit-test with real-world positives *and* a negative corpus (commit hashes, base64 strings, package names) before enabling.

---

## 10. NEW — Boot assembling animation

### 10.1 Concept

Replace the current static `<h1>J.A.R.V.I.S</h1>` on the splash screen with an animation where the letters fly in from random positions, briefly overshoot, then snap into place, followed by a sweeping HUD ring and the subtitle. This fires **once per Electron launch** and skips on manual splash returns (we already track `manualSplashRef`).

### 10.2 Design

- Pure CSS + React; no new dependency.
- Uses `prefers-reduced-motion` to short-circuit to the current static state — accessibility matters.
- Timing: 1.4 s for the full sequence. Splash auto-dismisses at 1.5 s (`SPLASH_DISMISS_MS`), so the animation completes just as the chat opens.

### 10.3 Animation phases

| t (ms) | Event |
|-------:|-------|
|     0  | Splash mounted. Letters positioned off-screen with random `(x, y, rotate)`. |
|  0–800 | Each letter tweens to final position using `cubic-bezier(.2, 1.2, .3, 1)` — 80 ms stagger per letter. |
|  600–900 | Subtitle fades in from 0 → 1 opacity, translateY(8 → 0). |
|  700–1100 | HUD ring sweeps a 360° arc under the title (SVG `stroke-dashoffset` animation). |
| 1000–1400 | System badge pulses once, `SYSTEM ONLINE` glows from 40% → 100% opacity. |

### 10.4 Files to modify
- `src/components/SplashScreen.jsx` — replace the static heading with a new `<AssemblingTitle />` child; gate on `prefers-reduced-motion`.
- `src/styles/components.css` — add `@keyframes jarvis-assemble-*`, `.letter`, `.hud-ring`, `.splash-pulse`.
- (no constant changes — `SPLASH_DISMISS_MS` stays at 1500).

### 10.5 New component

```jsx
// src/components/AssemblingTitle.jsx (sketch — not final code)
const LETTERS = ['J', 'A', 'R', 'V', 'I', 'S'];

export default function AssemblingTitle() {
  const reduceMotion = useReducedMotion();
  return (
    <div className={`assembling-title ${reduceMotion ? 'static' : 'animate'}`}>
      <svg className="hud-ring" viewBox="0 0 200 200" aria-hidden="true">
        <circle cx="100" cy="100" r="92" className="hud-ring-arc" />
      </svg>
      <h1 aria-label="JARVIS">
        {LETTERS.map((ch, i) => (
          <span
            key={i}
            className="letter"
            style={{
              '--i': i,
              '--rx': `${rand(-400, 400)}px`,
              '--ry': `${rand(-200, 200)}px`,
              '--rz': `${rand(-60, 60)}deg`,
            }}
          >
            {ch}
          </span>
        ))}
      </h1>
    </div>
  );
}
```

### 10.6 Guardrails
- Must **not** delay `connected` → chat transition. If the WebSocket connects before the animation finishes, we still wait until `SPLASH_DISMISS_MS` to avoid jarring reflow — but no longer.
- `prefers-reduced-motion: reduce` → render the final frame statically, no transforms.
- No layout shift after animation — final letter positions are pre-computed with absolute positioning so the header stays pixel-stable for the rest of the session.

### 10.7 Verification
- Start the app cold with `npm start` → animation plays once.
- Hit Escape → splash re-shows **without** re-playing (manual return path).
- Set browser DevTools → Rendering → `prefers-reduced-motion: reduce` → animation is skipped; static title shows immediately.

---

## 11. NEW — Per-report-type professional templates

### 11.1 Problem with current state
Today `report_generator.py::run` has one template (`backend/templates/report.html`) for every kind of report. The look is clean but generic; a git summary looks the same as a research report looks the same as a codebase audit. Users asked for an **Overleaf-style** academic layout: structured front matter, numbered sections, figures, citations list.

### 11.2 Target state
Introduce a **`report_type` parameter** on the `generate_html_report` tool. The generator picks a template based on the type.

Report types & their template files:

| `report_type` | Template | When the AI uses it |
|--------------|----------|-----|
| `research`   | `research_report.html` | Default for research queries — matches current behaviour |
| `diagnosis`  | `diagnosis_report.html` | Error diagnosis summaries (CAUSE/FIX/ALSO CHECK) |
| `git_summary`| `git_summary_report.html` | Changelog / commit rollup |
| `audit`      | `audit_report.html` | Codebase audits (like `JARVIS_CODEBASE_AUDIT.md`) |
| `executive`  | `executive_summary.html` | Short high-level briefings |
| `general`    | `general_report.html` | Fallback, styled like the current report |

### 11.3 Shared template infrastructure

All templates extend a `base_report.html` (Jinja2 inheritance), which provides:
- **Title page block** — title, authors ("JARVIS, {project name}"), date, project stack badges.
- **Abstract/TL;DR block**.
- **Table of contents** — auto-generated from section headings.
- **Section numbering** — 1, 1.1, 1.1.1 via CSS counters.
- **Bibliography/citations block** — rendered from `research_data` JSON.
- **Page numbering and headers** via `@page` CSS (print-media perfect).

### 11.4 Style guidance (Overleaf-style)

- Serif body: `Charter, Cambria, Georgia, serif` for reading; sans-serif headings (`Inter, Helvetica`). Dark-mode toggle via `prefers-color-scheme`.
- 72-char line length.
- Fixed-width captions under figures: `Figure 1.1: ...`.
- Numbered references in the body as `[3]`, collated in a bibliography at the end.
- Print CSS: A4 + 2.5 cm margins, page breaks between sections with `break-before: page`.

### 11.5 Per-type specializations

- **`diagnosis_report.html`** — top card with severity, impact radius, root-cause line; collapsed stack trace; "ALSO CHECK" as a secondary list; no bibliography section.
- **`git_summary_report.html`** — commit table (hash, author, date, subject); diff stats chart (simple bar, inline SVG); "risk areas" callout; no abstract.
- **`audit_report.html`** — severity-grouped sections (critical/high/medium/low); per-issue cards with file + line + fix; executive summary table at top.
- **`executive_summary.html`** — single-page layout, 5 bullets max, "what's next" callout.
- **`research_report.html`** — closest to current template; adds abstract, references, and appendix for raw data.
- **`general_report.html`** — base template with no specialization.

### 11.6 Files to create
- `backend/templates/base_report.html` — Jinja2 inheritance root.
- `backend/templates/research_report.html`
- `backend/templates/diagnosis_report.html`
- `backend/templates/git_summary_report.html`
- `backend/templates/audit_report.html`
- `backend/templates/executive_summary.html`
- `backend/templates/general_report.html`
- `backend/templates/_partials/toc.html`
- `backend/templates/_partials/bibliography.html`
- `backend/static/report.css` — shared stylesheet (inlined at render time for single-file portability).

### 11.7 Files to modify
- `backend/tools/report_generator.py`:
  - Add `report_type: str = "research"` parameter.
  - Template selector: `TEMPLATES = {"research": "research_report.html", ...}`.
  - Default to `general_report.html` when `report_type` is unknown (log a warning).
  - Remove `_render_fallback` — every case now has a real template.
- `backend/tools/__init__.py` — extend the tool schema:
  ```json
  {
    "report_type": {
      "type": "string",
      "enum": ["research", "diagnosis", "git_summary", "audit", "executive", "general"],
      "description": "Picks the report template. Use 'research' by default.",
      "default": "research"
    }
  }
  ```
- `backend/ai/prompts.py` — in `<research_report_rules>`, add guidance on picking the right `report_type`.

### 11.8 Guardrails
- Autoescape behavior stays the same — markdown → HTML happens in the generator, template injects pre-escaped HTML.
- `base_report.html` uses `{% block %}` / `{% extends %}` correctly; avoid Jinja2 `{% include %}` with unescaped content.
- Backwards compatibility: if an older LLM response omits `report_type`, fall back to `research` (closest to today's behaviour).

### 11.9 Verification
- Generate one of each type (test harness can call the tool directly in `tests/test_report_generator.py`).
- Open each HTML in the browser — check layout, print preview, dark mode toggle.
- Run with the `new` Electron "Open Report" flow — no URL-escaping regression.

---

## 12. Voice integration (cross-reference)

See [docs/JARVIS_VOICE_INTEGRATION_GUIDE.md](./JARVIS_VOICE_INTEGRATION_GUIDE.md).

Not in Phase 2 scope. Listed here so the phase-3 sequencing in §14 is complete.

---

## 13. Refactoring opportunities

### 13.0 Phase 2A blockers (promoted from the deferred list)

The following are **not optional refactors**. The Codex adversarial review (2026-04-20) flagged each as a correctness defect on a code path that Phase 2 features will extend. They ship before any work in §§2, 3, 4, 5, 6, 7, or 8 touches the same files.

| # | File / area | Defect | Acceptance test |
|---|-------------|--------|-----------------|
| R-2 | `backend/ai/claude_client.py:360-361` | Truncated tool result emits malformed JSON (`result_json[:N] + '..."}'`) — LLM then reasons over broken JSON | `tests/test_claude_client.py::test_truncated_tool_result_is_valid_json` — dispatch a tool whose stringified result exceeds `MAX_TOOL_OUTPUT_CHARS`; assert `json.loads(result)` succeeds and produces `{"truncated": true, "partial_data": "...", "note": "..."}` |
| R-3 | `backend/tools/tool_dispatcher.py:43-47` | Sync tools run without `asyncio.wait_for`; `read_codebase` on huge dirs hangs the agent loop forever | `tests/test_tool_dispatcher.py::test_sync_tool_hits_timeout` — register a sleep-forever tool; assert the dispatcher returns a structured timeout error within 60 s and does not leak the executor thread |
| R-5 | `backend/main.py` | `_current_mode` mutated process-globally by every `mode_change` handler; two ws clients share one variable | `tests/test_main.py::test_concurrent_sessions_have_independent_mode` — open two mocked ws clients; one switches to `cloud`; assert the other still reads `local` on its next `user_query` |

These three unlock §§5 and 8, which both expand the affected surfaces. R-5 is the linchpin for §5.5's per-session mandate.

### 13.1 Deferred refactor candidates (report only, no changes yet)

Known improvements surfaced during codebase review. **Not in scope for this plan.** Each is a candidate for its own PR after the advanced features land.

| # | File / area | Issue | Why it matters | Proposed fix (later) |
|---|-------------|-------|----------------|----------------------|
| R-1 | `backend/ai/prompts.py:122` | `open(path)` without `encoding="utf-8"`; no try/except | Crashes on Windows non-UTF-8 locales (audit MED-1, CRIT-2) | Wrap in try/except; always pass `encoding="utf-8"`; fall back to a minimal default `jarvis.json` shape |
| R-4 | `backend/tools/report_generator.py:230-268` | `_render_fallback` duplicates template styling | Dead code after templates are added — drift risk | Remove the function; if `report.html` is missing, raise a clear error at startup |
| R-6 | `backend/context/file_watcher.py:64-66` | `_last_event` dict mutated across threads without lock | Data race (audit MED-2) | `threading.Lock` around mutations |
| R-7 | `src/styles/components.css` | 611 lines in one file | Hard to maintain, hot-reload is slow | Split into `buttons.css`, `surface.css`, `splash.css`, `input.css`; barrel via `index.css` |
| R-8 | `src/App.jsx` | Drills `dispatch`, `setIsStreaming`, refs through hooks | Signature churn every time a handler moves | Introduce a small `AppContext` provider, only for the wiring — not a full Redux move |
| R-9 | `src/hooks/useConversations.js` | `localStorage` unbounded growth | Can exceed 5-10 MB over months (audit MED-5) | Cap to most-recent 50 conversations; summarize the rest |
| R-10 | `electron/main.js:?` | `sandbox: false` | Preload has full Node access — larger attack surface than needed | Re-evaluate once CSP is in; consider `sandbox: true` + `contextBridge.exposeInMainWorld` |
| R-11 | `backend/tools/__init__.py` | 284-line module with all schemas inline | Hard to grep one tool, heavy imports | Split into `tool_schemas/{tool_name}.py`, barrel in `__init__.py` |
| R-12 | `test_prompt.py` / `tests/` | Bare `except:` clauses (audit LOW-6) | Swallows `KeyboardInterrupt` | Narrow to specific exceptions |

Agreement to fix is **not** implied by inclusion here — each needs its own approval gate.

---

## 14. Sequenced implementation order & gates

Each "gate" is a point where we stop, verify, and decide to continue. No feature moves past its gate without the verification steps in §15 passing.

### Phase 2A.0 — Blockers (estimated: 1 session)
0. Land **R-2** (tool JSON truncation), **R-3** (sync tool timeout), **R-5** (per-session mode). Each paired with the regression test defined in §13.0.

**Gate 2A.0:** All three regression tests green. No behaviour change in single-client mode (existing smoke tests must still pass). Nothing in Phase 2A/B/C begins until this gate closes — the rest of the plan assumes correct tool-result JSON, bounded tool execution, and per-session mode state.

### Phase 2A — Foundation (estimated: 1-2 sessions)
1. **Security redaction** (§9.1) — ship first so every subsequent feature benefits.
2. **Workspace class + `.claude/` structure** (§5) — unblocks system prompt features; builds on the per-session state landed in Phase 2A.0.
3. **Agent Harness class** (§3) — no behaviour change, just the structure.

**Gate 2A:** All existing smoke tests pass. `npm run build` clean. No regression in normal chat. Two concurrent ws sessions with different `project_path` do not cross-pollute reads/writes (see §15 row "Workspace (concurrent)").

### Phase 2B — Intelligence (estimated: 2-3 sessions)
4. **Advanced system prompts** (§2) — preferences, failure log, capability map.
5. **Quality scoring + provider health** (§8) — detects regressions from prompt changes.
6. **Per-report-type templates** (§11).

**Gate 2B:** Visual review of all report types. Quality scoring doesn't false-positive on normal responses.

### Phase 2C — Autonomy (estimated: 3-4 sessions, needs rate-limit plan)
7. **Parallelization (fan-out research)** (§4) — gated behind `PARALLEL_AGENTS_ENABLED`.
8. **Auto research loop** (§6) — gated behind a UI button, never auto-triggered.

**Gate 2C:** Rate-limit telemetry shows no throttling. Cost telemetry stays under the weekly budget. (Browser automation is explicitly **not** in this phase — see Phase 2E.)

### Phase 2D — Polish (estimated: 1 session)
9. **Boot assembling animation** (§10). Lowest risk; cosmetic.

### Phase 2E — Deferred (needs consent/audit framework first)
10. **Consent/audit framework** — `ConsentDialog` (§7.2), `_pre_tool_check` hook on the agent, append-only `.claude/audit.log`. Shared foundation for everything below.
11. **Computer automation** (§7.2) — requires the consent framework.
12. **Browser automation (Tier 2)** — gated on the same consent framework; lift the design from §7.6 once (10) lands.
13. **Voice integration** — its own sprint, per [voice guide](./JARVIS_VOICE_INTEGRATION_GUIDE.md).

Each phase ends with: run verification matrix, update `JARVIS_ISSUES_REPORT.md`, push to a feature branch, PR with diff + screenshots.

---

## 15. Verification matrix

| Feature | Lint / type | Unit test | Integration | Manual |
|--------|-----------|-----------|-------------|--------|
| **R-2 regression** (blocker) | ✓ | `test_truncated_tool_result_is_valid_json` (§13.0) | Run an agent loop that triggers truncation; no parser error surfaces | — |
| **R-3 regression** (blocker) | ✓ | `test_sync_tool_hits_timeout` (§13.0) | Dispatcher returns structured error within 60 s | — |
| **R-5 regression** (blocker) | ✓ | `test_concurrent_sessions_have_independent_mode` (§13.0) | Two ws clients with different modes in the same process | Two Electron windows, flip mode in one, verify other unaffected |
| Prompts | eslint passes | `tests/test_prompts.py` — budget check, missing files, malformed JSON | Backend boots with broken `.claude/` | Ask 3 queries, verify failure log doesn't grow for good answers |
| Agent Harness | ✓ | `tests/test_agent.py` (6 cases in §3.5) | No change in WS event sequence | Run one typical query end-to-end, diff logs |
| Orchestrator | ✓ | variant-generation prompt yields ≥2 distinct queries | Fan-out with mocked sub-agents | Real fan-out on a real research query |
| Workspace | ✓ | Path containment test | `set_project_path` swap mid-session reads/writes the new `.claude/` | Two projects open in two windows don't cross-pollute |
| **Workspace (concurrent)** | ✓ | — | Two ws sessions with different `project_path` each call `read_codebase` + report write simultaneously — disjoint file reads, disjoint temp paths | Two Electron windows pointing at different projects, kick off simultaneous queries; inspect `.claude/` and `reports/` trees |
| Auto research | ✓ | Loop halts at cost cap | Loop halts at iteration cap | Iteration counter updates in UI |
| Browser automation (when unblocked) | ✓ | Allowlist regex tests | Every navigation/screenshot triggers `ConsentDialog`; audit entry appended to `.claude/audit.log` | Headless Playwright on 3 allowed URLs; deny prompt stops the tool mid-flight |
| Quality scoring | ✓ | Regression corpus (good/bad pairs) | Retry fires on <0.5 | Manual: ask a terrible question, see the retry |
| Provider health | ✓ | Lock correctness under asyncio.gather | Provider switch after simulated failures | Force one provider to 429, chain drops it |
| Security — redaction | ✓ | 30+ positive + 30+ negative regex cases | Logs never contain a key | Paste a fake key, see `[REDACTED]` |
| Boot animation | ✓ | — | `prefers-reduced-motion` works | Manual: cold start, reduced motion, Escape return |
| Report templates | ✓ | `tests/test_report_generator.py` × 6 types | AI picks the right type for diagnosis query | Visual inspection, print preview |

---

## 16. Open questions for the user

1. **Cost ceiling for auto-research.** Proposed: $0.25 per loop, $5 per day. Acceptable?
2. **Browser automation allowlist.** Proposed defaults: `github.com, stackoverflow.com, docs.python.org, npmjs.com`. Add anything?
3. **Computer automation.** Ship it in Phase 2 with the consent dialog, or defer to Phase 3 entirely?
4. **Report templates — audience.** Should audit reports assume the reader is a developer (terse, file:line) or a stakeholder (explain severity in English)? Two different flavors?
5. **Boot animation — once or every launch?** Proposed: once per cold start (not on Escape return). Confirm.
6. **Quality scorer retry behaviour.** Retry on score < 0.5 — is that threshold right? Too aggressive, users will notice the double-response latency.
7. **`.claude/` in PROJECT_PATH.** Auto-create on first query, or require a setting? Proposed: require a setting (don't pollute unknown repos).
8. **R-5 strategy.** Per-connection dict on the ws handler (simpler) vs. a `Session` class carried through the agent (cleaner)? Proposed: dict for Phase 2A.0, promote to class if §4/§6 orchestrator work needs richer state.
9. **Browser automation unblock criteria.** Ship with the same `ConsentDialog` as computer automation, or a lighter "read-only confirmation" prompt for GETs? Proposed: one dialog shape, per-action, to keep the audit log coherent.

---

## 17. Review history

- **2026-04-20** — Draft v1 complete.
- **2026-04-20** — Codex adversarial review run (`/codex:adversarial-review`). Verdict: `needs-attention`. Findings F-1 (R-2/R-3/R-5 promoted to Phase 2A.0 blockers), F-2 (§5 re-spec'd to per-session state), F-3 (browser automation deferred to Phase 2E behind consent framework) applied in-place. Draft now v2.

---

*End of plan. v2 reflects the adversarial review; ready for implementation gated on §14.*
