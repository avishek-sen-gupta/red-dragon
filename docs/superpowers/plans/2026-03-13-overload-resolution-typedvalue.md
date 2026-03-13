# Overload Resolution: TypedValue Args + Subtype-Aware Scoring — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `TypedValue` args through the overload resolution chain and integrate `TypeGraph.is_subtype_expr()` for inheritance-aware method dispatch.

**Architecture:** Change the resolver interface from `list[Any]` to `list[TypedValue]` end-to-end (compatibility scorer → strategy → resolver → ambiguity handler). Inject `TypeGraph` (built from `registry.class_parents`) into `DefaultTypeCompatibility` for subtype scoring. Retain `_COMPATIBLE_PAIRS` for primitive coercion.

**Tech Stack:** Python 3.13+, pytest, TypedValue/TypeExpr from interpreter/typed_value.py and interpreter/type_expr.py

---

## Chunk 1: Interface Migration + TypeCompatibility

### Task 1: Update DefaultTypeCompatibility to accept TypedValue and TypeGraph

**Files:**
- Modify: `interpreter/type_compatibility.py`
- Test: `tests/unit/test_type_compatibility.py`

- [ ] **Step 1: Write failing tests for TypedValue-based scoring**

Add to `tests/unit/test_type_compatibility.py`:

```python
from interpreter.typed_value import typed
from interpreter.type_graph import TypeGraph, DEFAULT_TYPE_NODES
from interpreter.type_node import TypeNode


def _default_graph() -> TypeGraph:
    return TypeGraph(DEFAULT_TYPE_NODES)


def _graph_with_classes() -> TypeGraph:
    class_nodes = (
        TypeNode(name="Animal", parents=("Any",)),
        TypeNode(name="Dog", parents=("Animal",)),
        TypeNode(name="Cat", parents=("Animal",)),
    )
    return TypeGraph(DEFAULT_TYPE_NODES + class_nodes)


class TestDefaultTypeCompatibilityTypedValue:
    """Tests using TypedValue args and TypeGraph injection."""

    def setup_method(self):
        self.compat = DefaultTypeCompatibility(_default_graph())

    # -- Exact matches (score 2) --

    def test_int_matches_int(self):
        assert self.compat.score(typed(42, scalar(TypeName.INT)), scalar(TypeName.INT)) == 2

    def test_float_matches_float(self):
        assert self.compat.score(typed(3.14, scalar(TypeName.FLOAT)), scalar(TypeName.FLOAT)) == 2

    def test_string_matches_string(self):
        assert self.compat.score(typed("hello", scalar(TypeName.STRING)), scalar(TypeName.STRING)) == 2

    def test_bool_matches_bool(self):
        assert self.compat.score(typed(True, scalar(TypeName.BOOL)), scalar(TypeName.BOOL)) == 2

    # -- Coercion pairs (score 1) --

    def test_int_compatible_with_float(self):
        assert self.compat.score(typed(42, scalar(TypeName.INT)), scalar(TypeName.FLOAT)) == 1

    def test_float_compatible_with_int(self):
        assert self.compat.score(typed(3.14, scalar(TypeName.FLOAT)), scalar(TypeName.INT)) == 1

    def test_bool_compatible_with_int(self):
        assert self.compat.score(typed(True, scalar(TypeName.BOOL)), scalar(TypeName.INT)) == 1

    # -- Neutral (score 0) --

    def test_unknown_arg_type_is_neutral(self):
        assert self.compat.score(typed("obj_0", UNKNOWN), scalar(TypeName.STRING)) == 0

    def test_unknown_declared_type_is_neutral(self):
        assert self.compat.score(typed(42, scalar(TypeName.INT)), UNKNOWN) == 0

    def test_none_with_unknown_type_is_neutral(self):
        assert self.compat.score(typed(None, UNKNOWN), scalar(TypeName.INT)) == 0

    # -- Mismatches (score -1) --

    def test_string_mismatches_int(self):
        assert self.compat.score(typed("hello", scalar(TypeName.STRING)), scalar(TypeName.INT)) == -1

    def test_int_mismatches_string(self):
        assert self.compat.score(typed(42, scalar(TypeName.INT)), scalar(TypeName.STRING)) == -1

    def test_float_mismatches_string(self):
        assert self.compat.score(typed(3.14, scalar(TypeName.FLOAT)), scalar(TypeName.STRING)) == -1

    def test_list_with_unknown_type_is_neutral(self):
        assert self.compat.score(typed([1, 2], UNKNOWN), scalar(TypeName.ARRAY)) == 0


class TestSubtypeScoring:
    """Tests for subtype-aware scoring with class hierarchies."""

    def setup_method(self):
        self.compat = DefaultTypeCompatibility(_graph_with_classes())

    def test_exact_class_match(self):
        assert self.compat.score(typed("obj_0", scalar("Dog")), scalar("Dog")) == 2

    def test_subtype_match(self):
        assert self.compat.score(typed("obj_0", scalar("Dog")), scalar("Animal")) == 1

    def test_transitive_subtype(self):
        assert self.compat.score(typed("obj_0", scalar("Dog")), scalar("Any")) == 1

    def test_unrelated_class_mismatch(self):
        assert self.compat.score(typed("obj_0", scalar("Dog")), scalar("Cat")) == -1

    def test_sibling_classes_mismatch(self):
        assert self.compat.score(typed("obj_0", scalar("Cat")), scalar("Dog")) == -1

    def test_heap_address_with_class_type_not_confused_with_string(self):
        """obj_0 is a heap address string, but typed as Dog — should not match String."""
        assert self.compat.score(typed("obj_0", scalar("Dog")), scalar(TypeName.STRING)) == -1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_type_compatibility.py::TestDefaultTypeCompatibilityTypedValue -v`
Expected: FAIL — `DefaultTypeCompatibility()` takes no arguments

- [ ] **Step 3: Implement DefaultTypeCompatibility changes**

Replace the body of `interpreter/type_compatibility.py`:

```python
"""TypeCompatibility — scores how well a runtime arg matches a declared parameter type."""

from __future__ import annotations

import logging
from typing import Protocol

from interpreter.constants import TypeName
from interpreter.type_expr import ScalarType, TypeExpr, UnknownType
from interpreter.type_graph import TypeGraph
from interpreter.typed_value import TypedValue

logger = logging.getLogger(__name__)

# Pairs where coercion is valid (source_type, target_type)
_COMPATIBLE_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        (TypeName.INT, TypeName.FLOAT),
        (TypeName.FLOAT, TypeName.INT),
        (TypeName.BOOL, TypeName.INT),
        (TypeName.BOOL, TypeName.FLOAT),
    }
)


class TypeCompatibility(Protocol):
    """Scores how well a runtime argument matches a declared parameter type."""

    def score(self, arg: TypedValue, declared_type: TypeExpr) -> int:
        """Return compatibility score: 2=exact, 1=compatible, 0=neutral, -1=mismatch."""
        ...


class DefaultTypeCompatibility:
    """Default scoring: exact=2, coercion/subtype=1, neutral=0, mismatch=-1.

    Uses _COMPATIBLE_PAIRS for primitive coercion (Int↔Float, Bool→Int)
    and TypeGraph.is_subtype_expr() for class hierarchy subtyping (Dog→Animal).
    """

    def __init__(self, type_graph: TypeGraph) -> None:
        self._type_graph = type_graph

    def score(self, arg: TypedValue, declared_type: TypeExpr) -> int:
        if isinstance(declared_type, UnknownType):
            return 0

        arg_type = arg.type
        if isinstance(arg_type, UnknownType):
            return 0

        if not isinstance(declared_type, ScalarType):
            return 0

        # Exact match
        if isinstance(arg_type, ScalarType) and arg_type.name == declared_type.name:
            return 2

        # Coercion match (Int↔Float, Bool→Int, Bool→Float)
        if isinstance(arg_type, ScalarType) and (arg_type.name, declared_type.name) in _COMPATIBLE_PAIRS:
            return 1

        # Subtype match (Dog → Animal, etc.)
        if self._type_graph.is_subtype_expr(arg_type, declared_type):
            return 1

        return -1
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_type_compatibility.py::TestDefaultTypeCompatibilityTypedValue tests/unit/test_type_compatibility.py::TestSubtypeScoring -v`
Expected: PASS

- [ ] **Step 5: Remove old test class and run full test file**

Delete the old `TestDefaultTypeCompatibility` class from `tests/unit/test_type_compatibility.py` (it passes raw values, which no longer matches the interface).

Run: `poetry run python -m pytest tests/unit/test_type_compatibility.py -v`
Expected: PASS — only the new TypedValue-based tests remain

- [ ] **Step 6: Commit**

```bash
git add interpreter/type_compatibility.py tests/unit/test_type_compatibility.py
git commit -m "feat: migrate DefaultTypeCompatibility to TypedValue args + TypeGraph subtype scoring"
```

---

### Task 2: Migrate resolver chain + tests to TypedValue (atomic)

All interface changes and test updates are done together in a single commit to avoid a test breakage window. No intermediate commits.

**Files:**
- Modify: `interpreter/resolution_strategy.py`
- Modify: `interpreter/overload_resolver.py`
- Modify: `interpreter/ambiguity_handler.py`
- Modify: `tests/unit/test_overload_resolver.py`

- [ ] **Step 1: Update ResolutionStrategy signatures**

In `interpreter/resolution_strategy.py`:

1. Replace `from typing import Any, Protocol` with `from typing import Protocol`
2. Add `from interpreter.typed_value import TypedValue`
3. Change all `args: list[Any]` → `args: list[TypedValue]` in: `ResolutionStrategy.rank()`, `ArityThenTypeStrategy.rank()`, `ArityThenTypeStrategy._arity_distance()`, `ArityThenTypeStrategy._type_score()`

No logic changes — `_type_score` passes each `arg` (now a `TypedValue`) to `self._type_compatibility.score(arg, param_type)`, which already expects `TypedValue` after Task 1. `_arity_distance` uses `len(args)` which works unchanged.

- [ ] **Step 2: Update OverloadResolver and NullOverloadResolver signatures**

In `interpreter/overload_resolver.py`:

1. Replace `from typing import Any` with nothing (remove the import)
2. Add `from interpreter.typed_value import TypedValue`
3. Change `OverloadResolver.resolve()` signature: `args: list[Any]` → `args: list[TypedValue]`
4. Change `NullOverloadResolver.resolve()` signature: `args: list[Any]` → `args: list[TypedValue]`

- [ ] **Step 3: Update AmbiguityHandler signatures and diagnostics**

In `interpreter/ambiguity_handler.py`:

1. Replace `from typing import Any, Protocol` with `from typing import Protocol`
2. Replace `from interpreter.vm import runtime_type_name` with `from interpreter.typed_value import TypedValue`
3. Change all `args: list[Any]` → `args: list[TypedValue]` in: `AmbiguityHandler.handle()`, `FallbackFirstWithWarning.handle()`, `StrictAmbiguityHandler.handle()`
4. In `FallbackFirstWithWarning.handle()`, replace:
   `arg_types = [runtime_type_name(a) or type(a).__name__ for a in args]`
   with:
   `arg_types = [str(a.type) for a in args]`
5. In `StrictAmbiguityHandler.handle()`, same replacement.

- [ ] **Step 4: Update test_overload_resolver.py**

In `tests/unit/test_overload_resolver.py`:

Add imports (keep existing imports):
```python
from interpreter.type_graph import TypeGraph, DEFAULT_TYPE_NODES
from interpreter.type_node import TypeNode
from interpreter.typed_value import typed
```

Replace `_make_resolver`:
```python
def _make_resolver(strict: bool = False) -> OverloadResolver:
    type_graph = TypeGraph(DEFAULT_TYPE_NODES)
    compat = DefaultTypeCompatibility(type_graph)
    strategy = ArityThenTypeStrategy(compat)
    handler = StrictAmbiguityHandler() if strict else FallbackFirstWithWarning()
    return OverloadResolver(strategy, handler)
```

Replace raw values with `typed()` calls throughout `TestOverloadResolver` and `TestNullOverloadResolver`:

| Before | After |
|--------|-------|
| `[42]` | `[typed(42, scalar(TypeName.INT))]` |
| `["hello"]` | `[typed("hello", scalar(TypeName.STRING))]` |
| `[42, "hello"]` | `[typed(42, scalar(TypeName.INT)), typed("hello", scalar(TypeName.STRING))]` |
| `[]` | `[]` |

Apply to all tests in both classes.

- [ ] **Step 5: Add subtype-aware resolution tests**

Add to `tests/unit/test_overload_resolver.py`:

```python
def _make_resolver_with_classes(strict: bool = False) -> OverloadResolver:
    class_nodes = (
        TypeNode(name="Animal", parents=("Any",)),
        TypeNode(name="Dog", parents=("Animal",)),
        TypeNode(name="Cat", parents=("Animal",)),
    )
    type_graph = TypeGraph(DEFAULT_TYPE_NODES + class_nodes)
    compat = DefaultTypeCompatibility(type_graph)
    strategy = ArityThenTypeStrategy(compat)
    handler = StrictAmbiguityHandler() if strict else FallbackFirstWithWarning()
    return OverloadResolver(strategy, handler)


class TestSubtypeOverloadResolution:
    def test_picks_exact_class_over_parent(self):
        """foo(Dog) should beat foo(Animal) when passing a Dog."""
        resolver = _make_resolver_with_classes()
        candidates = [_sig("Animal"), _sig("Dog")]
        assert resolver.resolve(candidates, [typed("obj_0", scalar("Dog"))]) == 1

    def test_picks_parent_when_no_exact(self):
        """foo(Animal) should match when passing a Dog and no foo(Dog) exists."""
        resolver = _make_resolver_with_classes()
        candidates = [_sig(TypeName.STRING), _sig("Animal")]
        assert resolver.resolve(candidates, [typed("obj_0", scalar("Dog"))]) == 1

    def test_sibling_classes_are_ambiguous_with_fallback(self):
        """foo(Dog) and foo(Cat) with a Dog arg — Dog matches exactly, Cat mismatches."""
        resolver = _make_resolver_with_classes()
        candidates = [_sig("Cat"), _sig("Dog")]
        assert resolver.resolve(candidates, [typed("obj_0", scalar("Dog"))]) == 1
```

- [ ] **Step 6: Run all overload resolver tests**

Run: `poetry run python -m pytest tests/unit/test_overload_resolver.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add interpreter/resolution_strategy.py interpreter/overload_resolver.py interpreter/ambiguity_handler.py tests/unit/test_overload_resolver.py
git commit -m "feat: migrate resolver chain to list[TypedValue], add subtype resolution tests"
```

---

## Chunk 2: Executor Call Sites + run.py Wiring + Integration Tests

### Task 4: Wire TypeGraph in run.py + update executor call sites (atomic)

Both changes must be committed together — after `run.py` constructs a resolver expecting `TypedValue`, the executor call sites must pass `TypedValue` or tests through `run()` will break.

**Files:**
- Modify: `interpreter/run.py:602-625`
- Modify: `interpreter/executor.py:1004,1294,1314`

- [ ] **Step 1: Update run.py — build TypeGraph and inject**

Add imports at the top of `interpreter/run.py`:
```python
from interpreter.type_graph import TypeGraph, DEFAULT_TYPE_NODES
from interpreter.type_node import TypeNode
```

Replace lines 622-625 (the `overload_resolver` construction) with:

```python
    class_nodes = tuple(
        TypeNode(name=cls, parents=tuple(parents))
        for cls, parents in registry.class_parents.items()
    )
    type_graph = TypeGraph(DEFAULT_TYPE_NODES + class_nodes)
    overload_resolver = OverloadResolver(
        ArityThenTypeStrategy(DefaultTypeCompatibility(type_graph)),
        FallbackFirstWithWarning(),
    )
```

- [ ] **Step 2: Update _handle_call_method (executor.py line ~1294)**

Change:
```python
winner = overload_resolver.resolve(sigs, [a.value for a in args])
```
to:
```python
winner = overload_resolver.resolve(sigs, args)
```

- [ ] **Step 3: Update parent chain walk (executor.py line ~1314)**

Change:
```python
winner = overload_resolver.resolve(parent_sigs, [a.value for a in args])
```
to:
```python
winner = overload_resolver.resolve(parent_sigs, args)
```

- [ ] **Step 4: Update _try_class_constructor_call (executor.py line ~1004)**

Change:
```python
winner = overload_resolver.resolve(init_sigs, [a.value for a in args])
```
to:
```python
winner = overload_resolver.resolve(init_sigs, args)
```

**Note:** `call_resolver.resolve_method()` (lines ~1281, ~1322) is NOT changed — `UnresolvedCallResolver` operates on raw values and is out of scope.

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass (11,274+)

- [ ] **Step 6: Commit**

```bash
git add interpreter/run.py interpreter/executor.py
git commit -m "feat: build TypeGraph from registry, pass TypedValue args to overload resolver"
```

---

### Task 5: Integration tests — Java overload resolution

**Files:**
- Create: `tests/integration/test_overload_resolution.py`

- [ ] **Step 1: Write integration test**

```python
"""Integration tests for overload resolution with class hierarchy."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_java(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.JAVA, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestJavaOverloadResolution:
    def test_overload_picks_matching_arity(self):
        """Overloaded methods with different arities resolve correctly."""
        src = """
        class Calc {
            int add(int a) { return a; }
            int add(int a, int b) { return a + b; }
        }
        class Main {
            public static void main(String[] args) {
                Calc c = new Calc();
                int x = c.add(5);
                int y = c.add(3, 4);
            }
        }
        """
        vars_ = _run_java(src, max_steps=1000)
        assert vars_["x"] == 5
        assert vars_["y"] == 7

    def test_overload_picks_matching_type(self):
        """Overloaded methods with different param types resolve correctly."""
        src = """
        class Formatter {
            String format(int x) { return "int:" + x; }
            String format(String x) { return "str:" + x; }
        }
        class Main {
            public static void main(String[] args) {
                Formatter f = new Formatter();
                String a = f.format(42);
                String b = f.format("hello");
            }
        }
        """
        vars_ = _run_java(src, max_steps=1000)
        assert vars_["a"] == "int:42"
        assert vars_["b"] == "str:hello"

    def test_overload_picks_subclass_over_parent(self):
        """Overloaded methods with class hierarchy resolve to most specific."""
        src = """
        class Animal {}
        class Dog extends Animal {}
        class Kennel {
            String accept(Animal a) { return "animal"; }
            String accept(Dog d) { return "dog"; }
        }
        class Main {
            public static void main(String[] args) {
                Dog d = new Dog();
                Kennel k = new Kennel();
                String result = k.accept(d);
            }
        }
        """
        vars_ = _run_java(src, max_steps=1000)
        assert vars_["result"] == "dog"
```

- [ ] **Step 2: Run integration test**

Run: `poetry run python -m pytest tests/integration/test_overload_resolution.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 4: Run Black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_overload_resolution.py
git commit -m "feat: add integration tests for Java overload resolution"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass, no regressions

- [ ] **Step 2: Run Black on entire codebase**

Run: `poetry run python -m black .`

- [ ] **Step 3: Verify test count hasn't regressed**

Previous count: 11,274+. New tests added: ~20 unit + ~2 integration. Expected total: ~11,296+.
