## Workflow

### Phases (mandatory, in order)

Every non-trivial task goes through these phases. Do not skip. Do not start implementing before completing brainstorm.

1. **Brainstorm** — **Always invoke the `superpowers:brainstorming` skill first.** Read the relevant code. Check how the existing system handles similar cases. Identify at least two approaches and their trade-offs. Ask: "does the system already have infrastructure for this?" Consider whether an open-source project already solves the problem.
2. **Plan** — Choose an approach. For features spanning multiple modules, identify independently-committable units and their order. For Heavy tasks, write the design down before proceeding. Use the `superpowers:writing-plans` skill for multi-step tasks.
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

Run all four before every commit, in this order:

```bash
poetry run python -m black .         # formatting
poetry run lint-imports               # architectural contracts
poetry run pyright interpreter/ mcp_server/  # type checking (basic mode; errors expected until per-file # pyright: standard promotion is complete)
poetry run python -m pytest tests/    # ALL tests (unit + integration), not just tests/unit/
```

Do not commit if any check fails. Fix, then re-run all four. Non-negotiable.
**Exception:** During the type annotation migration (Tasks 2–17 of the type-hints plan), pyright will report errors on unannotated files — this is expected. Each file is promoted to `# pyright: standard` as it is annotated; only promoted files are held to zero-error standard.

### Commits and state

- One logical unit per commit. Each commit must have its own tests.
- Push to `main` unless otherwise instructed.
- Update README and other living docs (ADRs, linker-design.md, type-system.md, etc.) if the diff changes public behavior, adds features, or modifies architecture. This is part of the commit, not a follow-up.
- `bd backup` before every commit.
- Leave the working directory clean. No uncommitted files.
- Prefer a committed partial result over an uncommitted complete attempt. If a session may end, commit what's done with a `WIP:` prefix and file an issue for the remainder.
- When test counts are mentioned (e.g., "all 625 tests passing"), verify that count hasn't regressed.
- When generating output directories, attach a timestamp and technique used.

### Data security

- **NEVER reference external codebases under analysis** (names, APIs, domains, packages, class names, organisation names) in any tracked artifact: commit messages, issues, specs, plans, docs, code comments, test names, screenshots.
- Use generic examples (`com.example.utils`, `class Foo`) instead of real names from codebases being analysed.
- Keep external-codebase-specific context in untracked experiment directories only.
- The consequences of leaking proprietary identifiers into public git history are catastrophic.

### Documentation

- Record salient architectural decisions as timestamped ADRs in `docs/architectural-design-decisions.md`.
- Never modify files in `docs/superpowers/specs/` or `docs/superpowers/plans/`.
- Update living documentation (README, `docs/type-system.md`, `docs/linker-design.md`, etc.) instead.
