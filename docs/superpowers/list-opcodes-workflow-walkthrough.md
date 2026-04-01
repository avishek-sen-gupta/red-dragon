# Superpowers Workflow: `list_opcodes` — Annotated Mechanics

**Purpose:** Show a technical audience exactly what fires, when, and what gets injected at every
step of a feature's lifecycle. Explicit markers appear at every tool/skill/hook activation point,
including turns where no skill was triggered and tool calls that inject no additional context.

**Feature implemented:** `list_opcodes` MCP tool — returns all 33 IR opcodes with categories,
fields, and semantic notes, derived via runtime introspection of `_TO_TYPED`.

---

## Notation

```
[HOOK fired: <name>                → injected: <what> | none]
[SKILL loaded: <name>              → injected: <what>]
[SKILL check: <outcome>            → no injection]
[TOOL called: <name>               → context injected: none | <what>]
[AGENT dispatched: <role>          model=<model> → context package: <what>]
```

`SKILL check: not triggered` appears on every turn where the agent evaluated whether a skill
applied and concluded it did not. The absence of this marker would be dishonest — the check
always happens (it was made mandatory by the using-superpowers skill at T0).

---

## T0 — Session Initialization (before any user message)

```
[HOOK fired: SessionStart:clear
 → injected ~2,000 tokens:
   - Implementation Guidelines (multi-language verification rules, scoping rules, LLM API rules)
   - Interaction Style (brainstorm collaboratively, stop on wrong assumptions, interruption handling)
   - Python Introspection policy (write to /tmp/*.py, clean up after, no python -c multiline)
   - Talisman policy (stop and prompt before updating .talismanrc, never overwrite entries)
   - Project Context (Python 3.13+, Poetry, pytest-xdist, Beads, ADRs, .importlinter)
   - Task Tracking (Beads workflow: create → claim → close → backup → commit; exhaustive detail)
   - External Dependencies (JDK 17+, Neo4j optional, Universal CTags, mojo-lsp, smojol paths)
   - Code Search Tools (ast-grep mandate for structural search; code-review-graph MCP tools first)
   - Workflow Phases (Brainstorm → Plan → Test → Implement → Self-review → Verify → Commit)
   - Verification Gate description (pre-commit hook auto-runs: Talisman, Black, import-linter,
     pytest, bd backup — "just commit, hook enforces all gates")]

[HOOK fired: SessionStart (code-review-graph MCP server)
 → injected ~200 tokens:
   - Notification that knowledge graph tools are available
   - Tool names: semantic_search_nodes_tool, query_graph_tool, get_impact_radius_tool,
     get_review_context_tool
   - Instruction: prefer these tools before manual file scanning]

[HOOK fired: SessionStart (superpowers plugin: auto-loads using-superpowers skill)
 → injected ~1,500 tokens:
   - "If there is even a 1% chance a skill might apply, you MUST invoke it"
   - Skill invocation flowchart: user message → check for skills → invoke → follow
   - Red Flags table: 11 rationalizations that mean STOP and check for skills
   - Skill priority order: process skills (brainstorming, debugging) before implementation skills
   - Rigid vs Flexible skill types (TDD = rigid: follow exactly; patterns = flexible: adapt)
   - "Instructions say WHAT, not HOW — 'Add X' doesn't mean skip workflows"]

[MEMORY auto-loaded: MEMORY.md
 → injected ~800 tokens:
   - Recent sessions (type annotation migration status, test count 13,235)
   - Module structure (interpreter/refs/, interpreter/vm/, interpreter/types/, etc.)
   - Type System gaps, roadmap, TypeExpr ADT location
   - Critical Workflow Reminders (always write integration tests, black before commit, etc.)
   - Tooling notes (use python -m black not poetry run black, use python -m pytest)
   - Design Feedback pointers (no workaround guards, no renaming tests, etc.)
   - MCP Server summary (FastMCP, stdio, 8 tools + 3 resources)]

[HOOK fired: currentDate injection
 → injected ~10 tokens: "Today's date is 2026-04-01"]
```

> **What this achieves:** ~4,510 tokens of ambient context are loaded before the user types a
> single character. The agent already knows: the project's tooling, verification protocol,
> workflow phases, and the obligation to check for skills at every step.

---

## T1 — User: "braintorm a dummy feature for me to demonstrate superpowers"

```
[HOOK fired: UserPromptSubmit
 → injected ~3,000 tokens:
   - Design Principles (use existing infrastructure, simplest mechanism first, no workaround
     guards, no spec-divergent additions, no defensive None checks)
   - Programming Patterns (functional style, frozen dataclasses, push wrapping to origin,
     one class per file, enums for fixed string sets)
   - Testing Patterns (TDD, concrete assertions not is-not-None, no mocking, xfail with
     issue IDs, both unit and integration tests, cover all reachable paths)
   - Refactoring Principles (grep for bare-string comparisons before domain type migration)
   - Workflow Skills Table (skill name → trigger condition → when to invoke)]
```

Agent applied 1% rule (from T0 using-superpowers): "brainstorm" is an explicit skill trigger.

```
[SKILL loaded: superpowers:brainstorming (via Skill tool)
 → BEFORE skill loads: PreToolUse:Skill hook fired
   → injected ~1,000 tokens of Testing Patterns:
     - TDD: write failing tests first
     - Review assertions for specificity (concrete values, not is not None)
     - xfail with issue ID references
     - Both unit and integration tests required
 → skill content loaded (~2,500 tokens):
   - HARD-GATE: do NOT write any code before design is approved
   - Mandatory 9-step checklist: explore → visual? → clarify → approaches → design →
     spec → self-review → user review → writing-plans
   - Process flowchart
   - "One question at a time" rule — ask only ONE question per message, wait for answer
   - Visual Companion offer protocol (must be its own message, user consent required)
   - Design for isolation and clarity (units with clear boundaries)
   - Working in existing codebases (explore first, follow patterns)
   - After Design: spec to docs/superpowers/specs/, commit, self-review, user review gate,
     then invoke ONLY writing-plans — no implementation skill]
```

Brainstorm checklist step 1: explore project context.

```
[TOOL called: Bash ("ls mcp_server/")                        → context injected: none]
[TOOL called: Bash ("grep -n '^@mcp|^def ' mcp_server/tools.py")
                                                             → context injected: none]
[TOOL called: Bash ("grep -n '^@mcp' mcp_server/server.py")  → context injected: none]
```

Agent assessed: no visual companion needed (choosing a feature area is a text question).

**Q1 (brainstorming protocol: one question per message):** "Which area — CLI enhancement (a),
MCP tool (b), or language frontend feature (c)?"

---

## T2 — User: "c"

```
[HOOK fired: UserPromptSubmit
 → injected ~3,000 tokens: same invariants as T1]

[SKILL check: not triggered
 → reason: brainstorming is already active (loaded at T1); no new phase transition;
   1% rule evaluated — no other skill applicable to a single-character answer mid-brainstorm]
```

No tool calls. Agent issued Q2 per one-question-at-a-time rule.

**Q2:** "Within MCP tools, some candidates: (a) list_all_types, (b) trace_execution_path,
(c) list_opcodes with opcode catalogue. Which direction?"

---

## T3 — User: "sure" (list_opcodes)

```
[HOOK fired: UserPromptSubmit
 → injected ~3,000 tokens: same invariants]

[SKILL check: not triggered
 → reason: still mid-brainstorm Q&A; no phase transition; 1% rule returned no applicable skill]
```

No tool calls. Agent issued Q3.

**Q3:** "How much detail per opcode? (a) minimal (name + category), (b) moderate (name +
fields + one-line description), (c) rich — full semantic notes per opcode, 3-5 sentences each?"

---

## T4 — User: "C, but put in a lot of detail"

```
[HOOK fired: UserPromptSubmit
 → injected ~3,000 tokens: same invariants]

[SKILL check: not triggered
 → reason: still mid-brainstorm; approach chosen but no phase transition yet;
   1% rule evaluated — brainstorming still active]
```

Agent now had enough to ground a design. Explored codebase (brainstorm checklist step 1 cont.):

```
[TOOL called: Read ("mcp_server/server.py" lines 38-88)      → context injected: none]
[TOOL called: Bash ("grep -n 'class Opcode|^    [A-Z]' interpreter/ir.py")
                                                             → context injected: none]
[TOOL called: Read ("interpreter/instructions.py" lines 196-315)
                                                             → context injected: none]
[TOOL called: Bash ("python3 -c 'from interpreter.instructions import _TO_TYPED; print(len(_TO_TYPED))'")
                                                             → context injected: none]
[TOOL called: Bash ("grep -n '\"\"\"' interpreter/instructions.py | head -40")
                                                             → context injected: none]
[TOOL called: Bash ("python3 -c 'import dataclasses; from interpreter.instructions import ...'")
                                                             → context injected: none]
```

Agent presented full design (brainstorm checklist step 5): response shape (JSON with `opcodes`
array), 8 categories, 33 opcode entries, per-opcode notes strategy, data source table
(introspection for fields/description vs hardcoded dicts for categories/notes).

---

## T5 — User: "yes" (design approved)

```
[HOOK fired: UserPromptSubmit
 → injected ~3,000 tokens: same invariants]

[SKILL check: not triggered
 → reason: brainstorm checklist step 6 is "write design doc" — a concrete action, not a
   phase that requires a new skill; brainstorming skill (already loaded at T1) covers this step]
```

Brainstorm checklist step 6: write design doc.

```
[TOOL called: Write ("docs/superpowers/specs/2026-04-01-list-opcodes-design.md")
                                                             → context injected: none]
[TOOL called: Bash ("git add docs/superpowers/specs/2026-04-01-list-opcodes-design.md")
                                                             → context injected: none]
[TOOL called: Bash ("git commit -m 'docs: list_opcodes design spec'")
                                                             → context injected: none]
```

Pre-commit hook ran automatically:

```
  Talisman      ✅
  Black         ✅
  import-linter ✅
  pytest        ✅ (13,235 tests)
  bd backup     ✅
```

Brainstorm checklist step 7: spec self-review (inline, no subagent — skill says "fix inline,
no need to re-review"). Agent scanned for placeholders, contradictions, ambiguity. Found none.

Brainstorm checklist step 8: user review gate. Agent asked: "Spec written and committed to
`docs/superpowers/specs/2026-04-01-list-opcodes-design.md`. Please review before we proceed."

---

## T6 — User: "looks good" (spec approved)

```
[HOOK fired: UserPromptSubmit
 → injected ~3,000 tokens: same invariants]
```

Brainstorm checklist step 9: "invoke writing-plans — this is the ONLY next step."
Agent applied 1% rule: writing-plans skill applies.

```
[SKILL loaded: superpowers:writing-plans (via Skill tool)
 → BEFORE skill loads: PreToolUse:Skill hook fired
   → injected ~1,000 tokens of Testing Patterns (same as T1 pre-skill injection)
 → skill content loaded (~1,500 tokens):
   - "Announce at start: I'm using the writing-plans skill"
   - File Structure section (decomposition decisions locked here — each file one responsibility)
   - Bite-Sized Task Granularity: each step = one action, 2-5 minutes
   - Mandatory plan header format (Goal, Architecture, Tech Stack)
   - Task structure template (Files: Create/Modify/Test, steps with actual code not descriptions)
   - No Placeholders rule: TBD/TODO/"add validation"/"similar to Task N" = plan failure
   - Self-Review checklist: spec coverage scan, placeholder scan, type consistency check
   - Execution Handoff: offer subagent-driven (recommended) vs inline execution]
```

Agent explored to write a grounded plan:

```
[TOOL called: Bash ("ls tests/unit/; find tests/ -name '*mcp*'")
                                                             → context injected: none]
[TOOL called: Bash ("grep -n '^def handle_' mcp_server/tools.py")
                                                             → context injected: none]
[TOOL called: Read ("tests/unit/test_mcp_tools.py" lines 1-40)
                                                             → context injected: none]
[TOOL called: Read ("mcp_server/tools.py" lines 1-30)        → context injected: none]
[TOOL called: Read ("mcp_server/server.py" lines 1-35)       → context injected: none]
[TOOL called: Write ("docs/superpowers/plans/2026-04-01-list-opcodes.md")
                                                             → context injected: none]
```

writing-plans self-review (from skill: "look at spec with fresh eyes, fix inline"):
agent re-read spec, confirmed all 7 spec requirements map to plan tasks, no TBD placeholders,
type names consistent throughout.

```
[TOOL called: Bash ("git add docs/superpowers/plans/2026-04-01-list-opcodes.md")
                                                             → context injected: none]
[TOOL called: Bash ("git commit -m 'docs: list_opcodes implementation plan'")
                                                             → context injected: none]
```

Pre-commit hook ran: ✅ all gates, 13,235 tests.

Execution Handoff (from skill): "Plan complete. Two options: (1) subagent-driven, (2) inline
execution. Which approach?"

---

## T7 — User: "1" (subagent-driven execution chosen)

```
[HOOK fired: UserPromptSubmit
 → injected ~3,000 tokens: same invariants]
```

Agent applied 1% rule: executing a plan using subagents → subagent-driven-development skill.

```
[SKILL loaded: superpowers:subagent-driven-development (via Skill tool)
 → BEFORE skill loads: PreToolUse:Skill hook fired
   → injected ~1,000 tokens of Testing Patterns
 → skill content loaded (~2,000 tokens):
   - Core principle: fresh subagent per task + two-stage review
   - Two-stage order is mandatory: spec compliance FIRST, code quality SECOND — never reverse
   - When-to-use flowchart (same session, no context switch → use this skill)
   - Per-task loop: implementer → spec reviewer → code quality reviewer
   - Model selection table:
       mechanical tasks (1-2 files, clear spec) → haiku
       integration tasks (multi-file, pattern matching) → sonnet
       architecture / design / review → opus
   - Handling implementer statuses: DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED
   - Red Flags: never skip reviews, never start code quality before spec ✅,
     never pass session history to subagents, never dispatch implementers in parallel
   - Prompt template references: implementer-prompt.md, spec-reviewer-prompt.md,
     code-quality-reviewer-prompt.md]
```

Controller extracted all tasks from plan. Created todo list.

```
[TOOL called: TaskCreate ("Task 1: implement handle_list_opcodes + tests")
                                                             → context injected: none]
[TOOL called: TaskCreate ("Task 2: register list_opcodes in server.py")
                                                             → context injected: none]
[TOOL called: TaskUpdate (Task 1 → in_progress)              → context injected: none]
[TOOL called: Read (implementer-prompt.md template)          → context injected: none]
```

---

## T8 — Task 1: Implementer Dispatch

Controller crafted a self-contained context package. Nothing from the session was passed through.

```
[AGENT dispatched: implementer  model=sonnet
 → context package crafted by controller (~3,000 tokens):
   - Full Task 1 text verbatim from plan (Steps 1-6):
       Step 1: file Beads issue + claim
       Step 2: write failing tests (19 test cases, exact assertions shown in plan)
       Step 3: run tests → verify FAIL
       Step 4: implement handle_list_opcodes() + _OPCODE_CATEGORIES + _OPCODE_NOTES + _type_str()
       Step 5: run tests → verify PASS
       Step 6: bd backup + commit
   - Codebase context: working dir, poetry run prefix, bd CLI syntax
   - Architecture: _TO_TYPED explanation, get_type_hints() + dataclasses.fields() pattern,
     existing handler structure in tools.py
   - Out-of-scope: do NOT touch server.py (Task 2)
   - Report format: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
 → NO session history
 → NO brainstorm transcript
 → NO spec document
 → NO other task context]
```

> **Key design:** The implementer has never seen T0–T7. The controller does not pass the session.
> It constructs exactly what this agent needs — no more. Context pollution is structurally
> impossible, not just disciplinary.

Implementer worked autonomously (subagent's own tool calls — each injects no additional context):

```
  [TOOL called: Bash ("bd create 'list_opcodes handler' --description='...'")
                                                               → context injected: none]
  [TOOL called: Bash ("bd update red-dragon-v0na --claim")     → context injected: none]
  [TOOL called: Read ("mcp_server/tools.py")                   → context injected: none]
  [TOOL called: Read ("interpreter/instructions.py")           → context injected: none]
  [TOOL called: Read ("interpreter/ir.py" — Opcode enum)       → context injected: none]
  [TOOL called: Read ("tests/unit/test_mcp_tools.py")          → context injected: none]
  [TOOL called: Edit ("tests/unit/test_mcp_tools.py"
     — add TestListOpcodes class, 17 test methods)             → context injected: none]
  [TOOL called: Bash ("poetry run python -m pytest
     tests/unit/test_mcp_tools.py::TestListOpcodes -v")        → context injected: none]
  (result: 17 FAILED — handle_list_opcodes not found ✅ expected red)
  [TOOL called: Edit ("mcp_server/tools.py"
     — add _OPCODE_CATEGORIES dict, _OPCODE_NOTES dict,
       _type_str() helper, handle_list_opcodes() handler)      → context injected: none]
  [TOOL called: Bash ("poetry run python -m pytest
     tests/unit/test_mcp_tools.py::TestListOpcodes -v")        → context injected: none]
  (result: 17 passed ✅ green)
  [TOOL called: Bash ("bd backup")                             → context injected: none]
  [TOOL called: Bash ("git add mcp_server/tools.py
                            tests/unit/test_mcp_tools.py
                       && git commit -m '...'")                → context injected: none]
  (pre-commit hook: ✅ Talisman, Black auto-fixed + re-staged, import-linter,
                    pytest 13,254 passed, bd backup)
```

Implementer reported: **DONE**

---

## T9 — Task 1: Spec Compliance Review

Skill rule (loaded at T7): "spec compliance BEFORE code quality — never reverse."

```
[AGENT dispatched: spec-reviewer  model=haiku
 → context package crafted by controller (~600 tokens):
   - Requirements as numbered checklist (extracted from spec, not from plan):
       1. All 33 opcodes present in response
       2. Each entry has name, category, description, fields, notes
       3. No source_location in any fields list
       4. Opcodes sorted alphabetically
       5. BINOP has fields: operator, left, right, result_reg
       6. LABEL has no opcode-specific fields beyond base fields
       7. CALL_FUNCTION category is "calls"
   - "CRITICAL: Do Not Trust the Report — run verification commands yourself"
   - Verification snippets: python -c for each of the 7 requirements
   - Report format: ✅ COMPLIANT or ❌ NOT COMPLIANT with file:line references
 → NO implementation details
 → NO session history
 → NO quality criteria]
```

Spec reviewer ran all verification commands independently:

```
  [TOOL called: Bash ("python -c 'from mcp_server.tools import handle_list_opcodes;
     r = handle_list_opcodes(); print(len(r[\"opcodes\"]))'")  → context injected: none]
  (result: 33 ✅)
  [TOOL called: Bash (python -c to check BINOP fields present) → context injected: none]
  [TOOL called: Bash (python -c to verify alphabetical sort)   → context injected: none]
  [TOOL called: Bash (python -c to verify no source_location)  → context injected: none]
  [TOOL called: Bash (python -c to check CALL_FUNCTION category)
                                                               → context injected: none]
```

Result: **✅ COMPLIANT — all 7 requirements verified independently.**

---

## T10 — Task 1: Code Quality Review

```
[AGENT dispatched: code-quality-reviewer  subagent_type=superpowers:code-reviewer
 → context package crafted by controller (~500 tokens):
   - What was implemented: handle_list_opcodes, _OPCODE_CATEGORIES, _OPCODE_NOTES, _type_str()
   - BASE_SHA and HEAD_SHA for git diff
   - Focus areas: import hygiene, type string formatting, note completeness, assertion quality
   - Working directory path
 → subagent_type=superpowers:code-reviewer loads its OWN skill protocol on initialization
   (the controller does not inject it — the subagent type carries it as its own SessionStart)]
```

Code reviewer ran `git diff BASE_SHA..HEAD_SHA`, read the changed files, found **3 Important issues:**

1. `from interpreter.ir import Opcode` — imported but unused in the handler body
2. Two separate `from interpreter.instructions import` lines — should be one merged import
3. `_type_str()` returns `<class 'interpreter.register.Register'>` for plain types — unclean output

---

## T11 — Task 1: Fix Dispatch (round 1)

```
[AGENT dispatched: fix-implementer  model=haiku
 → context package crafted by controller (~800 tokens):
   - Issue 1 + exact fix: remove `from interpreter.ir import Opcode`
   - Issue 2 + exact fix: merge the two interpreter.instructions import lines
   - Issue 3 + exact fix: in _type_str(), add `if hasattr(t, '__name__'): return t.__name__`
     before the str(t) fallback
   - Verification snippet: python -c showing expected clean type name output
   - Report format
 → NO session history
 → NO review conversation
 → NO spec text
 → NO prior implementer context]
```

```
  [TOOL called: Read ("mcp_server/tools.py")                   → context injected: none]
  [TOOL called: Edit ("mcp_server/tools.py"
     — remove Opcode import, merge imports, add __name__ branch to _type_str())
                                                               → context injected: none]
  [TOOL called: Bash ("python -c '<verification snippet>'")    → context injected: none]
  [TOOL called: Bash ("poetry run python -m pytest
     tests/unit/test_mcp_tools.py -v")                        → context injected: none]
  (result: 19 passed — implementer also added 2 tests for _type_str plain-type edge cases)
  [TOOL called: Bash ("git add mcp_server/tools.py tests/unit/test_mcp_tools.py
                       && git commit -m '...'")                → context injected: none]
```

---

## T12 — Task 1: Code Quality Re-Review (round 2)

```
[AGENT dispatched: code-quality-reviewer  subagent_type=superpowers:code-reviewer
 → context package crafted by controller (~300 tokens):
   - What was fixed (the 3 issues from round 1)
   - BASE_SHA and HEAD_SHA for the fix commit
   - Instruction: verify fixes landed, check for any new issues introduced
 → fresh context — no prior review conversation passed
 → subagent loads its own skill protocol]
```

Reviewer found **1 residual**: generic alias types still show module paths —
`tuple[interpreter.ir.CodeLabel, ...]` instead of `tuple[CodeLabel, ...]`.

---

## T13 — Task 1: Fix Dispatch (round 2)

```
[AGENT dispatched: fix-implementer  model=haiku
 → context package crafted by controller (~400 tokens):
   - The exact problem: _type_str() fallback branch calls str(t) without stripping module paths
   - The exact fix: re.sub(r"\b\w+\.(\w+\b)", r"\1", str(t)) in the fallback
   - Expected output before: "tuple[interpreter.ir.CodeLabel, ...]"
   - Expected output after:  "tuple[CodeLabel, ...]"
   - Verification snippet: python -c showing clean output for all 33 opcodes
 → NO session history
 → NO prior fix context]
```

```
  [TOOL called: Read ("mcp_server/tools.py")                   → context injected: none]
  [TOOL called: Edit ("mcp_server/tools.py"
     — add re.sub to _type_str() fallback branch)              → context injected: none]
  [TOOL called: Bash ("python -c '<verification snippet>'")    → context injected: none]
  [TOOL called: Bash ("poetry run python -m pytest tests/ -q") → context injected: none]
  (result: 13,254 passed)
  [TOOL called: Bash ("git add mcp_server/tools.py && git commit -m '...'")
                                                               → context injected: none]
```

---

## T14 — Task 1: Code Quality Re-Review (round 3)

```
[AGENT dispatched: code-quality-reviewer  subagent_type=superpowers:code-reviewer
 → context package crafted by controller (~250 tokens):
   - The residual issue from round 2 and what was done to fix it
   - BASE_SHA and HEAD_SHA for the round-2 fix commit
   - Instruction: confirm residual resolved, check for any new issues
 → fresh context — no rounds 1 or 2 passed]
```

Result: **✅ Approved.** No new issues. `_type_str` output is clean for all type variants.

```
[TOOL called: TaskUpdate (Task 1 → completed)                  → context injected: none]
[TOOL called: TaskUpdate (Task 2 → in_progress)                → context injected: none]
```

---

## T15 — Task 2: Implementer Dispatch

```
[AGENT dispatched: implementer  model=haiku
 → context package crafted by controller (~600 tokens):
   - Full Task 2 text verbatim from plan (Steps 1-5):
       Step 1: add `handle_list_opcodes` to the import block in server.py
       Step 2: add @mcp.tool() decorated list_opcodes() function with docstring
       Step 3: poetry run pyright mcp_server/server.py — confirm zero new errors
       Step 4: bd close red-dragon-v0na with closure reason
       Step 5: bd backup + commit
   - Explicit note: handle_list_opcodes() is already implemented (Task 1 done) — pure wiring
   - Beads issue to close: red-dragon-v0na
 → NO Task 1 context
 → NO session history
 → NO spec text]
```

```
  [TOOL called: Read ("mcp_server/server.py")                  → context injected: none]
  [TOOL called: Edit ("mcp_server/server.py"
     — add handle_list_opcodes to imports,
       add list_opcodes() @mcp.tool() registration with docstring)
                                                               → context injected: none]
  [TOOL called: Bash ("poetry run pyright mcp_server/server.py")
                                                               → context injected: none]
  (result: 0 new errors)
  [TOOL called: Bash ("bd close red-dragon-v0na --reason 'handle_list_opcodes implemented...'")
                                                               → context injected: none]
  [TOOL called: Bash ("bd backup")                             → context injected: none]
  [TOOL called: Bash ("git add mcp_server/server.py && git commit -m '...'")
                                                               → context injected: none]
  (pre-commit hook: ✅ all gates, 13,254 tests, committed e6f2e055)
```

Implementer reported: **DONE**

---

## T16 — Task 2: Spec Compliance Review

```
[AGENT dispatched: spec-reviewer  model=haiku
 → context package crafted by controller (~400 tokens):
   - Requirements checklist for Task 2 (extracted from spec):
       1. list_opcodes registered as @mcp.tool() in server.py
       2. Function has a docstring describing its purpose
       3. Return type is dict[str, Any]
       4. handle_list_opcodes imported from mcp_server.tools
   - "Do not trust the report — verify independently"
   - Verification commands: grep + python -c import check
 → NO implementation details
 → NO session history]
```

```
  [TOOL called: Bash ("grep -n 'list_opcodes' mcp_server/server.py")
                                                               → context injected: none]
  [TOOL called: Bash ("python -c 'from mcp_server.server import ...'")
                                                               → context injected: none]
```

Result: **✅ COMPLIANT — all 4 requirements verified.**

---

## T17 — Task 2: Code Quality Review

```
[AGENT dispatched: code-quality-reviewer  subagent_type=superpowers:code-reviewer
 → context package crafted by controller (~300 tokens):
   - What was implemented: @mcp.tool() registration in server.py, import added
   - BASE_SHA and HEAD_SHA
   - Note: this is purely mechanical wiring — no logic added
 → subagent loads its own skill protocol]
```

Result: **✅ Approved.** Pure wiring change. No logic, no edge cases, no issues.

```
[TOOL called: TaskUpdate (Task 2 → completed)                  → context injected: none]
```

Feature shipped. All tasks complete.

---

## Context Layer Summary

```
Layer                           Fires When                    Approx size   Scope
──────────────────────────────────────────────────────────────────────────────────────────────
SessionStart:clear hook         Once at session start          ~2,000t       always present
code-review-graph MCP hook      Once at session start          ~200t         always present
using-superpowers skill         Once at session start          ~1,500t       always present
MEMORY.md auto-load             Every response                 ~800t         always present
currentDate injection           Every response                 ~10t          always present
──────────────────────────────────────────────────────────────────────────────────────────────
UserPromptSubmit hook           Every user message             ~3,000t       per turn
                                (fires even for "c", "sure", "yes", "1")
──────────────────────────────────────────────────────────────────────────────────────────────
PreToolUse:Skill hook           Before every Skill tool call   ~1,000t       during skill phase
Active skill content            While skill is running         ~1,500–3,000t during skill phase
──────────────────────────────────────────────────────────────────────────────────────────────
Per-subagent context package    Each Agent tool dispatch       ~300–3,000t   in subagent only
                                                                             never in controller
──────────────────────────────────────────────────────────────────────────────────────────────
Approximate peak per controller turn (skill active + subagent dispatch): ~15,000t
Approximate floor per controller turn (plain mid-brainstorm Q&A answer):  ~7,510t
```

Note the floor: even the trivial turn T2 ("c") injected ~7,510 tokens (SessionStart layers +
MEMORY + UserPromptSubmit). There is no "cheap" turn.

---

## Subagent Dispatch Summary

| # | Role | Model | Context size | Outcome |
|---|------|-------|--------------|---------|
| 1 | Implementer (Task 1) | sonnet | ~3,000t | DONE — 17 tests → green |
| 2 | Spec reviewer (Task 1) | haiku | ~600t | ✅ All 7 verified |
| 3 | Code quality reviewer (Task 1) | code-reviewer | ~500t | 3 Important issues |
| 4 | Fix implementer (round 1) | haiku | ~800t | Fixed, 19 tests pass |
| 5 | Code quality re-reviewer (round 2) | code-reviewer | ~300t | 1 residual |
| 6 | Fix implementer (round 2) | haiku | ~400t | Fixed, 13,254 tests |
| 7 | Code quality re-reviewer (round 3) | code-reviewer | ~250t | ✅ Approved |
| 8 | Implementer (Task 2) | haiku | ~600t | DONE — registered |
| 9 | Spec reviewer (Task 2) | haiku | ~400t | ✅ All 4 verified |
| 10 | Code quality reviewer (Task 2) | code-reviewer | ~300t | ✅ Approved |

> Every subagent worked from a hand-crafted context package. None received session history.
> None received another subagent's conversation. Isolation is structural, not disciplinary.

---

## Key Mechanical Properties

### Hooks are not skills

Hooks (`SessionStart`, `UserPromptSubmit`, `PreToolUse:Skill`) are shell commands configured in
`.claude/settings.json`. They fire unconditionally on lifecycle events. Their output is prepended
to the message context before the agent sees it. The agent cannot suppress or opt out of them.

### Skills are opt-in — but the obligation to check is not

Skills are loaded via the `Skill` tool. The agent must invoke them. The obligation comes from
the `using-superpowers` skill injected at T0: "1% chance a skill applies = you MUST invoke it."
A skill is a markdown file; loading it injects its text as context.

When the agent decides a skill does not apply, that decision is shown explicitly as
`[SKILL check: not triggered]`. This makes the check visible even when it produces no injection.

### The double-injection pattern

When the agent calls `Skill: superpowers:writing-plans`, two things happen in order:

1. `PreToolUse:Skill` hook fires → injects Testing Patterns (~1,000 tokens)
2. The writing-plans skill content loads (~1,500 tokens)

The plan-writing protocol arrives pre-loaded with testing rules before it reads a single word of
the skill content. The hook is a mandatory primer; the skill is the protocol.

### Subagents receive no session history

The controller crafts a complete, self-contained prompt for each subagent. The implementer has
never seen the brainstorm. The spec reviewer has never seen the implementation. The code quality
reviewer sees only SHAs and focus areas. This prevents context pollution and forces the
controller to be explicit about what each agent needs — if the context package is incomplete,
the agent returns NEEDS_CONTEXT, not a guess.

### The pre-commit hook is the unconditional gate

Talisman, Black, import-linter, pytest, and bd backup run on every `git commit` via
`.claude/hooks/pre-commit`. No agent (controller or subagent) can merge broken code. The
SessionStart hook injected this policy at T0: "just commit — the hook enforces everything."

### Two-stage review order is enforced by the skill

The subagent-driven-development skill (loaded at T7) states: "Never start code quality review
before spec compliance is ✅." Spec compliance answers "did we build the right thing?" Code
quality answers "did we build it well?" Running code quality first wastes review cycles on a
feature that might be wrong. The order is a protocol rule, not a preference.

### The 3,000-token floor per turn

The UserPromptSubmit hook fires on every user message — including single-character answers like
"c" (T2) and "sure" (T3). There is no "cheap" turn. Combined with the session-persistent layers,
every controller turn carries at minimum ~7,510 tokens of injected context before the agent
processes the message content.
