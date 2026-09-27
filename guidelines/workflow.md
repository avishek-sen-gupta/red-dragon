## Workflow

### Phases (mandatory, in order)

Every non-trivial task goes through these. Do not start implementing before completing brainstorm.

1. **Brainstorm** — Read the relevant code and check how the system handles similar cases. Identify at least two approaches and their trade-offs. Ask whether the system already has infrastructure for this, and whether an open-source project already solves it. Weigh absolute correctness against "good enough"; if in doubt, ask.
2. **Plan** — Choose an approach. For features spanning multiple modules, identify independently-committable units and their order.
3. **Test first** — Write failing tests that define the expected behaviour. No implementation code until at least one test exists.
4. **Implement** — Write the minimum code to make the tests pass.
5. **Self-review** — Review your own diff against `guardrails.md` and `design-principles.md`, using the checklist in `code-review.md`.
6. **Verify** — Run the full verification gate below. All checks must pass.
7. **Commit** — One logical unit per commit.

When asked to audit or show issues, only report findings — do not fix unless explicitly asked.

### Complexity classification

Classify before starting; this sets how much ceremony is needed.

- **Light** (< 50 lines, single file, no new abstractions) — brief brainstorm. Example: adding an entry to a dispatch table.
- **Standard** (50–300 lines, 2–5 files, follows existing patterns) — brainstorm identifies the pattern being followed.
- **Heavy** (300+ lines, new abstractions, multiple subsystems) — brainstorm must produce a written design with trade-offs before any code. Break into independently-committable units; do not attempt in a single pass. Re-read the actual code before each phase, since a design document can anchor you to a flawed model.

### Verification gate

Run all of these before every commit. If you imported a language layer, its
`workflow.md` already substitutes the concrete commands; otherwise fill them in.

```bash
<formatter> .        # e.g. black, prettier, google-java-format
<type-checker>       # e.g. pyright --strict, tsc --noEmit, javac -Werror
<linter>             # architectural contracts: import-linter, eslint boundaries, ArchUnit
<test-runner> tests/ # ALL tests, unit and integration
```

Do not commit if any check fails. Fix, then re-run all of them. Non-negotiable.

**Prefer a machine-checkable gate to a written rule.** A convention that a
checker can decide belongs in the linter slot above, not only in these files:
prose is advisory and degrades as a session grows, while a gate fails the commit
the same way every time. When a rule here has a corresponding check, the check is
the enforcement and this document is the rationale. Adding a rule is therefore
two questions — what does it say, and what fails the build when it is broken? If
nothing can, say so, so the reader knows it rests on review alone.

Never silence a gate to make a commit pass. A violation is either a defect to fix
or a rule to change deliberately, in its own commit, with the reason recorded.

### Commits and state

- One logical unit per commit, even when mechanical. Each commit carries its own tests and is separately reviewable and revertible.
- Push to `main` unless otherwise instructed.
- Complete each unit fully before starting the next. Do not begin new work while the current unit is uncommitted.
- Prefer a committed partial result over an uncommitted complete attempt. If a session may end, commit what's done with a `WIP:` prefix and file an issue for the remainder.
- Leave the working directory clean.
- When generating output directories, attach a timestamp and the technique used.

### Documentation

- Update the README and other living docs in the **same commit** as the change, whenever the diff alters public behaviour, adds a feature, or changes architecture. This is not a follow-up task.
- Record salient architectural decisions as timestamped ADRs.
- Never modify immutable specs and design records. Update the living documentation instead.
