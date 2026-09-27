## Code Search and Analysis Tools

### Structural search

Use `ast-grep` rather than regex grep for code *shapes* — it matches AST patterns and handles multi-line constructs, indentation variance, and nesting that regex misses.

Reach for it when searching for constructor or call patterns, finding call sites with a particular argument shape, or locating every construction that passes a field you are migrating. Plain grep is enough for keyword searches, imports, and constant definitions.

### Knowledge graph

Where a code knowledge graph is available (e.g. the `code-review-graph` MCP server), query it before scanning files by hand — semantic node search, relationship traversal (`callers_of`, `callees_of`, `imports_of`, `tests_for`, `inheritors_of`), and impact radius before a change. It avoids full-codebase scans. Fall back to grep/glob/read when the graph doesn't cover what you need.

### Workflow skills and agents

Use these where they belong in the workflow, not as an afterthought. Adapt to what is actually installed.

| Skill / Agent | Trigger | What it is for |
|---|---|---|
| `brainstorming` | Before any creative work | Mandatory first phase — questions and a design before code |
| `writing-plans` | A multi-step task, once the design is approved | Turns a spec into independently committable units |
| `test-driven-development` | Implementing anything | The failing test comes first |
| `systematic-debugging` | A test failure or unexpected behaviour | Before proposing a fix, not after it fails |
| `verification-before-completion` | About to claim something works | Run the command and read the output first |
| `migration-planner` | Brainstorming a type migration | Injects migration strategy when replacing primitives with domain types |
| `audit-asserts` | Periodic test sweeps | Finds tests whose assertions don't match their names |
| `documentation` | Docs have drifted | Updates README, ADRs, living documentation |
| `/simplify` | After an implementation lands | Reuse, quality, efficiency. Quality only — it does not hunt bugs |
| `/code-review` | Before merging, or on request | Correctness review at a chosen effort level |
| `claude-mem:smart-explore` | Unfamiliar structure | Tree-sitter outlines instead of whole files |
| `claude-mem:mem-search` | Resuming earlier work | "How did we do this last time?" |
| `code-review:*` agents | After a substantial feature | `security-auditor`, `contracts-reviewer`, `bug-hunter`, `test-coverage-reviewer` |
