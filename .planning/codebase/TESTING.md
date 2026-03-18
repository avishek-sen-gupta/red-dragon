# Testing Patterns

**Analysis Date:** 2026-03-18

## Test Framework

**Runner:**
- pytest 8.0.0+
- Config: `pyproject.toml` under `[tool.pytest.ini_options]`

**Test Discovery:**
- Testpaths: `tests/`
- Execution: `poetry run python -m pytest` (not `poetry run pytest`)

**Run Commands:**
```bash
poetry run python -m pytest tests/                   # Run all tests
poetry run python -m pytest tests/ -n auto           # Run with parallel workers (auto-detected)
poetry run python -m pytest tests/ -m 'not external' # Exclude external API tests
poetry run python -m pytest tests/ -v                # Verbose output
poetry run python -m pytest tests/ --tb=short        # Shorter tracebacks
```

**Marker Configuration:**
```toml
markers = [
    "external: tests requiring external services (LLM APIs); run with -m external",
]
```

Use `-m 'not external'` to exclude tests that require live LLM API calls (default in CI).

## Test File Organization

**Structure:**
```
tests/
├── unit/                          # Pure logic tests, no VM execution
│   ├── test_*.py                  # Single-function/class unit tests
│   ├── rosetta/                   # Cross-language IR lowering tests
│   │   ├── conftest.py            # Shared rosetta fixtures
│   │   └── test_rosetta_*.py      # Multi-language lowering/execution
│   ├── exercism/                  # Exercism problem suites
│   │   ├── conftest.py            # Solution loading, canonical case fixtures
│   │   ├── test_exercism_*.py     # Parametrized test generation
│   │   └── exercises/             # Problem definitions and solutions
│   │       └── {exercise}/
│   │           ├── canonical_data.json
│   │           └── solutions/
│   │               └── {language}.{ext}
│   ├── equivalence/               # Cross-language IR equivalence assertions
│   │   ├── conftest.py            # Cross-language helpers
│   │   └── test_*_equiv.py        # Opcode sequence comparison tests
│   └── demos/                     # Demo/reference programs
└── integration/                   # VM execution tests (end-to-end)
    └── test_*_execution.py        # Full pipeline: parse → lower → execute
```

**Naming:**
- Unit tests: `test_{component}.py` (e.g., `test_registry.py`, `test_type_expr.py`)
- Rosetta tests: `test_rosetta_{feature}.py` (e.g., `test_rosetta_linked_list.py`)
- Integration tests: `test_{language}_execution.py` or `test_{feature}_execution.py`

## Test Structure

**Standard Unit Test Pattern:**
```python
"""Tests for some module."""

from __future__ import annotations

from interpreter.some_module import SomeClass


class TestSomeFeature:
    """Descriptive suite name for a logical grouping."""

    def test_specific_behavior_case(self):
        """Clear description of what behavior is being tested."""
        # Arrange
        obj = SomeClass(param=value)

        # Act
        result = obj.some_method()

        # Assert
        assert result == expected_value
```

**Rosetta Cross-Language Pattern:**
```python
"""Rosetta test: {feature} across all 15 deterministic frontends."""

from __future__ import annotations

from interpreter.frontends import SUPPORTED_DETERMINISTIC_LANGUAGES
from interpreter.ir import Opcode

from tests.unit.rosetta.conftest import (
    parse_for_language,
    assert_clean_lowering,
    assert_cross_language_consistency,
    execute_for_language,
    extract_answer,
    STANDARD_EXECUTABLE_LANGUAGES,
)

PROGRAMS: dict[str, str] = {
    "python": """...""",
    "javascript": """...""",
    # ... all 15 languages
}


class TestLoweringAllLanguages:
    """Lowering tests verify IR generation from each language."""

    @pytest.mark.parametrize("language", SUPPORTED_DETERMINISTIC_LANGUAGES)
    def test_lowers_to_required_opcodes(self, language):
        ir = parse_for_language(language, PROGRAMS[language])
        assert_clean_lowering(
            ir,
            min_instructions=10,
            required_opcodes={Opcode.LOAD_VAR, Opcode.STORE_VAR},
            language=language,
        )


class TestExecutionAllLanguages:
    """Execution tests verify VM produces consistent results."""

    @pytest.mark.parametrize("language", STANDARD_EXECUTABLE_LANGUAGES)
    def test_execution_produces_answer(self, language):
        vm, stats = execute_for_language(language, PROGRAMS[language])
        assert extract_answer(vm, language) == expected_value
```

**Integration Test Pattern (Full VM Execution):**
```python
"""Integration tests for {feature} end-to-end execution."""

from __future__ import annotations

from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_program(source: str, language: str = "python", max_steps: int = 500) -> dict:
    """Helper: parse, lower, and execute, return unwrapped locals."""
    vm = run(source, language=language, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestCFeatureExecution:
    def test_feature_works(self):
        source = """\
int x = 42;
"""
        vars_ = _run_program(source, language="c")
        assert vars_["x"] == 42
```

## Test Data & Fixtures

**Conftest Files:**
- `tests/unit/rosetta/conftest.py` — Rosetta execution helpers
  - `parse_for_language(language, source)` — Parse and lower via deterministic frontend
  - `execute_for_language(language, source)` — Full pipeline execution
  - `extract_answer(vm, language)` — Extract `answer` variable from frame 0 locals
  - `extract_array(vm, var_name, length, language)` — Extract heap array
  - `assert_clean_lowering(ir, min_instructions, required_opcodes, language)` — Verify IR quality
  - `assert_cross_language_consistency(results, required_opcodes, expected_languages)` — Verify all languages produce consistent opcodes

- `tests/unit/exercism/conftest.py` — Exercism problem suite helpers
  - `load_solution(exercise, language)` — Read solution source file
  - `load_canonical_cases(exercise, property_filter="")` — Load JSON test cases
  - `format_arg(value, language)` — Format Python value as language literal
  - `build_program(solution_source, function_name, args, language)` — Substitute function arguments into solution

- `tests/unit/equivalence/conftest.py` — IR equivalence helpers
  - `function_opcode_sequence(language, source, func_name)` — Extract normalized opcode sequence (no LABELs, DECL_VAR normalized to STORE_VAR)

**Test Data Location:**
- Solution code: `tests/unit/exercism/exercises/{exercise}/solutions/{language}.{ext}`
- Canonical test cases: `tests/unit/exercism/exercises/{exercise}/canonical_data.json`

**Language Extension Mapping:**
```python
LANGUAGE_EXTENSIONS: dict[str, str] = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "java": ".java",
    "ruby": ".rb",
    "go": ".go",
    "php": ".php",
    "csharp": ".cs",
    "c": ".c",
    "cpp": ".cpp",
    "rust": ".rs",
    "kotlin": ".kt",
    "scala": ".scala",
    "lua": ".lua",
    "pascal": ".pas",
}
```

## Dependency Injection & Mocking

**Pattern: Fake Implementations Instead of Mocks**

The codebase uses fake implementations (subclasses) rather than `unittest.mock.patch`:

```python
from interpreter.llm_client import LLMClient

class FakeLLMClient(LLMClient):
    """Fake LLM client that returns canned responses."""

    def __init__(self, response: str = "[]"):
        self.response = response
        self.calls: list[dict] = []

    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_message": user_message,
            "max_tokens": max_tokens,
        })
        return self.response


class TestLLMFrontend:
    def test_parsing(self):
        fake_client = FakeLLMClient(response='[{"opcode":"CONST","operands":["42"]}]')
        frontend = LLMFrontend(llm_client=fake_client)
        result = frontend.lower(b"some source")
        assert len(fake_client.calls) == 1
```

**No Patching:**
- Avoid `unittest.mock.patch` — dependencies are always injected
- Fake subclasses control behavior deterministically
- Assertion tracking on fake instances (`.calls` list) replaces mock assertions

## Test Markers & Selection

**External Service Tests:**
```python
@pytest.mark.external
def test_calls_live_llm_api():
    """Test requires actual LLM API (OpenAI, Claude, etc)."""
    result = llm_frontend.lower(source)
    assert result is not None
```

Run with: `poetry run python -m pytest tests/ -m external`

**Expected Failures (xfail):**
```python
@pytest.mark.xfail(reason="Pascal doesn't support pointer dereferencing yet")
def test_pascal_pointer_deref():
    """This test documents a known gap in Pascal frontend."""
    vm, _ = execute_for_language("pascal", PROGRAM)
    assert extract_answer(vm, "pascal") == 42
```

Use xfail when a feature is not yet implemented in a language frontend. The test stays in the suite but doesn't block CI.

## Async Testing

**Not Used:** All tests are synchronous. The VM is deterministic and doesn't use async/await.

## Error Testing

**Error Assertions in Unit Tests:**
```python
def test_invalid_opcode_raises(self):
    """Invalid opcodes should raise TypeError."""
    with pytest.raises(TypeError, match="invalid opcode"):
        IRInstruction(opcode="INVALID", operands=[])
```

**VM Halting on Errors (Integration Tests):**
```python
def test_undefined_variable_halts(self):
    source = "print(undefined_var)"
    vm = run(source, language="python", max_steps=500)
    # VM execution halts; check execution stats or exception
    # (Error behavior depends on VM error handler configuration)
```

## Coverage

**Requirements:** No explicit coverage targets enforced in CI (yet).

**Code Quality Exclusions:**
```toml
[tool.radon]
exclude = "tests/*"
cc_min = "C"
```

Tests are excluded from complexity analysis (radon).

## Test Categories

**Unit Tests (No VM Execution):**
- IR instruction validation (`tests/unit/test_ir_*.py`)
- Registry/CFG building (`tests/unit/test_registry.py`, `tests/unit/test_cfg.py`)
- Type system (`tests/unit/test_type_expr.py`, `tests/unit/test_type_resolver.py`)
- Frontend lowering (without VM) (`tests/unit/test_*_frontend.py`)
- Data structures and utilities

**Rosetta Lowering Tests (Parse + Lower, No Execution):**
- All 15 language frontends must lower the same program
- Files: `tests/unit/rosetta/test_rosetta_*.py`
- Assertions: entry label, opcode presence, no unsupported symbolics

**Rosetta Execution Tests (Full VM Pipeline):**
- Verify 15 languages execute with consistent results
- Files: `tests/integration/test_*_execution.py`, `tests/unit/rosetta/test_rosetta_*.py`
- Helpers: `execute_for_language()`, `extract_answer()`
- Max steps: 2000 default, configurable per test

**Exercism Test Suites:**
- Parametrized tests that load canonical problem definitions
- Generate test cases with multiple argument combinations
- Verify solution code works across languages
- Files: `tests/unit/exercism/test_exercism_*.py`

**Equivalence Tests:**
- Verify IR opcode sequences match across languages (normalized)
- Extract function body, compare opcode stream
- Files: `tests/unit/equivalence/test_*_equiv.py`

## Key Helpers in .planning/

**From rosetta/conftest.py:**
- `parse_for_language(language, source)` → `list[IRInstruction]`
- `execute_for_language(language, source, max_steps=2000)` → `tuple[VMState, ExecutionStats]`
- `extract_answer(vm, language)` → object (the `answer` variable)
- `assert_clean_lowering(ir, min_instructions, required_opcodes, language)` → None (raises AssertionError on violation)
- `assert_cross_language_consistency(results, required_opcodes, expected_languages)` → None

**From exercism/conftest.py:**
- `load_solution(exercise, language)` → str
- `load_canonical_cases(exercise, property_filter="")` → list[dict]
- `build_program(solution_source, function_name, args, language)` → str (with substituted call)
- `format_arg(value, language)` → str (e.g., "True" in Python, "true" in JS)

## Common Patterns in Tests

**Testing VM Execution Results:**
```python
def test_variable_assignment(self):
    vm = run("x = 42", language="python")
    locals_dict = unwrap_locals(vm.call_stack[0].local_vars)
    assert locals_dict["x"] == 42
```

**Accessing Heap Objects:**
```python
def test_object_creation(self):
    source = """\
class Dog:
    def __init__(self, name):
        self.name = name
d = Dog("Rex")
"""
    vm = run(source, language="python")
    vars_ = unwrap_locals(vm.call_stack[0].local_vars)
    obj_addr = vars_["d"]  # Heap address string
    assert vm.heap[obj_addr].fields.get("name").value == "Rex"
```

**Language-Specific Variable Names:**
PHP variables include the `$` prefix:
```python
def extract_answer(vm: VMState, language: str) -> object:
    var_name = f"${var_name}" if language == "php" else var_name
    frame = vm.call_stack[0]
    return frame.local_vars[var_name].value
```

**Asserting Clean Lowering (4-Tier Battery):**
1. First instruction is `LABEL("entry")`
2. Minimum instruction count satisfied
3. Zero `SYMBOLIC` instructions with `"unsupported:"` in operands
4. All required opcodes present in IR

## Execution Statistics & Limits

**ExecutionStats Fields:**
- `steps` — Number of VM steps executed (useful for perf regressions)
- `llm_calls` — Number of LLM API calls made (0 for deterministic execution)

**Max Steps Configuration:**
```python
vm, stats = execute_for_language(language, source, max_steps=2000)
assert stats.steps < 200  # Verify it completed quickly
```

Typical tests use 300–500 steps for small programs. Reduce for hot-path tests, increase for complex recursion.

---

*Testing analysis: 2026-03-18*
