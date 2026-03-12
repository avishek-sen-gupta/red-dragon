# Executor Overload Resolution Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the VM executor to pick the correct method overload at call time based on arity and argument types.

**Architecture:** Three injectable protocol-based strategies (TypeCompatibility, ResolutionStrategy, AmbiguityHandler) composed by an OverloadResolver. The resolver is threaded through the executor dispatch chain and called unconditionally at every method/constructor dispatch. A null-object `NullOverloadResolver` (always returns 0) serves as the default when no resolver is injected.

**Tech Stack:** Python 3.13+, Protocol typing, pytest

**Spec:** `docs/superpowers/specs/2026-03-12-executor-overload-resolution-design.md`

---

## Chunk 1: Core protocols and implementations

### Task 0: Make `_runtime_type_name` public

**Files:**
- Modify: `interpreter/vm.py:222-229` (rename function)
- Modify: all files that import `_runtime_type_name` from `interpreter.vm`

The function `_runtime_type_name` in `vm.py` is private (leading underscore) but will be needed by `type_compatibility.py` and `ambiguity_handler.py`. Rename it to `runtime_type_name` to make it a public API.

- [ ] **Step 1: Rename `_runtime_type_name` to `runtime_type_name` in vm.py**

In `interpreter/vm.py`, rename the function at line 222 and update all call sites within the file. Also update `_PYTHON_TYPE_TO_TYPE_NAME` references if needed. Use find-and-replace across the file.

- [ ] **Step 2: Update all imports**

Search for `_runtime_type_name` across the codebase and update imports:
- `interpreter/vm.py` — internal call sites
- `tests/unit/test_resolve_typed_reg.py` — imports `_runtime_type_name`
- Any other files found via `grep -r "_runtime_type_name"`

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest -x -q`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "refactor: make runtime_type_name public API in vm.py"
```

---

### Task 1: TypeCompatibility protocol and DefaultTypeCompatibility

**Files:**
- Create: `interpreter/type_compatibility.py`
- Test: `tests/unit/test_type_compatibility.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_type_compatibility.py`:

```python
"""Unit tests for TypeCompatibility — runtime arg vs declared type scoring."""

from interpreter.constants import TypeName
from interpreter.type_compatibility import DefaultTypeCompatibility
from interpreter.type_expr import scalar, UNKNOWN


class TestDefaultTypeCompatibility:
    def setup_method(self):
        self.compat = DefaultTypeCompatibility()

    # -- Exact matches (score 2) --

    def test_int_matches_int(self):
        assert self.compat.score(42, scalar(TypeName.INT)) == 2

    def test_float_matches_float(self):
        assert self.compat.score(3.14, scalar(TypeName.FLOAT)) == 2

    def test_string_matches_string(self):
        assert self.compat.score("hello", scalar(TypeName.STRING)) == 2

    def test_bool_matches_bool(self):
        assert self.compat.score(True, scalar(TypeName.BOOL)) == 2

    # -- Compatible pairs (score 1) --

    def test_int_compatible_with_float(self):
        assert self.compat.score(42, scalar(TypeName.FLOAT)) == 1

    def test_float_compatible_with_int(self):
        assert self.compat.score(3.14, scalar(TypeName.INT)) == 1

    def test_bool_compatible_with_int(self):
        assert self.compat.score(True, scalar(TypeName.INT)) == 1

    # -- Neutral (score 0) --

    def test_heap_address_is_neutral(self):
        assert self.compat.score("obj_Dog_0", scalar(TypeName.STRING)) == 0

    def test_none_is_neutral(self):
        assert self.compat.score(None, scalar(TypeName.INT)) == 0

    def test_unknown_declared_type_is_neutral(self):
        assert self.compat.score(42, UNKNOWN) == 0

    def test_list_runtime_type_is_neutral(self):
        assert self.compat.score([1, 2], scalar(TypeName.ARRAY)) == 0

    # -- Mismatches (score -1) --

    def test_string_mismatches_int(self):
        assert self.compat.score("hello", scalar(TypeName.INT)) == -1

    def test_int_mismatches_string(self):
        assert self.compat.score(42, scalar(TypeName.STRING)) == -1

    def test_float_mismatches_string(self):
        assert self.compat.score(3.14, scalar(TypeName.STRING)) == -1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_type_compatibility.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.type_compatibility'`

- [ ] **Step 3: Write the implementation**

Create `interpreter/type_compatibility.py`:

```python
"""TypeCompatibility — scores how well a runtime arg matches a declared parameter type."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from interpreter.constants import TypeName
from interpreter.type_expr import ScalarType, TypeExpr, UnknownType
from interpreter.vm import runtime_type_name

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

    def score(self, arg: Any, declared_type: TypeExpr) -> int:
        """Return compatibility score: 2=exact, 1=compatible, 0=neutral, -1=mismatch."""
        ...


class DefaultTypeCompatibility:
    """Default scoring: exact=2, compatible=1, neutral=0, mismatch=-1.

    Heap addresses (strings starting with "obj_") are scored as neutral
    to avoid false matches with String-typed overloads.
    """

    def score(self, arg: Any, declared_type: TypeExpr) -> int:
        if isinstance(declared_type, UnknownType):
            return 0

        rt = runtime_type_name(arg)

        # Unknown runtime type (symbolic, list, dict, None, etc.)
        if not rt:
            return 0

        # Heap addresses are strings but should not match String params
        if rt == TypeName.STRING and isinstance(arg, str) and arg.startswith("obj_"):
            return 0

        if not isinstance(declared_type, ScalarType):
            return 0

        declared_name = declared_type.name

        if rt == declared_name:
            return 2

        if (rt, declared_name) in _COMPATIBLE_PAIRS:
            return 1

        return -1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_type_compatibility.py -v`
Expected: All 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/type_compatibility.py tests/unit/test_type_compatibility.py
git commit -m "feat: add TypeCompatibility protocol and DefaultTypeCompatibility"
```

---

### Task 2: AmbiguityHandler protocol, FallbackFirstWithWarning, and StrictAmbiguityHandler

**Files:**
- Create: `interpreter/ambiguity_handler.py`
- Test: `tests/unit/test_ambiguity_handler.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_ambiguity_handler.py`:

```python
"""Unit tests for AmbiguityHandler implementations."""

import logging

import pytest

from interpreter.ambiguity_handler import (
    AmbiguousOverloadError,
    FallbackFirstWithWarning,
    StrictAmbiguityHandler,
)
from interpreter.function_signature import FunctionSignature
from interpreter.type_expr import UNKNOWN


def _sig(n_params: int) -> FunctionSignature:
    """Helper: create a FunctionSignature with n_params UNKNOWN-typed params."""
    return FunctionSignature(
        params=tuple((f"p{i}", UNKNOWN) for i in range(n_params)),
        return_type=UNKNOWN,
    )


class TestFallbackFirstWithWarning:
    def test_returns_first_ranked(self):
        handler = FallbackFirstWithWarning()
        candidates = [_sig(1), _sig(2), _sig(3)]
        result = handler.handle(candidates, [42], [2, 0, 1])
        assert result == 2

    def test_logs_warning(self, caplog):
        handler = FallbackFirstWithWarning()
        candidates = [_sig(1), _sig(2)]
        with caplog.at_level(logging.WARNING):
            handler.handle(candidates, [42, "hello"], [0, 1])
        assert "ambiguous" in caplog.text.lower()

    def test_single_ranked_returns_it(self):
        handler = FallbackFirstWithWarning()
        candidates = [_sig(1)]
        result = handler.handle(candidates, [42], [0])
        assert result == 0


class TestStrictAmbiguityHandler:
    def test_raises_on_ambiguity(self):
        handler = StrictAmbiguityHandler()
        candidates = [_sig(1), _sig(2)]
        with pytest.raises(AmbiguousOverloadError):
            handler.handle(candidates, [42], [0, 1])

    def test_error_contains_candidate_count(self):
        handler = StrictAmbiguityHandler()
        candidates = [_sig(1), _sig(2), _sig(3)]
        with pytest.raises(AmbiguousOverloadError, match="3"):
            handler.handle(candidates, [42], [0, 1, 2])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_ambiguity_handler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.ambiguity_handler'`

- [ ] **Step 3: Write the implementation**

Create `interpreter/ambiguity_handler.py`:

```python
"""AmbiguityHandler — decides what to do when overload resolution is inconclusive."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from interpreter.function_signature import FunctionSignature
from interpreter.vm import runtime_type_name

logger = logging.getLogger(__name__)


class AmbiguousOverloadError(Exception):
    """Raised by StrictAmbiguityHandler when resolution is ambiguous."""


class AmbiguityHandler(Protocol):
    """Pick winner from equally-ranked overload candidates."""

    def handle(
        self,
        candidates: list[FunctionSignature],
        args: list[Any],
        ranked: list[int],
    ) -> int:
        """Return index into candidates for the winning overload."""
        ...


class FallbackFirstWithWarning:
    """Default handler: pick first ranked candidate and log a warning."""

    def handle(
        self,
        candidates: list[FunctionSignature],
        args: list[Any],
        ranked: list[int],
    ) -> int:
        arg_types = [runtime_type_name(a) or type(a).__name__ for a in args]
        logger.warning(
            "Ambiguous overload resolution: %d candidates for args %s, picking index %d",
            len(candidates),
            arg_types,
            ranked[0],
        )
        return ranked[0]


class StrictAmbiguityHandler:
    """Testing handler: raise on ambiguity to verify resolution is disambiguating."""

    def handle(
        self,
        candidates: list[FunctionSignature],
        args: list[Any],
        ranked: list[int],
    ) -> int:
        arg_types = [runtime_type_name(a) or type(a).__name__ for a in args]
        raise AmbiguousOverloadError(
            f"Ambiguous overload: {len(candidates)} candidates for args {arg_types}"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_ambiguity_handler.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/ambiguity_handler.py tests/unit/test_ambiguity_handler.py
git commit -m "feat: add AmbiguityHandler protocol with fallback and strict implementations"
```

---

### Task 3: ResolutionStrategy protocol and ArityThenTypeStrategy

**Files:**
- Create: `interpreter/resolution_strategy.py`
- Test: `tests/unit/test_resolution_strategy.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_resolution_strategy.py`:

```python
"""Unit tests for ResolutionStrategy — candidate ranking by arity then type."""

from interpreter.constants import TypeName
from interpreter.function_kind import FunctionKind
from interpreter.function_signature import FunctionSignature
from interpreter.resolution_strategy import ArityThenTypeStrategy
from interpreter.type_compatibility import DefaultTypeCompatibility
from interpreter.type_expr import scalar, UNKNOWN


def _sig(*param_types: str, kind: FunctionKind = FunctionKind.UNBOUND) -> FunctionSignature:
    """Helper: create FunctionSignature from TypeName strings."""
    return FunctionSignature(
        params=tuple(
            (f"p{i}", scalar(t) if t else UNKNOWN) for i, t in enumerate(param_types)
        ),
        return_type=UNKNOWN,
        kind=kind,
    )


def _instance_sig(*param_types: str) -> FunctionSignature:
    """Helper: instance method with 'this' as first param + given params."""
    params = [("this", UNKNOWN)] + [
        (f"p{i}", scalar(t) if t else UNKNOWN) for i, t in enumerate(param_types)
    ]
    return FunctionSignature(
        params=tuple(params),
        return_type=UNKNOWN,
        kind=FunctionKind.INSTANCE,
    )


class TestArityThenTypeStrategy:
    def setup_method(self):
        self.strategy = ArityThenTypeStrategy(DefaultTypeCompatibility())

    # -- Arity-based resolution --

    def test_single_candidate_returns_it(self):
        candidates = [_sig(TypeName.INT)]
        assert self.strategy.rank(candidates, [42]) == [0]

    def test_empty_candidates_returns_empty(self):
        assert self.strategy.rank([], [42]) == []

    def test_arity_match_preferred(self):
        candidates = [_sig(TypeName.INT, TypeName.INT), _sig(TypeName.INT)]
        ranked = self.strategy.rank(candidates, [42])
        assert ranked[0] == 1

    def test_two_args_picks_two_param_overload(self):
        candidates = [_sig(TypeName.INT), _sig(TypeName.INT, TypeName.STRING)]
        ranked = self.strategy.rank(candidates, [42, "hello"])
        assert ranked[0] == 1

    def test_zero_args_picks_nullary(self):
        candidates = [_sig(TypeName.INT), _sig()]
        ranked = self.strategy.rank(candidates, [])
        assert ranked[0] == 1

    def test_fewer_args_than_params_scores_by_available(self):
        """2 args against a 3-param candidate — only first 2 positions scored."""
        candidates = [
            _sig(TypeName.INT, TypeName.STRING, TypeName.FLOAT),
            _sig(TypeName.INT, TypeName.STRING),
        ]
        ranked = self.strategy.rank(candidates, [42, "hello"])
        assert ranked[0] == 1  # exact arity match wins

    # -- Type-based tiebreaking --

    def test_same_arity_exact_type_wins(self):
        candidates = [_sig(TypeName.STRING), _sig(TypeName.INT)]
        ranked = self.strategy.rank(candidates, [42])
        assert ranked[0] == 1

    def test_same_arity_compatible_vs_mismatch(self):
        candidates = [_sig(TypeName.STRING), _sig(TypeName.FLOAT)]
        ranked = self.strategy.rank(candidates, [42])
        assert ranked[0] == 1

    def test_same_arity_both_exact_preserves_order(self):
        candidates = [_sig(TypeName.INT), _sig(TypeName.INT)]
        ranked = self.strategy.rank(candidates, [42])
        assert ranked[0] == 0

    # -- Instance methods use callable_params (excludes this) --

    def test_instance_method_arity_excludes_this(self):
        candidates = [_instance_sig(TypeName.INT, TypeName.INT), _instance_sig(TypeName.INT)]
        ranked = self.strategy.rank(candidates, [42])
        assert ranked[0] == 1

    # -- Multi-argument type scoring --

    def test_multi_arg_type_score_sum(self):
        candidates = [_sig(TypeName.STRING, TypeName.INT), _sig(TypeName.INT, TypeName.STRING)]
        ranked = self.strategy.rank(candidates, [42, "hello"])
        assert ranked[0] == 1

    # -- Unknown types are neutral --

    def test_unknown_args_dont_penalize(self):
        candidates = [_sig(TypeName.INT), _sig(TypeName.STRING)]
        ranked = self.strategy.rank(candidates, ["obj_Dog_0"])
        assert ranked[0] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_resolution_strategy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.resolution_strategy'`

- [ ] **Step 3: Write the implementation**

Create `interpreter/resolution_strategy.py`:

```python
"""ResolutionStrategy — ranks overload candidates by arity then type compatibility."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from interpreter.function_signature import FunctionSignature
from interpreter.type_compatibility import TypeCompatibility

logger = logging.getLogger(__name__)


class ResolutionStrategy(Protocol):
    """Ranks overload candidates from best to worst match."""

    def rank(
        self,
        candidates: list[FunctionSignature],
        args: list[Any],
    ) -> list[int]:
        """Return candidate indices sorted best-to-worst."""
        ...


class ArityThenTypeStrategy:
    """Default strategy: filter by arity distance, then rank by type score."""

    def __init__(self, type_compatibility: TypeCompatibility) -> None:
        self._type_compatibility = type_compatibility

    def rank(
        self,
        candidates: list[FunctionSignature],
        args: list[Any],
    ) -> list[int]:
        if not candidates:
            return []

        # Score each candidate: (arity_distance, -type_score, original_index)
        scored = [
            (self._arity_distance(sig, args), -self._type_score(sig, args), i)
            for i, sig in enumerate(candidates)
        ]
        scored.sort()
        return [i for _, _, i in scored]

    def _arity_distance(self, sig: FunctionSignature, args: list[Any]) -> int:
        return abs(len(sig.callable_params) - len(args))

    def _type_score(self, sig: FunctionSignature, args: list[Any]) -> int:
        params = sig.callable_params
        return sum(
            self._type_compatibility.score(arg, param_type)
            for arg, (_, param_type) in zip(args, params)
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_resolution_strategy.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/resolution_strategy.py tests/unit/test_resolution_strategy.py
git commit -m "feat: add ResolutionStrategy protocol and ArityThenTypeStrategy"
```

---

### Task 4: OverloadResolver compositor with NullOverloadResolver

**Files:**
- Create: `interpreter/overload_resolver.py`
- Test: `tests/unit/test_overload_resolver.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_overload_resolver.py`:

```python
"""Unit tests for OverloadResolver — compositor of strategy + ambiguity handler."""

import pytest

from interpreter.ambiguity_handler import (
    AmbiguousOverloadError,
    FallbackFirstWithWarning,
    StrictAmbiguityHandler,
)
from interpreter.constants import TypeName
from interpreter.function_signature import FunctionSignature
from interpreter.overload_resolver import NullOverloadResolver, OverloadResolver
from interpreter.resolution_strategy import ArityThenTypeStrategy
from interpreter.type_compatibility import DefaultTypeCompatibility
from interpreter.type_expr import scalar, UNKNOWN


def _sig(*param_types: str) -> FunctionSignature:
    return FunctionSignature(
        params=tuple(
            (f"p{i}", scalar(t) if t else UNKNOWN) for i, t in enumerate(param_types)
        ),
        return_type=UNKNOWN,
    )


def _make_resolver(strict: bool = False) -> OverloadResolver:
    compat = DefaultTypeCompatibility()
    strategy = ArityThenTypeStrategy(compat)
    handler = StrictAmbiguityHandler() if strict else FallbackFirstWithWarning()
    return OverloadResolver(strategy, handler)


class TestOverloadResolver:
    # -- Edge cases --

    def test_empty_candidates_returns_zero(self):
        resolver = _make_resolver()
        assert resolver.resolve([], [42]) == 0

    def test_single_candidate_returns_zero(self):
        resolver = _make_resolver()
        assert resolver.resolve([_sig(TypeName.INT)], [42]) == 0

    # -- Arity resolution --

    def test_picks_matching_arity(self):
        resolver = _make_resolver()
        candidates = [_sig(TypeName.INT, TypeName.INT), _sig(TypeName.INT)]
        assert resolver.resolve(candidates, [42]) == 1

    # -- Type resolution --

    def test_picks_matching_type(self):
        resolver = _make_resolver()
        candidates = [_sig(TypeName.STRING), _sig(TypeName.INT)]
        assert resolver.resolve(candidates, [42]) == 1

    # -- Strict handler raises on genuine ambiguity --

    def test_strict_raises_on_identical_signatures(self):
        resolver = _make_resolver(strict=True)
        candidates = [_sig(TypeName.INT), _sig(TypeName.INT)]
        with pytest.raises(AmbiguousOverloadError):
            resolver.resolve(candidates, [42])

    # -- Fallback handler resolves ambiguity silently --

    def test_fallback_resolves_identical_signatures(self):
        resolver = _make_resolver(strict=False)
        candidates = [_sig(TypeName.INT), _sig(TypeName.INT)]
        result = resolver.resolve(candidates, [42])
        assert result in (0, 1)

    # -- End-to-end: multi-arg disambiguation --

    def test_multi_arg_picks_best_type_match(self):
        resolver = _make_resolver()
        candidates = [_sig(TypeName.STRING, TypeName.INT), _sig(TypeName.INT, TypeName.STRING)]
        assert resolver.resolve(candidates, [42, "hello"]) == 1


class TestNullOverloadResolver:
    def test_always_returns_zero(self):
        resolver = NullOverloadResolver()
        assert resolver.resolve([_sig(TypeName.INT), _sig(TypeName.STRING)], [42]) == 0

    def test_empty_candidates_returns_zero(self):
        resolver = NullOverloadResolver()
        assert resolver.resolve([], []) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_overload_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.overload_resolver'`

- [ ] **Step 3: Write the implementation**

Create `interpreter/overload_resolver.py`:

```python
"""OverloadResolver — composes ResolutionStrategy and AmbiguityHandler."""

from __future__ import annotations

import logging
from typing import Any

from interpreter.ambiguity_handler import AmbiguityHandler
from interpreter.function_signature import FunctionSignature
from interpreter.resolution_strategy import ResolutionStrategy

logger = logging.getLogger(__name__)


class OverloadResolver:
    """Picks the best overload candidate by composing a ranking strategy
    with an ambiguity handler for ties.
    """

    def __init__(
        self,
        strategy: ResolutionStrategy,
        ambiguity_handler: AmbiguityHandler,
    ) -> None:
        self._strategy = strategy
        self._ambiguity_handler = ambiguity_handler

    def resolve(
        self,
        candidates: list[FunctionSignature],
        args: list[Any],
    ) -> int:
        """Return index of winning candidate."""
        if len(candidates) <= 1:
            return 0
        ranked = self._strategy.rank(candidates, args)
        if len(ranked) <= 1:
            return ranked[0]
        return self._ambiguity_handler.handle(candidates, args, ranked)


class NullOverloadResolver(OverloadResolver):
    """Null-object resolver that always returns index 0 (current behavior).

    Used as default parameter value to avoid None checks.
    """

    def __init__(self) -> None:
        pass  # No strategy or handler needed

    def resolve(
        self,
        candidates: list[FunctionSignature],
        args: list[Any],
    ) -> int:
        return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_overload_resolver.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Run all unit tests for the new modules**

Run: `poetry run python -m pytest tests/unit/test_type_compatibility.py tests/unit/test_ambiguity_handler.py tests/unit/test_resolution_strategy.py tests/unit/test_overload_resolver.py -v`
Expected: All 40 tests PASS

- [ ] **Step 6: Commit**

```bash
git add interpreter/overload_resolver.py tests/unit/test_overload_resolver.py
git commit -m "feat: add OverloadResolver compositor with NullOverloadResolver"
```

---

## Chunk 2: Executor integration

### Task 5: Thread OverloadResolver and type_env through executor dispatch chain

**Files:**
- Modify: `interpreter/executor.py:1297-1319` (LocalExecutor.execute signature and dispatch)
- Modify: `interpreter/executor.py:1150-1158` (_handle_call_method signature)
- Modify: `interpreter/executor.py:915-922` (_try_class_constructor_call signature)
- Modify: `interpreter/executor.py:1048-1058` (_handle_call_function signature)
- Modify: `interpreter/executor.py:1322-1344` (_try_execute_locally — NOTE: this function is in executor.py, NOT run.py)
- Modify: `interpreter/run.py:185-204` (execute_cfg signature)
- Modify: `interpreter/run.py:247-255` (execute_cfg call to _try_execute_locally)
- Modify: `interpreter/run.py:324-331` (execute_cfg_traced signature)
- Modify: `interpreter/run.py:386-394` (execute_cfg_traced call to _try_execute_locally)
- Modify: `interpreter/run.py:570-593` (run() function — construct default resolver)

This task only threads the parameters through — no behavioral changes yet. All existing tests must still pass.

The `NullOverloadResolver` is used as default parameter value everywhere, eliminating the need for `None` checks. The `type_env` parameter already has `_EMPTY_TYPE_ENV` as default in `execute_cfg`; use the same pattern for functions that need it.

- [ ] **Step 1: Add imports to executor.py**

Add to the imports section of `interpreter/executor.py`:

```python
from interpreter.overload_resolver import NullOverloadResolver, OverloadResolver
from interpreter.type_environment import TypeEnvironment
from interpreter.type_expr import scalar
```

Also create a module-level default:

```python
_DEFAULT_OVERLOAD_RESOLVER = NullOverloadResolver()
```

- [ ] **Step 2: Update LocalExecutor.execute() signature**

In `interpreter/executor.py`, at line 1297, change the `execute` method to accept two new kwargs:

```python
@classmethod
def execute(
    cls,
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str = "",
    ip: int = 0,
    call_resolver: UnresolvedCallResolver = _DEFAULT_RESOLVER,
    overload_resolver: OverloadResolver = _DEFAULT_OVERLOAD_RESOLVER,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
) -> ExecutionResult:
    handler = cls.DISPATCH.get(inst.opcode)
    if not handler:
        return ExecutionResult.not_handled()
    return handler(
        inst=inst,
        vm=vm,
        cfg=cfg,
        registry=registry,
        current_label=current_label,
        ip=ip,
        call_resolver=call_resolver,
        overload_resolver=overload_resolver,
        type_env=type_env,
    )
```

Note: `_EMPTY_TYPE_ENV` already exists in the executor module (used by `_resolve_typed_reg`). If it's in `run.py` instead, import or duplicate it.

- [ ] **Step 3: Update _handle_call_method signature**

At line 1150, add `overload_resolver` and `type_env` kwargs:

```python
def _handle_call_method(
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
    call_resolver: UnresolvedCallResolver = _DEFAULT_RESOLVER,
    overload_resolver: OverloadResolver = _DEFAULT_OVERLOAD_RESOLVER,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    **kwargs: Any,
) -> ExecutionResult:
```

- [ ] **Step 4: Update _handle_call_function and _try_class_constructor_call signatures**

At `_handle_call_function` (line ~1048):

```python
def _handle_call_function(
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
    call_resolver: UnresolvedCallResolver = _DEFAULT_RESOLVER,
    overload_resolver: OverloadResolver = _DEFAULT_OVERLOAD_RESOLVER,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    **kwargs: Any,
) -> ExecutionResult:
```

Update the call to `_try_class_constructor_call` (line ~1133):

```python
ctor_result = _try_class_constructor_call(
    func_val, args, inst, vm, cfg, registry, current_label,
    overload_resolver=overload_resolver, type_env=type_env,
)
```

At `_try_class_constructor_call` (line 915):

```python
def _try_class_constructor_call(
    func_val: Any,
    args: list[Any],
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
    overload_resolver: OverloadResolver = _DEFAULT_OVERLOAD_RESOLVER,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
) -> ExecutionResult:
```

- [ ] **Step 5: Update _try_execute_locally in executor.py**

In `interpreter/executor.py` (NOT run.py), update `_try_execute_locally` (line 1322):

```python
def _try_execute_locally(
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str = "",
    ip: int = 0,
    call_resolver: UnresolvedCallResolver = _DEFAULT_RESOLVER,
    overload_resolver: OverloadResolver = _DEFAULT_OVERLOAD_RESOLVER,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
) -> ExecutionResult:
    return LocalExecutor.execute(
        inst,
        vm,
        cfg,
        registry,
        current_label,
        ip,
        call_resolver,
        overload_resolver=overload_resolver,
        type_env=type_env,
    )
```

- [ ] **Step 6: Update execute_cfg and execute_cfg_traced in run.py**

Add `overload_resolver` parameter to `execute_cfg` (line 185):

```python
def execute_cfg(
    cfg: CFG,
    entry_point: str,
    registry: FunctionRegistry,
    config: VMConfig = VMConfig(),
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    conversion_rules: TypeConversionRules = _IDENTITY_RULES,
    overload_resolver: OverloadResolver = _DEFAULT_OVERLOAD_RESOLVER,
) -> tuple[VMState, ExecutionStats]:
```

Update the `_try_execute_locally` call site inside `execute_cfg` (~line 247):

```python
result = _try_execute_locally(
    instruction,
    vm,
    cfg=cfg,
    registry=registry,
    current_label=current_label,
    ip=ip,
    call_resolver=call_resolver,
    overload_resolver=overload_resolver,
    type_env=type_env,
)
```

Add the same parameter to `execute_cfg_traced` (line ~324) and forward at its `_try_execute_locally` call site (~line 386).

Import the default in run.py:

```python
from interpreter.overload_resolver import NullOverloadResolver, OverloadResolver
_DEFAULT_OVERLOAD_RESOLVER = NullOverloadResolver()
```

- [ ] **Step 7: Construct default resolver in run()**

In the `run()` function (around line 586), after `type_env` is built:

```python
from interpreter.resolution_strategy import ArityThenTypeStrategy
from interpreter.type_compatibility import DefaultTypeCompatibility
from interpreter.ambiguity_handler import FallbackFirstWithWarning

overload_resolver = OverloadResolver(
    ArityThenTypeStrategy(DefaultTypeCompatibility()),
    FallbackFirstWithWarning(),
)

vm, exec_stats = execute_cfg(
    cfg,
    entry,
    registry,
    vm_config,
    type_env=type_env,
    conversion_rules=conversion_rules,
    overload_resolver=overload_resolver,
)
```

- [ ] **Step 8: Run full test suite to verify no regressions**

Run: `poetry run python -m pytest -x -q`
Expected: All ~11,247 tests PASS (zero behavioral change — NullOverloadResolver returns 0, same as `func_labels[0]`)

- [ ] **Step 9: Commit**

```bash
git add interpreter/executor.py interpreter/run.py
git commit -m "feat: thread OverloadResolver and type_env through executor dispatch chain"
```

---

### Task 6: Use resolver in _handle_call_method

**Files:**
- Modify: `interpreter/executor.py:1193-1204` (method lookup and parent chain walk)

No `if overload_resolver:` guards needed — the `NullOverloadResolver` default handles the no-resolver case by returning 0.

- [ ] **Step 1: Replace `func_labels[0]` with resolver call in direct lookup**

In `_handle_call_method`, replace lines 1193-1195:

```python
# Before:
methods = registry.class_methods[type_hint]
func_labels = methods.get(method_name, [])
func_label = func_labels[0] if func_labels else ""

# After:
methods = registry.class_methods[type_hint]
func_labels = methods.get(method_name, [])
if func_labels:
    sigs = type_env.method_signatures.get(scalar(type_hint), {}).get(method_name, [])
    if len(sigs) != len(func_labels):
        logger.warning("sig/label count mismatch for %s.%s", type_hint, method_name)
        func_label = func_labels[0]
    else:
        winner = overload_resolver.resolve(sigs, args)
        func_label = func_labels[winner]
else:
    func_label = ""
```

- [ ] **Step 2: Replace `parent_labels[0]` with resolver call in parent chain walk**

Replace lines 1197-1204:

```python
# Before:
if not func_label or func_label not in cfg.blocks:
    for parent in registry.class_parents.get(type_hint, []):
        parent_methods = registry.class_methods.get(parent, {})
        parent_labels = parent_methods.get(method_name, [])
        candidate = parent_labels[0] if parent_labels else ""
        if candidate and candidate in cfg.blocks:
            func_label = candidate
            break

# After:
if not func_label or func_label not in cfg.blocks:
    for parent in registry.class_parents.get(type_hint, []):
        parent_methods = registry.class_methods.get(parent, {})
        parent_labels = parent_methods.get(method_name, [])
        if not parent_labels:
            continue
        parent_sigs = type_env.method_signatures.get(scalar(parent), {}).get(method_name, [])
        if len(parent_sigs) != len(parent_labels):
            logger.warning("sig/label count mismatch for %s.%s", parent, method_name)
            candidate = parent_labels[0]
        else:
            winner = overload_resolver.resolve(parent_sigs, args)
            candidate = parent_labels[winner]
        if candidate and candidate in cfg.blocks:
            func_label = candidate
            break
```

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest -x -q`
Expected: All tests PASS (existing code paths use single overloads, so resolver returns 0)

- [ ] **Step 4: Commit**

```bash
git add interpreter/executor.py
git commit -m "feat: use OverloadResolver in _handle_call_method for method and parent chain dispatch"
```

---

### Task 7: Use resolver in _try_class_constructor_call

**Files:**
- Modify: `interpreter/executor.py:929-932` (constructor init_label lookup)

- [ ] **Step 1: Replace `init_labels[0]` with resolver call**

Replace lines 929-932:

```python
# Before:
methods = registry.class_methods.get(class_name, {})
init_labels = methods.get("__init__", [])
init_label = init_labels[0] if init_labels else ""

# After:
methods = registry.class_methods.get(class_name, {})
init_labels = methods.get("__init__", [])
if init_labels:
    init_sigs = type_env.method_signatures.get(scalar(class_name), {}).get("__init__", [])
    if len(init_sigs) != len(init_labels):
        logger.warning("sig/label count mismatch for %s.__init__", class_name)
        init_label = init_labels[0]
    else:
        winner = overload_resolver.resolve(init_sigs, args)
        init_label = init_labels[winner]
else:
    init_label = ""
```

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x -q`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add interpreter/executor.py
git commit -m "feat: use OverloadResolver in _try_class_constructor_call for constructor overloads"
```

---

### Task 8: Format, full test suite, final commit

- [ ] **Step 1: Run Black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x -q`
Expected: All ~11,247 tests PASS

- [ ] **Step 3: Commit formatting if needed**

```bash
git add -u
git commit -m "style: format overload resolution code with Black"
```

---

## Chunk 3: Integration tests

### Task 9: Integration tests with overloaded Java/C# methods

**Files:**
- Create: `tests/integration/test_overload_resolution.py`

These tests exercise the full pipeline: source code -> frontend -> IR -> type inference -> executor with overload resolution.

**Important note on deduplication risk:** Type inference deduplicates identical `FunctionSignature` objects (line 513 in `type_inference.py`), while the registry keeps all labels. If both overloads infer to all-UNKNOWN params, `len(sigs) < len(func_labels)` will trigger the length-mismatch fallback. If integration tests fail for this reason, mark them `@pytest.mark.xfail(reason="type inference deduplicates identical signatures — needs typed parameter propagation")`.

- [ ] **Step 1: Write integration tests**

Create `tests/integration/test_overload_resolution.py`:

```python
"""Integration tests for executor overload resolution through full pipeline.

Tests that when source code defines overloaded methods, the executor picks
the correct overload based on call-site argument arity and types.
"""

from interpreter.run import run


class TestJavaOverloadResolutionByArity:
    """Java methods overloaded by parameter count."""

    def test_nullary_vs_unary_picks_nullary(self):
        source = """
        class Greeter {
            String greet() {
                return "hello";
            }
            String greet(String name) {
                return "hello " + name;
            }
        }
        Greeter g = new Greeter();
        String result = g.greet();
        """
        vm, _ = run(source, lang="java")
        assert vm.current_frame.local_vars.get("result") == "hello"

    def test_nullary_vs_unary_picks_unary(self):
        source = """
        class Greeter {
            String greet() {
                return "hello";
            }
            String greet(String name) {
                return "hello " + name;
            }
        }
        Greeter g = new Greeter();
        String result = g.greet("world");
        """
        vm, _ = run(source, lang="java")
        assert vm.current_frame.local_vars.get("result") == "hello world"


class TestJavaOverloadResolutionByType:
    """Java methods overloaded by parameter type (same arity)."""

    def test_int_vs_string_picks_int(self):
        source = """
        class Printer {
            String show(int x) {
                return "int:" + x;
            }
            String show(String s) {
                return "str:" + s;
            }
        }
        Printer p = new Printer();
        String result = p.show(42);
        """
        vm, _ = run(source, lang="java")
        assert vm.current_frame.local_vars.get("result") == "int:42"

    def test_int_vs_string_picks_string(self):
        source = """
        class Printer {
            String show(int x) {
                return "int:" + x;
            }
            String show(String s) {
                return "str:" + s;
            }
        }
        Printer p = new Printer();
        String result = p.show("hello");
        """
        vm, _ = run(source, lang="java")
        assert vm.current_frame.local_vars.get("result") == "str:hello"


class TestJavaConstructorOverload:
    """Java constructor overloading."""

    def test_constructor_overload_by_arity(self):
        source = """
        class Point {
            int x;
            int y;
            Point() {
                this.x = 0;
                this.y = 0;
            }
            Point(int x, int y) {
                this.x = x;
                this.y = y;
            }
        }
        Point p = new Point(3, 4);
        int px = p.x;
        int py = p.y;
        """
        vm, _ = run(source, lang="java")
        assert vm.current_frame.local_vars.get("px") == 3
        assert vm.current_frame.local_vars.get("py") == 4
```

- [ ] **Step 2: Run integration tests**

Run: `poetry run python -m pytest tests/integration/test_overload_resolution.py -v`
Expected: Tests PASS. If they fail due to signature deduplication, mark as `xfail` with the reason documented above.

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest -x -q`
Expected: All tests PASS

- [ ] **Step 4: Format and commit**

```bash
poetry run python -m black .
git add tests/integration/test_overload_resolution.py
git commit -m "test: add integration tests for executor overload resolution"
```

---

### Task 10: Update README and push

- [ ] **Step 1: Update README to mention overload resolution**

Add a brief mention of overload resolution support in the relevant section of `README.md`.

- [ ] **Step 2: Run Black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 3: Run full test suite one final time**

Run: `poetry run python -m pytest -x -q`
Expected: All tests PASS

- [ ] **Step 4: Commit and push**

```bash
git add -u
git commit -m "docs: update README for overload resolution support"
git push origin main
```
