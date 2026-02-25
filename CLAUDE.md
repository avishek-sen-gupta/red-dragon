# RedDragon - Claude Code Instructions

## Workflow Rules

- After completing implementation tasks, always run the full test suite before committing. Do not commit code that hasn't passed all tests.
- When implementing plans that span many files, complete each logical unit fully before moving to the next. Do not start a new task until the current one is committed. If the session may end, prefer a committed partial result over an uncommitted complete attempt.
## Project Context
- Primary languages: Python (main codebase), TypeScript/JavaScript (tooling/web), Markdown (docs).
- When editing Python, always run `black` formatting before committing. When test counts are mentioned (e.g., 'all 625 tests passing'), verify that count hasn't regressed.

## Common Mistakes to Avoid
- When the user asks to run detection/analysis on a specific subdirectory or module (e.g., 'smojol-api'), scope the operation precisely to that directory. Do not run on the parent repo or broader scope unless explicitly asked.
- When working with LLM API calls or external APIs, start with small test inputs before processing large datasets. Large inputs (e.g., full grammar files, large symbol sets) can overflow context windows or crash connections.

## Interaction Style
- When a user interrupts or cancels a task, do not ask clarifying questions — immediately proceed with the redirected instruction. Treat interruptions as implicit 'stop what you're doing and do this instead'.

## Build

- When asked to commit and push, always ask which branch to push to unless it's already clear from context. Never assume 'main' branch.
- Before committing anything, update the README based on the diffs. I should not have to repeat this in my instructions.
- Before committing anything, run `poetry run black` on every Python file touched in the change. The CI pipeline enforces Black formatting and will fail if this is skipped.
- Before committing anything, run all tests, fixing them if necessary. If test assertions are being removed, ask me to review them.

## Testing Patterns

- Use `pytest` with fixtures for test setup
- Do not patch with `unittest.mock.patch`. Use proper dependency injection, and then inject mock objects.
- Use `tmp_path` fixture for filesystem tests
- Tests requiring external repos (mojo-lsp, smojol) are integration tests
- When fixing tests, do not blindly change test assertions to make the test pass. Only modify assertions once you are sure that the actual code output is actually valid according to the context.
- Always start from writing unit tests for the smallest feasible units of code. True unit tests (which do not exercise true I/O) should be in a `unit` directory under the test directory. Tests which exercise I/O (call LLMs, touch databases) should be in the `integration` directory under the test directory.

## Programming Patterns

- Use proper dependency injection for interfaces to external systems like Neo4J, OS, and File I/O. Do not hardcode importing the concrete modules in these cases. This applies especially to I/O or nondeterministic modules (eg: clock libraries, GUID libraries, etc.).
- Minimise and/or avoid mutation.
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
