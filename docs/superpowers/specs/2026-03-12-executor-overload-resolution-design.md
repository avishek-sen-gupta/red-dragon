# Executor Overload Resolution at Call Time

**Date:** 2026-03-12
**Bead:** `red-dragon-gsl.7.3.2`
**Status:** Design approved

## Problem

The executor has zero overload awareness. When dispatching a method call, `class_methods[type_hint][method_name]` returns a `list[str]` of func_labels, but the executor always takes `func_labels[0]`. For languages with method overloading (Java, C#, C++, Kotlin, Scala), this means the wrong overload can be called when multiple definitions exist with different arities or parameter types.

The `TypeEnvironment` already tracks `list[FunctionSignature]` per method (with arity, declared types, and `FunctionKind`), but the executor never consults it.

## Design

### Architecture

A standalone `OverloadResolver` compositor that composes three injectable strategies:

1. **`TypeCompatibility`** — scores how well a runtime argument matches a declared parameter type
2. **`ResolutionStrategy`** — ranks candidate overloads (consumes `TypeCompatibility`)
3. **`AmbiguityHandler`** — decides what to do when resolution is inconclusive

All three are protocols with one default implementation each. Every language gets the default implementations initially; per-language strategies can be injected later without architectural changes.

```
TypeCompatibility <- ResolutionStrategy <- OverloadResolver -> AmbiguityHandler
                                                ^
                                            executor.py
                                                ^
                                             run.py (injection)
```

### Protocols and Default Implementations

#### TypeCompatibility

```python
# interpreter/type_compatibility.py

class TypeCompatibility(Protocol):
    def score(self, arg: Any, declared_type: TypeExpr) -> int:
        """Score how well a runtime arg matches a declared parameter type."""
        ...
```

**`DefaultTypeCompatibility`** implementation:
- Exact match (runtime type name == declared scalar name) -> **2**
- Compatible pair (e.g., runtime `Int` vs declared `Float`) -> **1**
- Unknown runtime type (symbolic, heap address, None) -> **0** (neutral, no penalty)
- Mismatch (runtime `String` vs declared `Int`) -> **-1**

Uses `_runtime_type_name()` (from `vm.py`) for the runtime side. Note: heap object arguments (addresses like `"obj_Dog_0"`) are Python strings, so `_runtime_type_name` returns `"String"`. `DefaultTypeCompatibility` must detect heap addresses (strings starting with `"obj_"`) and return neutral `0` explicitly, to avoid false matches with `String`-typed overloads.

#### ResolutionStrategy

```python
# interpreter/resolution_strategy.py

class ResolutionStrategy(Protocol):
    def rank(self, candidates: list[FunctionSignature], args: list[Any]) -> list[int]:
        """Return candidate indices sorted best-to-worst."""
        ...
```

**`ArityThenTypeStrategy`** implementation (receives `TypeCompatibility` as dependency):
1. Score each candidate by arity distance: `abs(len(sig.callable_params) - len(args))`
2. Filter to candidates with minimum arity distance
3. Among arity-matched candidates, compute type score: sum of `type_compatibility.score(arg, declared_type)` per argument position
4. Return indices sorted by (arity_distance ASC, type_score DESC)

#### AmbiguityHandler

```python
# interpreter/ambiguity_handler.py

class AmbiguityHandler(Protocol):
    def handle(self, candidates: list[FunctionSignature], args: list[Any], ranked: list[int]) -> int:
        """Pick winner from equally-ranked candidates. Return index into candidates."""
        ...
```

**`FallbackFirstWithWarning`** (default):
- Logs a warning with function name, candidate count, and arg types
- Returns `ranked[0]`

**`StrictAmbiguityHandler`** (for testing):
- Raises `AmbiguousOverloadError` with diagnostic info
- Used in tests to verify resolution is actually disambiguating

### OverloadResolver

```python
# interpreter/overload_resolver.py

class OverloadResolver:
    def __init__(self, strategy: ResolutionStrategy, ambiguity_handler: AmbiguityHandler):
        self._strategy = strategy
        self._ambiguity_handler = ambiguity_handler

    def resolve(self, candidates: list[FunctionSignature], args: list[Any]) -> int:
        """Return index of winning candidate.

        Custom ResolutionStrategy implementations must return a non-empty list.
        """
        if len(candidates) <= 1:
            return 0
        ranked = self._strategy.rank(candidates, args)
        if len(ranked) <= 1:
            return ranked[0] if ranked else 0
        return self._ambiguity_handler.handle(candidates, args, ranked)
```

### Executor Integration

The resolver is called **unconditionally** at every method and constructor dispatch — it handles zero-candidate and single-candidate paths internally.

**Threading path:** The `OverloadResolver` and `type_env` must be threaded through the executor dispatch chain:
- `run.py` → `_try_execute_locally(overload_resolver=..., type_env=...)` → `LocalExecutor.execute(...)` → handler kwargs
- Same threading pattern as existing `call_resolver` injection.

**`_handle_call_method`** change:

```python
# Before:
func_labels = methods.get(method_name, [])
func_label = func_labels[0] if func_labels else ""

# After:
func_labels = methods.get(method_name, [])
sigs = type_env.method_signatures.get(scalar(type_hint), {}).get(method_name, [])
if func_labels and len(sigs) != len(func_labels):
    logger.warning("sig/label count mismatch for %s.%s", type_hint, method_name)
    winner = 0
else:
    winner = resolver.resolve(sigs, args)
func_label = func_labels[winner] if func_labels else ""
```

**Parent chain walk:** The existing parent chain walk (which searches `registry.class_parents` for inherited methods) must also apply overload resolution when the inherited method has multiple labels. The `method_signatures` lookup walks parents in the same order:

```python
# Parent chain walk with overload resolution:
for parent in registry.class_parents.get(type_hint, []):
    parent_methods = registry.class_methods.get(parent, {})
    parent_labels = parent_methods.get(method_name, [])
    if parent_labels:
        parent_sigs = type_env.method_signatures.get(scalar(parent), {}).get(method_name, [])
        if parent_labels and len(parent_sigs) != len(parent_labels):
            logger.warning("sig/label count mismatch for %s.%s", parent, method_name)
            func_label = parent_labels[0]
        else:
            winner = resolver.resolve(parent_sigs, args)
            func_label = parent_labels[winner]
        break
```

**`_try_class_constructor_call`** — same pattern for `methods.get("__init__", [])`. Note: constructors are called from `_handle_call_function`, so `_handle_call_function` must forward the resolver and `type_env` to `_try_class_constructor_call`, even though its own dispatch logic does not change.

**`_handle_call_function`** — no change to its own dispatch logic (standalone functions use FUNC_REF labels, already single-target). It must forward `OverloadResolver` and `type_env` to `_try_class_constructor_call`.

**Injection path:** `OverloadResolver` is constructed in `run.py` and passed to the executor alongside `type_env`, `cfg`, `registry` — same pattern as existing `conversion_rules` injection.

### Index Alignment Invariant

The resolver returns an index into the `sigs` list, which is used to index into `func_labels`. This requires that `registry.class_methods[class_name][method_name]` and `type_env.method_signatures[scalar(class_name)][method_name]` are populated in the same order. Both are built during the same IR scan pass: the registry scans for `<function:name@label>` patterns, and type inference processes them in IR order. The ordering invariant holds because both iterate the same instruction list sequentially.

**Deduplication risk:** Type inference deduplicates identical `FunctionSignature` objects (e.g., two overloads with all-`UNKNOWN` params), while the registry keeps all labels. This can cause `len(sigs) < len(func_labels)`. The length-mismatch guard in the integration code (shown above) catches this and falls back to index 0 with a warning.

## File Layout

### New Files

| File | Contents |
|------|----------|
| `interpreter/type_compatibility.py` | `TypeCompatibility` protocol + `DefaultTypeCompatibility` |
| `interpreter/resolution_strategy.py` | `ResolutionStrategy` protocol + `ArityThenTypeStrategy` |
| `interpreter/ambiguity_handler.py` | `AmbiguityHandler` protocol + `FallbackFirstWithWarning` + `StrictAmbiguityHandler` |
| `interpreter/overload_resolver.py` | `OverloadResolver` compositor |

### Modified Files

| File | Change |
|------|--------|
| `interpreter/executor.py` | Accept `OverloadResolver` and `type_env` in `LocalExecutor.execute()`, `_handle_call_method`, `_try_class_constructor_call`; thread through dispatch chain |
| `interpreter/run.py` | Construct `OverloadResolver` with defaults, pass `overload_resolver` and `type_env` to `_try_execute_locally()` |

### Test Files

| File | Contents |
|------|----------|
| `tests/unit/test_type_compatibility.py` | `DefaultTypeCompatibility` scoring for all match categories (exact, compatible, neutral/heap, mismatch) |
| `tests/unit/test_resolution_strategy.py` | `ArityThenTypeStrategy` ranking with various overload sets |
| `tests/unit/test_ambiguity_handler.py` | Both `FallbackFirstWithWarning` and `StrictAmbiguityHandler` |
| `tests/unit/test_overload_resolver.py` | Compositor end-to-end with mock strategies |
| `tests/integration/test_overload_resolution.py` | Full-pipeline tests with actual Java/C# overloaded methods through `run()` |

## Design Decisions

- **Unconditional resolver call:** The resolver handles all edge cases (zero, single, multiple candidates) internally. The executor does not branch on candidate count.
- **Three injectable axes:** Type compatibility, resolution strategy, and ambiguity handling are separate protocols. Each can be swapped independently per language.
- **One default everywhere initially:** All languages get `ArityThenTypeStrategy` + `DefaultTypeCompatibility` + `FallbackFirstWithWarning`. Per-language specialization is deferred until needed.
- **Neutral scoring for unknowns:** Heap objects, symbolics, and None values score 0 (neutral) rather than penalizing. This prevents false negatives when type info is incomplete.
- **No change to `_handle_call_function` dispatch logic:** Standalone function dispatch uses FUNC_REF labels (already single-target). `_handle_call_function` only forwards the resolver to `_try_class_constructor_call`.
- **Parent chain resolution:** Inherited method overloads are resolved the same way — `method_signatures` lookup walks parents in MRO order.
- **Index alignment:** `func_labels` and `sigs` lists share ordering because both are built from the same sequential IR scan. Length mismatch triggers fallback to index 0 with warning.
