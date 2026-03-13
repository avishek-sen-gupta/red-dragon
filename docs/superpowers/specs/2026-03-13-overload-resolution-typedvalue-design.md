# Overload Resolution: TypedValue Args + Subtype-Aware Scoring

**Date:** 2026-03-13
**Bead:** `red-dragon-gsl.7.3.2`
**Status:** Design approved

## Problem

The overload resolver receives raw Python values (`list[Any]`) — type information is stripped at the call site via `[a.value for a in args]`. `DefaultTypeCompatibility.score()` uses `runtime_type_name(arg)` to infer types from raw values, which works for primitives but fails for heap objects (they appear as address strings like `"obj_0"`). There is no subtype-aware scoring — `is_subtype_expr()` from `TypeGraph` is not integrated, so overloads like `foo(Animal)` vs `foo(Dog)` cannot be disambiguated.

## Design

### 1. Interface Changes

The protocol chain changes from `Any` to `TypedValue` throughout:

```python
# TypeCompatibility protocol
def score(self, arg: TypedValue, declared_type: TypeExpr) -> int: ...

# ResolutionStrategy protocol
def rank(self, candidates: list[FunctionSignature], args: list[TypedValue]) -> list[int]: ...

# OverloadResolver
def resolve(self, candidates: list[FunctionSignature], args: list[TypedValue]) -> int: ...

# AmbiguityHandler protocol
def handle(self, candidates: list[FunctionSignature], args: list[TypedValue], ranked: list[int]) -> int: ...
```

### 2. DefaultTypeCompatibility Changes

Constructor gains a `TypeGraph` parameter:

```python
class DefaultTypeCompatibility:
    def __init__(self, type_graph: TypeGraph) -> None:
        self._type_graph = type_graph
```

`score()` reads `arg.type` instead of calling `runtime_type_name(arg)`:

```python
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

Scoring hierarchy:
- Exact type match = 2
- Coercion match = 1 (Int↔Float, Bool→Int — from `_COMPATIBLE_PAIRS`)
- Subtype match = 1 (Dog → Animal, Int → Number, etc. — from `TypeGraph`)
- Unknown type on either side = 0 (neutral)
- Unrelated types = -1

The heap address string check (`arg.startswith("obj_")`) is removed — type information comes from `arg.type` directly.

The `_COMPATIBLE_PAIRS` table is **retained** — it encodes coercion relationships (e.g., an Int can be passed where a Float is expected), not subtype relationships. Int and Float are siblings under Number in the type graph, not subtypes of each other. `is_subtype_expr(scalar("Int"), scalar("Float"))` returns `False`. The coercion table and the subtype graph serve different purposes and both score at 1.

### 3. TypeGraph Construction in run()

After registry scanning and before `OverloadResolver` construction:

```python
class_nodes = tuple(
    TypeNode(name=cls, parents=tuple(parents))
    for cls, parents in registry.class_parents.items()
)
type_graph = TypeGraph(DEFAULT_TYPE_NODES + class_nodes)
```

Construction order in `run()`:
1. Parse → lower → build CFG
2. Scan registry (`class_parents` populated)
3. Build `TypeGraph` from registry class hierarchy
4. Build `DefaultTypeCompatibility(type_graph)`
5. Build `OverloadResolver(ArityThenTypeStrategy(compatibility), FallbackFirstWithWarning())`
6. Run type inference
7. Execute

### 4. Call Site Changes in Executor

Three call sites stop extracting `.value`:

**`_handle_call_method` (line ~1294):**
```python
# Before:
winner = overload_resolver.resolve(sigs, [a.value for a in args])
# After:
winner = overload_resolver.resolve(sigs, args)
```

**Parent chain walk (line ~1314):** Same change.

**`_handle_call_function` / `_try_class_constructor_call`:** Same pattern where applicable.

`args` is already `list[TypedValue]` — built by `[_resolve_binop_operand(vm, a) for a in arg_regs]`.

## Files Modified

| File | Change |
|------|--------|
| `interpreter/type_compatibility.py` | `score()` takes `TypedValue`, inject `TypeGraph`, retain `_COMPATIBLE_PAIRS` for coercion, remove heap address string check, read `arg.type` instead of `runtime_type_name(arg)` |
| `interpreter/resolution_strategy.py` | `rank()` takes `list[TypedValue]` |
| `interpreter/overload_resolver.py` | `resolve()` takes `list[TypedValue]`; `NullOverloadResolver.resolve()` signature updated for consistency |
| `interpreter/ambiguity_handler.py` | `handle()` takes `list[TypedValue]`, replace `runtime_type_name(a)` with `str(a.type)` in diagnostic messages |
| `interpreter/executor.py` | Call sites pass `args` directly instead of `[a.value for a in args]` |
| `interpreter/run.py` | Build `TypeGraph` from registry, inject into `DefaultTypeCompatibility` |

## Testing

### Unit Tests

- `test_type_compatibility.py`: Update to pass `TypedValue`. Add subtype scoring tests — `TypedValue("obj_0", scalar("Dog"))` against `scalar("Animal")` = 1, against `scalar("Dog")` = 2, against `scalar("Cat")` = -1.
- `test_overload_resolver.py`: Update to pass `TypedValue`. Add test: overloads `foo(Animal)` and `foo(Dog)`, passing `Dog`-typed arg resolves to `foo(Dog)`.

### Integration Tests

- Java program with overloaded methods taking different class types, verifying correct overload dispatch via `run()`.

## Not Changed / Out of Scope

- **`UnresolvedCallResolver`** — `call_resolver.resolve_method()` (executor.py lines ~1281, ~1322) still receives `[a.value for a in args]`. This interface does not perform type-based resolution and remains on raw values.

## Design Decisions

- **TypedValue end-to-end:** Same pattern as the TypedValue migration — pass `TypedValue` through the full resolution chain instead of stripping types at the boundary.
- **Exact = 2, subtype = 1:** Same scoring scale as current primitives. Most-specific overload wins naturally via sum scoring in `ArityThenTypeStrategy`.
- **TypeGraph built from registry:** Class hierarchy is static and known after registry scanning. No need for type inference.
- **Retain _COMPATIBLE_PAIRS:** Coercion (Int↔Float, Bool→Int) and subtyping (Dog→Animal) are different relationships. Int and Float are siblings under Number, not subtypes of each other. The coercion table handles the former, the TypeGraph handles the latter. Both score at 1.
- **Remove heap address check:** Type comes from `arg.type`, not from inspecting the raw value string.
