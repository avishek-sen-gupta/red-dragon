## Code Review

### Self-review checklist

Before every commit, scan the diff for these anti-patterns:

- **Workaround guards** — `is not None`, bare `try/except`, or conditional logic added just to make tests pass without understanding the root cause.
- **Weak assertions** — `assert x is not None` or `assert "name" in result` when a concrete value assertion (`assert result == 30`) is possible.
- **Mutation in loops** — mutable accumulators inside `for` loops instead of comprehensions/map/filter/reduce.
- **Stale documentation** — README, linker-design.md, frontend design docs, IR reference, VM design docs, frontend lowering gaps, ADRs, etc. that no longer match the implementation.
- **Missing tests** — new code paths without corresponding unit AND integration tests.
- **Leaked abstractions** — internal labels, register names, or IR details exposed in public APIs or test assertions.
- **Dead code** — unused imports, unreachable branches, assigned-but-never-read variables.

### Requested reviews

When asked to review code (or when running `/review`), apply the Programming Patterns and Design Principles sections as the review rubric. Prioritise findings by severity:

1. **CRITICAL** — security vulnerabilities, data loss risks
2. **HIGH** — likely bugs, significant performance issues
3. **MEDIUM** — code quality, moderate risk
4. **LOW** — minor improvements

Report findings only. Do not fix code during review — present findings and let the user decide what to act on. File issues for anything that needs follow-up work.
