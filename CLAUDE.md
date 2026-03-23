# RedDragon — Agent Instructions

## Project Context

- **Language:** Python 3.13+ (main codebase), Markdown (docs)
- **Package manager:** Poetry (`poetry run` prefix for all commands)
- **Test framework:** pytest with pytest-xdist (parallel by default)
- **Formatter:** Black
- **Architectural contracts:** import-linter (`.importlinter`)
- **Pre-commit hooks:** Talisman (secret detection)
- **Issue tracker:** Beads (`bd`)
- **ADRs:** `docs/architectural-design-decisions.md`
- **Specs (immutable):** `docs/superpowers/specs/` and `docs/superpowers/plans/` — never modify these. Newer specs supersede older ones by convention.

## Task Tracking

Use `bd` (Beads) for ALL task tracking. Do NOT use markdown TODO lists.

1. File an issue before starting work: `bd create "title" --description="..." -t bug|feature|task -p 0-4`
2. Claim it: `bd update <id> --claim`
3. When done: `bd close <id> --reason "..."`
4. Before every commit: `bd backup`

## Workflow

### Phases (mandatory, in order)

Every non-trivial task goes through these phases. Do not skip. Do not start implementing before completing brainstorm.

1. **Brainstorm** — Read the relevant code. Check how the existing system handles similar cases. Identify at least two approaches and their trade-offs. Ask: "does the system already have infrastructure for this?" Consider whether an open-source project already solves the problem.
2. **Plan** — Choose an approach. For features spanning multiple modules, identify independently-committable units and their order. For Heavy tasks, write the design down before proceeding.
3. **Test first** — Write failing tests that define the expected behavior. No implementation code until at least one test exists.
4. **Implement** — Write the minimum code to make the tests pass.
5. **Self-review** — Before running the verification gate, review your own diff (`git diff`). Check against the Design Principles and Programming Patterns sections below. Look for: workaround guards, mutation in loops, missing test coverage, weak assertions, leaked abstractions, stale docs. If the diff is large (Heavy task), run the `/review` skill.
6. **Verify** — Run the full verification gate (see below). All checks must pass.
7. **Commit** — One logical unit per commit. `bd backup` before `git add`. Push to remote.

When asked to audit or show issues, only report findings — do not fix unless explicitly asked.

### Complexity classification

Classify before starting. This determines how much ceremony is needed.

- **Light** (< 50 lines, single file, no new abstractions) — brief brainstorm. Example: adding a node type to a dispatch table.
- **Standard** (50–300 lines, 2–5 files, follows existing patterns) — brainstorm identifies the pattern being followed. Example: adding import extraction for a new language.
- **Heavy** (300+ lines, new abstractions, multiple subsystems) — brainstorm must produce a written design with trade-offs before any code. Break into independently-committable units. Do not attempt in a single pass. Re-read actual code before each phase — design documents can anchor you to a flawed model.

### Verification gate

Run all three before every commit, in this order:

```bash
poetry run python -m black .         # formatting
poetry run lint-imports               # architectural contracts
poetry run python -m pytest tests/    # full test suite
```

Do not commit if any check fails. Fix, then re-run all three. Non-negotiable.

### Commits and state

- One logical unit per commit. Each commit must have its own tests.
- Push to `main` unless otherwise instructed.
- Update the README if the diffs warrant it.
- `bd backup` before every commit.
- Leave the working directory clean. No uncommitted files.
- Prefer a committed partial result over an uncommitted complete attempt. If a session may end, commit what's done with a `WIP:` prefix and file an issue for the remainder.
- When test counts are mentioned (e.g., "all 625 tests passing"), verify that count hasn't regressed.
- When generating output directories, attach a timestamp and technique used.

### Documentation

- Record salient architectural decisions as timestamped ADRs in `docs/architectural-design-decisions.md`.
- Never modify files in `docs/superpowers/specs/` or `docs/superpowers/plans/`.
- Update living documentation (README, `docs/type-system.md`, `docs/linker-design.md`, etc.) instead.

## Design Principles

- **Use existing infrastructure before adding new abstractions.** Ask: "does the system already have something that solves this?" The answer is usually yes. Example: anonymous class alias resolution was solved by reading the variable store at `new_object` time — the variable store already was a pointer table. Zero new infrastructure.
- **Start from the simplest possible mechanism.** Begin with minimal intervention. Add complexity only when proven insufficient.
- **Prefer emitting equivalent IR over threading conventions through multiple layers.** If a feature can be expressed using existing opcodes and builtins, do that. Example: rest parameters (`...args`) → `slice(arguments, N)` in IR, reusing the existing `slice` builtin.
- **No speculative code without tests.** Every code path must have a test that exercises it.
- **Stay consistent with established patterns.** When the codebase has a way of doing something (e.g., `TypeExpr` ADT), use it.
- **Never mask bugs with workaround guards.** Don't add `is not None` checks to make tests pass. Fix the root cause.
- **Pass decisions through data, don't re-derive downstream.** If a decision was made upstream, attach it to the data (e.g., `is_ctor` flag on `StackFrame`). Don't re-detect via fragile lookups.
- **Do not encode information in string representations.** Use typed objects (`Pointer`, `FuncRef`, `ClassRef`, etc.). Never use string prefixes, patterns, or regex to deduce what a value represents — use `isinstance`.

## Programming Patterns

### Code style

- Functional programming style. Avoid `for` loops with mutations — use comprehensions, `map`, `filter`, `reduce`.
- Prefer early return. Use `if` for exceptional cases, not the happy path.
- Small, composable functions. No massive functions.
- Fully qualified imports. No relative imports.
- One class per file (dataclass or otherwise).
- Logging, not `print` statements.
- Constants instead of magic strings and numbers. Wrap globals in classes.
- Enums for fixed string sets, not raw strings.

### Types and values

- No defensive programming. No `None` checks, no generic exception handling. If unsure, pause and ask.
- No `None` as a default parameter. Use empty structures (`{}`, `[]`, `()`).
- No `None` returns from non-None return types. Use null object pattern.
- No mutation after construction. Inject all dependencies at construction time.
- Domain-appropriate wrapping types for data crossing function boundaries. Wrap/unwrap at boundary layers only.
- Resolve enums into executable objects early in the call chain, then inject as dependencies.

### Architecture

- Ports-and-adapters. Functional core, imperative shell.
- Dependency injection for external systems (Neo4j, OS, file I/O, clocks, GUIDs).
- No static methods.

## Testing Patterns

- **TDD:** Write failing tests first. For every bug fix, write a test that fails without the fix.
- **Review assertions after writing tests.** After writing tests, review every assertion for specificity. Replace weak assertions (`assert x is not None`, `assert "name" in result`, `assert len(items) > 0`) with concrete value assertions (`assert result == 30`, `assert items == [1, 2, 3]`). If a concrete assertion isn't possible, document why.
- **Unit vs integration:** Unit tests (no I/O) in `tests/unit/`. Integration tests (LLMs, databases, external repos) in `tests/integration/`.
- **Fixtures:** Use `pytest` fixtures and `tmp_path` for filesystem tests.
- **No mocking:** Do not use `unittest.mock.patch`. Use dependency injection with mock objects.
- **Assertions are sacred:** Do not modify test assertions unless certain the change is valid. Do not remove assertions without review.
- **No implementation hacks for tests:** Never add special behavior just to make tests pass. Document hard-to-implement behavior or ask for guidance.
- **xfail for frontend gaps:** If a frontend doesn't handle a feature yet, write the real test with correct assertions, mark it `xfail` with `reason="description — <issue-id>"`, and file a corresponding Beads issue. The xfail reason must reference the issue ID so it's traceable. Don't rename tests or write fallback programs. Exclude languages that genuinely lack the feature (e.g., C has no classes).
- **Both unit and integration tests** for every new feature.

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

## Implementation Guidelines

- When implementing features for multiple languages, verify each language's actual capabilities against VM/frontend source code. Don't assume.
- When adding a language feature, consult existing frontend/VM documentation and implementation as reference before deciding on approach.
- When the user asks to scope to a specific subdirectory or module, scope precisely. Don't run on the broader repo.
- When working with LLM APIs, start with small test inputs before processing large datasets.
- Review subagent output for workaround guards (`is not None` checks that mask bugs).

## Interaction Style

- When interrupted or cancelled, immediately proceed with the new instruction. No clarifying questions — treat interruptions as implicit redirects.
- **Brainstorm collaboratively.** When thinking through approaches, present options and trade-offs to the user and actively incorporate their input before proceeding. Do not pick an approach and start implementing without discussion. The user's judgment on complexity/correctness trade-offs overrides the agent's default.
- **Stop and consult when patching.** If an implementation requires more than one corrective patch (fix-on-fix), stop. The design is wrong. Re-brainstorm the approach with the user before adding more patches. Accumulating compensating transforms is a sign the underlying model doesn't match reality.

## Python Introspection

- Write temporary scripts to `/tmp/*.py` and execute with `poetry run python /tmp/script.py`.
- Clean up temp files after use.
- Do not use `python -c` with multiline strings.

## Talisman (Secret Detection)

- If Talisman detects a potential secret, **stop** and prompt for guidance before updating `.talismanrc`.
- Don't overwrite existing `.talismanrc` entries — add at the end.

## External Dependencies

- Integration tests depend on local repo paths (`~/code/mojo-lsp`, `~/code/smojol`).
- COBOL frontend requires JDK 17+ and the ProLeap bridge JAR.
- Neo4j is optional (for graph persistence).
- Universal CTags is external (for code symbol extraction).
