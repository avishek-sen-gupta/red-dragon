# Structured Class References

> **Issue:** red-dragon-wgb — Replace regex-based CLASS_REF_PATTERN with structured class references

## Problem

Class references are stringly-typed. Frontends emit `CONST "<class:name@label>"` or `CONST "<class:name@label:Parent1,Parent2>"`, encoding name, label, and parent chain into a formatted string. Every consumer — registry, type inference, executor — regex-parses this string back into components via `CLASS_REF_PATTERN`. This is the same fragility that `FUNC_REF_PATTERN` had (fixed in ADR-105 / red-dragon-fdc).

There are 33 construction sites across 15 frontend files, and 4 consumer sites (2 in executor.py, 1 in registry.py, 1 in type_inference.py).

## Decision

Replace the stringly-typed class reference with a **symbol table** (constant pool) keyed by label. The IR carries plain label strings; structured data lives in the symbol table. Same approach as ADR-105 for function references.

### Data type

```python
@dataclass(frozen=True)
class ClassRef:
    name: str              # "Dog", "Counter", "__anon_class_0"
    label: str             # "class_Dog_0"
    parents: tuple[str, ...]  # ("Animal",) or () for no parents
```

No runtime binding equivalent (unlike `BoundFuncRef` for closures). Class references are purely compile-time.

A null object sentinel for failed lookups:

```python
NO_CLASS_REF = ClassRef(name="", label="", parents=())
```

Consumer sites that look up a label in the symbol table use `class_symbol_table.get(label, NO_CLASS_REF)` and check `ref.name` truthiness — no `None` checks anywhere.

### Symbol table

A `dict[str, ClassRef]` keyed by label. Lives on `TreeSitterEmitContext` during lowering.

A new `emit_class_ref(class_name, class_label, parents, result_reg)` method on `TreeSitterEmitContext`:
1. Registers `ClassRef(name=class_name, label=class_label, parents=tuple(parents))` in the symbol table
2. Emits `CONST class_label` (plain label string, no angle brackets)

All 33 frontend construction sites replace `CLASS_REF_TEMPLATE.format(...)` / `make_class_ref(...)` with `ctx.emit_class_ref(...)`.

### Pipeline flow

The symbol table flows from frontend → `run()` → downstream consumers:

```
frontend.lower() → (instructions, class_symbol_table)
    ↓
run() passes class_symbol_table to:
    ├── build_registry(instructions, cfg, func_symbol_table, class_symbol_table)
    ├── infer_types(instructions, ..., class_symbol_table)
    └── execute_cfg(cfg, ..., class_symbol_table)
```

### Consumer changes

**Registry scanning** (`_scan_classes`, line ~99): Instead of `_parse_class_ref(str(inst.operands[0]))`, checks if a CONST operand string exists in the class symbol table. Extracts `ClassRef.name`, `.label`, `.parents` directly.

**Type inference** (`_infer_const_type`, line ~879): Instead of `_CLASS_REF_PATTERN.search(str(raw))`, checks `raw in class_symbol_table`. Returns `UNKNOWN` for class refs.

**Executor** — 2 call sites:

1. `_handle_new_object` (line ~328): Dereferences a variable holding a class ref to get the canonical class name. Changes from `_parse_class_ref(str(raw))` to `isinstance(raw, ClassRef)`, accessing `.name` directly.
2. `_try_class_constructor_call` (line ~1029): Checks if a call target is a class reference for constructor dispatch. Changes from `_parse_class_ref(func_val)` to `isinstance(func_val, ClassRef)`, accessing `.name` and `.label` directly.

### Deletions

- `CLASS_REF_PATTERN` (constants.py)
- `CLASS_REF_TEMPLATE` (constants.py)
- `CLASS_REF_WITH_PARENTS_TEMPLATE` (constants.py)
- `RefPatterns.CLASS_RE` (registry.py)
- `RefPatterns` class entirely (no remaining patterns)
- `RefParseResult` class (registry.py) — no remaining users
- `_parse_class_ref()` (registry.py)
- `_CLASS_REF_PATTERN` (type_inference.py)
- `make_class_ref()` (common/declarations.py)

### LLM frontend boundary

The LLM frontend continues to instruct the LLM to emit `<class:name@label>` strings. A new `_convert_llm_class_refs()` function (parallel to the existing `_convert_llm_func_refs()`) converts these to symbol table entries + plain labels using a local regex. This is the ONLY place regex is used for class references — at the LLM boundary.

The existing `_FUNC_REF_LABEL_PATTERN` in the chunked LLM renumberer already handles both `<function:...>` and `<class:...>` patterns. It stays string-based at the boundary, converting after reassembly.

### Backward compatibility

No shim. Direct switch to plain labels (no dual-phase transition):
- IR output changes from `CONST "<class:Dog@class_Dog_0>"` to `CONST "class_Dog_0"`
- Registers hold `ClassRef` objects where they previously held strings
- Unit tests checking IR shape (~79 assertions) update to plain labels
- Integration tests are transparent — they test final VM state

## Scope

- **In scope:** Class references (`ClassRef`, symbol table, all frontend construction sites, registry, type inference, executor, LLM frontend boundary conversion)
- **Out of scope:** Nothing — this completes the stringly-typed reference elimination

## Files

- `interpreter/class_ref.py` — `ClassRef` dataclass (new)
- `interpreter/constants.py` — delete `CLASS_REF_PATTERN`, `CLASS_REF_TEMPLATE`, `CLASS_REF_WITH_PARENTS_TEMPLATE`
- `interpreter/frontends/context.py` — add `class_symbol_table` dict and `emit_class_ref()` method
- `interpreter/frontends/_base.py` — add `_class_symbol_table`, `_emit_class_ref()`, `class_symbol_table` property
- `interpreter/frontend.py` — add `class_symbol_table` property to ABC
- `interpreter/frontends/common/declarations.py` — replace `make_class_ref()` with `ctx.emit_class_ref()`
- `interpreter/frontends/` (15 frontend files, 33 sites) — replace `CLASS_REF_TEMPLATE.format(...)` with `ctx.emit_class_ref(...)`
- `interpreter/registry.py` — delete `_parse_class_ref()`, `RefPatterns`, `RefParseResult`; accept class symbol table
- `interpreter/type_inference.py` — delete `_CLASS_REF_PATTERN`; accept class symbol table
- `interpreter/executor.py` — `isinstance(val, ClassRef)` at 2 sites
- `interpreter/run.py` — thread class symbol table through pipeline
- `interpreter/llm_frontend.py` — parse `<class:...>` strings into symbol table entries
- `interpreter/chunked_llm_frontend.py` — convert after reassembly
- `tests/unit/` — update ~79 IR shape assertions
- `tests/integration/` — no changes expected

## Testing

- Unit tests: verify `ClassRef` construction, symbol table population, `emit_class_ref` emits correct IR
- Unit tests: verify registry, type inference, executor work with class symbol table
- Integration tests: all existing tests pass unchanged (they test VM output, not IR shape)
- Regression: full test suite (11680 tests)
