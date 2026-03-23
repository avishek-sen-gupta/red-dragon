# RedDragon - Claude Code Instructions

## Task Tracking

Use `bd` (Beads) for all task tracking. Before starting work:
1. Run `bd ready` to see unblocked tasks
2. Claim your task: `bd update <id> --claim`
3. When done: `bd update <id> --status closed`
4. Before committing, always backup your work with `bd backup`, and push the exports to the remote repo.

Do NOT use markdown TODO lists. All tasks live in Beads.

## Workflow Rules

- For each feature, treat it as an independent commit / push, with its own unit/integration/e2e testing. Always implement changes incrementally, one at a time. Do not batch mass feature implementations across multiple languages/files without explicit approval. Commit and verify tests pass after each individual change.
- When asked to audit or show issues, only report findings — do not start fixing them unless explicitly asked to fix.
- The workflow is Brainstorm -> Discuss Trade-offs of different designs -> Plan -> Write unit tests -> Implement -> Fix Tests -> Commit -> Refactor.
- Do some brainstorming before starting work on a new feature / bugfix..
- When brainstorming / planning, consider the follow parameters:
  - Whether there are any open source projects which perform similar functionality, so that you don't have to write new code for the task
  - The complexity of the implementation matters. Think of a good balance between absolute correctness and "good enough". If in doubt, prompt me for guidance.
- Once a design is finalised, document salient architectural decisions as a timestamped Architectural Decision Record in `docs/architectural-design-decisions.md`.
- **Never modify files in `docs/superpowers/specs/` or `docs/superpowers/plans/`.** These are point-in-time design records. Newer specs supersede older ones by convention. Update living documentation (README, `docs/type-system.md`, etc.) instead.
- After completing implementation tasks, always run the full test suite before committing. Do not commit code that hasn't passed all tests.
- When implementing plans that span many files, complete each logical unit fully before moving to the next. Do not start a new task until the current one is committed. If the session may end, prefer a committed partial result over an uncommitted complete attempt.

### Enforced Phases Per Unit of Work

Every non-trivial task (feature, bugfix, refactor) must go through these phases in order. Do not skip phases. Do not start implementing before completing brainstorm.

1. **Brainstorm** — Understand the problem. Read the relevant code. Check how the existing system handles similar cases. Identify at least two approaches and their trade-offs. Ask: "does the system already have infrastructure for this?"
2. **Plan** — Choose an approach. Write it down (in the issue description, or verbally if small). For features that span multiple modules, identify the independently-committable units and their order.
3. **Test first** — Write failing tests that define the expected behavior. Do not write implementation code until at least one test exists that exercises the new behavior.
4. **Implement** — Write the minimum code to make the tests pass.
5. **Verify** — Run the full verification gate: `poetry run python -m black .` + `poetry run lint-imports` + `poetry run python -m pytest tests/`. All three must pass before committing.
6. **Commit** — One logical unit per commit. `bd backup` before `git add`. Push to remote.

### Complexity Classification

Before starting work, classify the task:

- **Light** (< 50 lines changed, single file, no new abstractions) — brainstorm can be brief. Example: adding a node type to a dispatch table.
- **Standard** (50-300 lines, 2-5 files, uses existing patterns) — brainstorm should identify the pattern being followed. Example: adding import extraction for a new language.
- **Heavy** (300+ lines, new abstractions, multiple subsystems) — brainstorm must produce a written design with trade-offs before any code. Example: the multi-file linker. Break into independently-committable units. Do not attempt in a single pass.

### Verification Gate

Before every commit, run all three checks in this order:

```bash
poetry run python -m black .                    # formatting
poetry run lint-imports                          # architectural contracts
poetry run python -m pytest tests/              # full test suite
```

Do not commit if any check fails. Fix the failure, then re-run all three. This is non-negotiable — the CI pipeline enforces all three, and a local failure that passes CI by luck is still a process failure.
## Project Context
- Primary languages: Python (main codebase), TypeScript/JavaScript (tooling/web), Markdown (docs).
- When editing Python, always run `black` formatting before committing. When test counts are mentioned (e.g., 'all 625 tests passing'), verify that count hasn't regressed.
- When you are generating a new run, for every output directory, please attach time stamp and the technique used

## Design Principles

- **Use existing infrastructure before adding new abstractions.** Before introducing a new dict, registry, or tracking structure, ask: "does the system already have something that solves this?" The answer is usually yes.
  - *Example:* When anonymous class expressions needed alias resolution (`const Foo = class { ... }; new Foo()`), three progressively simpler designs were attempted: (1) a `class_aliases` dict in the registry, (2) a pointer chain mechanism, (3) just reading the variable store at `new_object` time — because the variable store already *was* a pointer table mapping `Foo` → `<class:__anon_class_0@...>`. The final solution was a 5-line dereference in `_handle_new_object` with zero new infrastructure.
- **Start from the simplest possible mechanism.** When solving a problem, begin with the minimal intervention. If that's insufficient, add complexity incrementally. Do not start with a rich abstraction and work backwards.
- **Prefer emitting equivalent IR over threading new conventions through multiple layers.** When a feature can be expressed as IR using existing opcodes and builtins, do that — don't introduce new prefixes, registry fields, or VM conventions. Example: rest parameters (`...args`) were implemented by emitting `slice(arguments, N)` in the function body IR, reusing the existing `slice` builtin, instead of threading a `param_rest:` prefix through frontend → registry → VM.
- **Don't add speculative code without tests proving it works.** Every code path must have a test that exercises it. Untested "nice to have" branches hide bugs — e.g., a string slice branch that accidentally sliced heap address strings (`'arr_0'[2:]` → `'r_0'`).
- **Stay consistent with established patterns.** When the codebase has a way of doing something (e.g., `TypeExpr` ADT for types), use it — do not fall back to older patterns (e.g., format strings through `parse_type()`) out of habit.
- **Never mask bugs with workaround guards.** When a test fails, don't add a guard (like `value is not None`) that makes it pass without understanding *why* it fails. Fix the root cause. A passing test suite does not mean the code is correct.
- **Pass decisions through data, don't re-derive them downstream.** If a decision has been made upstream (e.g., "this is a constructor call"), attach it to the data flowing through the system (e.g., `is_ctor` flag on `StackFrame`). Do not re-detect the same decision downstream via fragile lookups or heuristics.

## Implementation Guidelines
- When implementing features for multiple languages, verify each language's actual capabilities against VM/frontend source code rather than assuming. Do not claim a language lacks a feature without checking.
- When adding a new language feature, consult the existing language frontend/VM documentation / implementation (if it exists) to see how it does this. Use that as a reference, then decide how much deviation is needed to adapt it to our VM.

## Common Mistakes to Avoid
- When the user asks to run detection/analysis on a specific subdirectory or module (e.g., 'smojol-api'), scope the operation precisely to that directory. Do not run on the parent repo or broader scope unless explicitly asked.
- When working with LLM API calls or external APIs, start with small test inputs before processing large datasets. Large inputs (e.g., full grammar files, large symbol sets) can overflow context windows or crash connections.
- Review subagent output for workaround guards — subagents will add `is not None` checks or similar guards to make test suites pass, masking real bugs instead of fixing root causes.

## Interaction Style
- When a user interrupts or cancels a task, do not ask clarifying questions — immediately proceed with the redirected instruction. Treat interruptions as implicit 'stop what you're doing and do this instead'.

## Python introspection commands
- Write temporary scripts to /tmp/*.py and execute with `poetry run python /tmp/script.py` rather than using python -c with multiline strings. Clean up temp files after use.

## Build

- When asked to commit and push, always push to 'main' branch, unless otherwise instructed.
- Before committing anything, update the README based on the diffs.
- Before committing anything, run the full verification gate (black + lint-imports + pytest). See "Verification Gate" above.
- If test assertions are being removed, ask me to review them.
- Always leave the working directory clean. Commit all changes (including transient file deletions) before finishing work. Never leave uncommitted files behind.

### Fresh Context for Heavy Tasks

For tasks classified as **Heavy** (300+ lines, new abstractions), explicitly re-read the relevant code at the start of each phase. Do not rely on assumptions from earlier phases — design documents can anchor you to a flawed model. Before implementing, re-read the actual code that your implementation will interact with (VM dispatch, registry scanning, CFG building, etc.).

### State on Disk

All work state must survive session crashes:
- `bd backup` before every commit (ensures Beads state is exported)
- Issues filed before work starts (ensures intent is recorded even if session dies)
- Prefer committed partial results over uncommitted complete attempts
- If a session may end, commit what's done with a clear "WIP:" prefix and file an issue for the remainder

## Testing Patterns

- Use `pytest` with fixtures for test setup
- Do not patch with `unittest.mock.patch`. Use proper dependency injection, and then inject mock objects.
- You may not modify tests unless you're absolutely certain that the test change is valid for the behaviour you are verifying.
- Use `tmp_path` fixture for filesystem tests
- Tests requiring external repos (mojo-lsp, smojol) are integration tests
- When fixing tests, do not blindly change test assertions to make the test pass. Only modify assertions once you are sure that the actual code output is actually valid according to the context.
- Always start from writing unit tests for the smallest feasible units of code. True unit tests (which do not exercise true I/O) should be in a `unit` directory under the test directory. Tests which exercise I/O (call LLMs, touch databases) should be in the `integration` directory under the test directory.
- Make sure you are not creating any special implementation behaviour just to get the tests to pass. It's far better to document hard-to-implement behaviour than to try to fix the test for the test's sake. Alternatively, pause and ask me for guidance.
- Write both unit and integration tests for every new feature.
- Never rename tests or write fallback programs to avoid testing a feature the language actually supports. If a frontend doesn't handle the feature yet, write the real program with correct assertions, mark it `xfail`, and file an issue for the gap. Exclude languages that genuinely lack the feature (e.g., C has no classes) rather than faking a test.


## Programming Patterns

- Categorically avoid defensive programming. This includes checking for None, and adding generic exception handling. If you are unaware of a better way to handle a situation, pause and ask me for guidance.
- Use proper dependency injection for interfaces to external systems like Neo4J, OS, and File I/O. Do not hardcode importing the concrete modules in these cases. This applies especially to I/O or nondeterministic modules (eg: clock libraries, GUID libraries, etc.).
- For every bug you fix, make sure you have a test that fails without the bug fix. If you don't have a test that fails without the bug fix, write one.
- Minimise and/or avoid mutation.
- STOP USING FOR LOOPS WITH MUTATIONS IN THEM. JUST STOP.
- Write your code aggressively in the Functional Programming style, but balance it with readability. Avoid for loops where list comprehensions, map, filter, reduce, etc. can be used.
- Minimise magic strings and numbers by refactoring them into constants
- Don't expose raw global variables in files indiscriminately; wrap them as constants in classes, etc.
- When writing `if` conditions, prefer early return. Use `if` conditions for checking and acting on exceptional cases. Minimise or eliminate triggering happy path in `if` conditions.
- Parameters in functions, if they must have default values, must have those values as empty structures corresponding to the non-empty types (empty dictionaries, lists, etc.). Categorically, do not use None.
- If a function has a non-None return type, never return None.
- If a function returns a non-None type in its signature, but cannot return an object of that type because of some condition, use null object pattern. Do not return None.
- Prefer small, composable functions. Do not write massive functions.
- Do not use static methods. EVER.
- Add copious helpful logs to track progress of tasks, especially long-running ones, or ones which involve loops.
- Use a ports-and-adapter type architecture in your design decisions. Adhere to the tenet of "Functional Core, Imperative Shell".
- When importing, use fully qualified module names. Do not use relative imports.
- Favour one class per file, dataclass or otherwise.
- If enums map to actual objects with behaviour (if they represent configurable functionalities, for example), resolve them into the actual executable objects as early on in the call chain as possible, and inject those objects as dependencies, not the enums.
- For variables which can only take a fixed set of values (a set of strings, for example), use enums instead of strings.
- Avoid using direct print statements, unless it's for one-off debugging. Use logging facilities.
- Do not mutate objects to initialise them. All dependencies should be injected during object construction time.
- Do not use primitives to pass around data across functions. Make sure you are using domain-appropriate wrapping types. Any wrapping / unwrapping should happen strictly at the boundary layers of the system.
- **Do not encode information in string representations.** Use typed objects (`Pointer`, `FuncRef`, `ClassRef`, etc.) to carry structured data. Never use string prefixes, patterns, or regex to deduce what a value represents — use `isinstance` checks on the actual type.

## Code Review Patterns

- Use the `Programming Patterns` section to ensure compliance of code.

## Dependencies

- Python 3.13+
- Poetry for dependency management
- Universal CTags (external) for code symbol extraction
- Neo4j (optional) for graph persistence

## Notes

- Use `poetry run` prefix for all Python commands
- If Talisman detects a potential secret, stop what you are doing, prompt me for what needs to be done, and only then should you update the `.talismanrc` file.
- Potential secrets in files trigger Talisman pre-commit hook - add to `.talismanrc` if needed. Don't overwrite existing `.talismanrc` entries, add at the end
- Integration tests depend on local repo paths (`~/code/mojo-lsp`, `~/code/smojol`)
