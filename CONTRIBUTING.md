# Contributing to RedDragon

Thanks for your interest in contributing! RedDragon is an experimental project, and contributions are welcome.

## Getting Started

```bash
git clone https://github.com/avishek-sen-gupta/red-dragon.git
cd red-dragon
poetry install
```

For COBOL frontend support, you also need JDK 17+ and the ProLeap bridge JAR (see README for setup).

## Development Workflow

1. **Create a branch** for your feature or fix.
2. **Write tests first.** Unit tests go in `tests/unit/`, integration tests in `tests/integration/`. See [Testing](#testing) below.
3. **Implement** the feature or fix.
4. **Format** with Black: `poetry run python -m black .`
5. **Run the full test suite**: `poetry run python -m pytest tests/ -x -q`
6. **Open a pull request** against `main`.

## Testing

- Use `pytest` with fixtures for test setup.
- Use dependency injection instead of `unittest.mock.patch` — inject mock objects directly.
- Use the `tmp_path` fixture for any filesystem tests.
- Unit tests must not perform real I/O (no LLM calls, no database access, no network).
- Integration tests (LLM calls, external repos, databases) go in `tests/integration/`.
- Every bug fix should include a test that fails without the fix.
- Every new feature should have both unit and integration tests.

## Code Style

- **Python 3.13+**, managed with Poetry.
- **Black** formatting is enforced in CI — run `poetry run python -m black .` before committing.
- Prefer functional style: list comprehensions, `map`, `filter`, `reduce` over mutation-heavy `for` loops.
- Favour small, composable functions. Avoid large monolithic functions.
- Use fully qualified module imports — no relative imports.
- Use dependency injection for external system interfaces (Neo4j, file I/O, LLM clients, clocks, GUIDs).
- Prefer early return over deeply nested `if/else`.
- Use enums instead of magic strings for fixed value sets.
- Do not use `None` as a default parameter — use empty structures (`[]`, `{}`, etc.).
- Do not return `None` from functions with non-None return types — use null object pattern instead.
- Add logging (not `print`) for progress tracking, especially in loops and long-running tasks.

## Architecture

RedDragon follows a **functional core, imperative shell** (ports-and-adapters) architecture:

- **Frontends** (`interpreter/frontends/`) parse source and emit IR. Each language is a package with pure lowering functions dispatched via a context object.
- **IR** (`interpreter/ir.py`) is a flat list of three-address code instructions with 27 opcodes.
- **CFG** (`interpreter/cfg.py`, `interpreter/cfg_types.py`) builds control flow graphs from IR.
- **Dataflow** (`interpreter/dataflow/`) performs reaching definitions, def-use chains, and dependency analysis.
- **VM** (`interpreter/run.py`) executes IR deterministically, with optional LLM fallback for symbolic values.

## Adding a New Language Frontend

1. Create a package under `interpreter/frontends/<language>/`.
2. Implement `frontend.py` inheriting from `BaseFrontend`, overriding `_build_constants()`, `_build_stmt_dispatch()`, and `_build_expr_dispatch()`.
3. Add pure lowering functions in separate modules (e.g., `control_flow.py`, `expressions.py`, `assignments.py`).
4. Register the language in the frontend factory.
5. Add tests in `tests/unit/test_<language>_frontend.py`.
6. Add Rosetta cross-language tests to verify structural consistency with other frontends.

## Reporting Issues

Open an issue on [GitHub](https://github.com/avishek-sen-gupta/red-dragon/issues) with:

- A minimal code snippet that reproduces the problem
- The language and frontend type used
- Expected vs. actual IR or execution output

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE.md).
