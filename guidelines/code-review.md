## Code Review

Use `guardrails.md`, `design-principles.md` and `programming-patterns.md` as the rubric.

### Self-review checklist

Before every commit, scan the diff for the following. Apply it to subagent output as closely as to your own — delegated code arrives unreviewed.

- **Workaround guards** — null checks, bare catch-alls, or a branch added to pass a test without understanding the failure.
- **Comments that shouldn't exist** — anything beyond a one-line class or module header.
- **Speculative abstractions** — extension points, configuration knobs, or generality with no current caller.
- **Weak assertions** — an existence or containment check where a concrete value was available.
- **Mutation in loops** — accumulators inside `for` loops instead of functional constructs.
- **Stale documentation** — if the diff changes what a run does, what a tool accepts, or what lands on disk, the docs change in the same commit.
- **Missing tests** — a new code path with no test; a new tool or entry point especially.
- **Leaked abstractions** — internal labels or implementation details surfacing in public APIs or test assertions.
- **Data as strings** — a `*_json` field, a hand-built map standing in for a record, a serialisation call outside an adapter or file write.
- **Constraints hidden in the function body** — a check on arguments the caller never sees, when it could have been declared on the field.
- **Dead code** — unused imports, unreachable branches, values assigned and never read, machinery with no caller.
- **Subprocess arguments** — an externally-supplied string reaching `argv` where the child could read it as an option.

### Guards that read state

A guard that asks for the *latest* entry in an append-only log is almost always wrong. Entries are appended rather than replaced, and a process records its terminal status before it finishes writing — so the last entry is the uninteresting one. Ask whether the history *contains* what you care about, and ask it inside the transaction that acts on the answer.

### Requested reviews

Order findings by severity:

1. **CRITICAL** — a sandbox escape, a data-loss risk, a secret in a tracked artifact
2. **HIGH** — a likely bug, a broken invariant, a significant performance problem
3. **MEDIUM** — code quality, a contract that defers rather than states
4. **LOW** — minor improvements

Report findings only; do not fix during a review. File issues for anything needing follow-up. Distinguish what you read from the code from what you actually reproduced, and say which is which — an unverified reading is a hypothesis, and calling it a bug wastes the reader's trust.
