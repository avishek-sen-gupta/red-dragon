## Workflow skills and agents

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
