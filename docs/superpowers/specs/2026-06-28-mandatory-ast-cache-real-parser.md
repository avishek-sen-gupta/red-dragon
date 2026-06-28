# Mandatory AST Cache + Real Parser Design

## Goal

Make the two-phase AST cache path the only path through `compile_cobol`. Remove all fake parsers from the codebase — every test that touches COBOL compilation uses a real `ProLeapCobolParser`.

## Motivation

The current `compile_cobol` has two paths: a default in-process path (parse + lower in one shot) and an opt-in cache path (Phase 1: parallel parse to disk; Phase 2: sequential load + lower). The in-process path is a memory hazard: Python's GC does not guarantee collection of ASG objects between loop iterations, so compiling N subprograms can accumulate N ASGs in memory simultaneously. The cache path eliminates this by ensuring at most one ASG is live at any moment.

Fake parsers (hand-crafted ASG dicts, `FakeSubprocessRunner`, `_FakeParseToFileParser`) hide real parsing bugs and misrepresent the system under test. The real bridge JAR is fast enough for unit tests; using it consistently removes a whole class of false confidence.

## Architecture

### `compile_cobol` — cache path becomes the only path

`parser` becomes a required keyword-only argument with no default. Callers must supply a `ProLeapCobolParser` explicitly.

`ast_cache_dir: Path | None = None` stays optional. When `None`, the function creates a `tempfile.TemporaryDirectory()` internally, runs the two-phase flow inside it, and removes it before returning. When supplied by the caller, cleanup is the caller's responsibility.

The non-cache `else` branch is deleted entirely.

### `compile_cobol_module` — `ast_path` always required

`ast_path: Path | None = None` default is removed. `ast_path` becomes a required positional-keyword argument. The `else` branch that called `frontend.lower(source)` is deleted.

### `make_cobol_parser` factory — new in `interpreter/cobol/cobol_parser.py`

```python
def make_cobol_parser(copybook_dirs: list[Path] | None = None) -> ProLeapCobolParser:
    bridge_jar = os.environ.get(
        "PROLEAP_BRIDGE_JAR",
        "proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar",
    )
    return ProLeapCobolParser(RealSubprocessRunner(), bridge_jar, copybook_dirs=copybook_dirs)
```

This makes the implicit default that currently lives inside `frontend.py` into an explicit, importable factory. `frontend.py`'s own fallback is left as-is — it serves direct callers of `get_frontend` and is out of scope.

## Files Changed

### Core

- **Modify** `interpreter/project/cobol_compile.py` — `parser` required, `ast_path` required, delete both non-cache else branches, auto-temp `TemporaryDirectory`
- **Modify** `interpreter/cobol/cobol_parser.py` — add `make_cobol_parser` factory

### Production callers

- **Modify** `interpreter/run.py` — add `parser = make_cobol_parser(copybook_dirs=copybook_dirs)` before `compile_cobol`
- **Modify** `interpreter/project/cobol_connections.py` — `parser` becomes required in `extract_cobol_connections`; propagated from caller
- **Modify** `jackal/jackal/cobol_step.py` — pass the `ProLeapCobolParser` it already constructs into `compile_cobol`
- **No change** `cicada/cics/bootstrap.py` — already passes a real parser
- **No change** `squall` — already passes a real parser

### Tests

- **Modify** `tests/unit/project/test_cobol_compile.py` — delete `_FakeParseToFileParser`; all `compile_cobol` and `parallel_parse_to_cache` calls get `parser=make_cobol_parser()`
- **Modify** `tests/unit/cobol/test_cobol_frontend_cache.py` — delete `_FakeRunner`; `CobolFrontend` constructed with `make_cobol_parser()`
- **Modify** `tests/unit/test_cobol_parser.py` — delete `FakeSubprocessRunner`; tests that verified bridge internals (command construction, stdin passing) are deleted since those behaviours are verified implicitly by successful parsing; tests that verify parsing behaviour (ASG deserialization, error enrichment) are rewritten with real COBOL source and `make_cobol_parser().parse(source)`
- **Modify** `tests/unit/test_cobol_frontend.py` — delete `_FakeParser`; all ~30 tests replace hand-crafted ASG dicts with real COBOL source strings compiled via `compile_cobol(source, parser=make_cobol_parser())`
- **Modify** `tests/unit/test_cobol_e2e.py` — delete `_FakeParser`; same migration as `test_cobol_frontend.py`
- **Modify** `tests/integration/project/test_cobol_connections.py` — add `parser=make_cobol_parser()` at each `extract_cobol_connections` callsite

## Test Strategy

All COBOL tests use `make_cobol_parser()` which reads `PROLEAP_BRIDGE_JAR` from the environment (with a default path). A test that uses only the bridge JAR and no other external dependencies (no database, no network, no filesystem beyond temp files) remains a unit test by definition — it lives in `tests/unit/`.

Tests that previously verified bridge internals (exact command arguments, stdin wire format) are deleted. Those properties are structurally guaranteed by the `ProLeapCobolParser` implementation and verified end-to-end whenever a test successfully parses real COBOL.

## Out of Scope

- `frontend.py`'s implicit `cobol_parser=None` fallback in `get_frontend` — left as-is for direct callers of `get_frontend`
- `cicada/tests/unit/cics/test_bootstrap.py` `_fake_compile` monkeypatch — tests dispatch logic, not COBOL parsing; not a fake parser
- `jackal/tests/unit/test_jcl_bridge_parser.py` `_FakeRunner` — JCL parsing, not COBOL
