## Code Search and Analysis Tools

### ast-grep (structural code search)

Use the `/ast-grep` skill for structural code searches instead of regex grep. ast-grep matches AST patterns and handles multi-line constructs, indentation variations, and nested expressions that regex misses.

**When to use ast-grep:**
- Searching for constructor/function call patterns (e.g., `FuncRef(name=$X)`, `DeclVar(name=$N, value_reg=$R)`)
- Finding all call sites of a specific function with certain argument shapes
- Migrating field types: finding all constructions that pass a specific field
- Any search where the pattern spans multiple lines or has variable whitespace

**When plain grep is sufficient:**
- Simple keyword/string searches (`SELF_PARAM_NAMES`, `def _handle_const`)
- Import statements
- Constant definitions

### code-review-graph (knowledge graph)

Use the code-review-graph MCP tools before scanning files manually for codebase understanding:

- `semantic_search_nodes_tool` — find classes, functions, or types by name or keyword
- `query_graph_tool` — explore relationships: `callers_of`, `callees_of`, `imports_of`, `children_of`, `tests_for`, `inheritors_of`, `file_summary`
- `get_impact_radius_tool` — understand blast radius before making changes
- `get_review_context_tool` — token-efficient review context for PRs

These save significant tokens by avoiding full codebase scans. Fall back to grep/glob/read only when the graph doesn't cover what you need.

### Workflow skills and agents

Use these installed skills and agents at the right points in the workflow:

| Skill / Agent | Trigger | When to use |
|---|---|---|
| `/tdd` | Starting a feature or bug fix | Enforces red-green-refactor discipline with structured test-first loop |
| `/audit-asserts` | Periodic test quality sweeps | Scans test files for assertion-vs-name mismatches (custom skill in `.claude/skills/audit-asserts/`) |
| `/simplify` | After completing implementation | Reviews changed code for reuse, quality, and efficiency opportunities |
| `migration-planner` skill | During brainstorming for type migrations | Auto-triggers when replacing primitives with domain types; injects migration strategies |
| `claude-mem:smart-explore` | Understanding code structure | Token-optimized tree-sitter AST exploration; use instead of reading full files when you only need function signatures or class outlines |
| `claude-mem:mem-search` | Continuing work from prior sessions | Searches persistent cross-session memory for "how did we do X last time?" |
| `debugger` agent | Test failures or unexpected behavior | Systematic debugging with persistent state; use proactively before proposing fixes |
| `code-review` agents | After completing major features | Specialized reviewers: `security-auditor`, `contracts-reviewer`, `bug-hunter`, `test-coverage-reviewer` — dispatch via the Agent tool |
