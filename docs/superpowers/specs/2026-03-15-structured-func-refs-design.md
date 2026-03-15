# Structured Function References

> **Issue:** red-dragon-fdc — Replace regex-based FUNC_REF_PATTERN with structured function references

## Problem

Function references are stringly-typed. Frontends emit `CONST "<function:name@label>"`, encoding name, label, and (at runtime) closure ID into a formatted string. Every consumer — registry, type inference, executor — regex-parses this string back into components via `FUNC_REF_PATTERN`. This is fragile (e.g., dotted names like `Counter.new` break `\w+` matching) and violates the design principle of passing decisions through data rather than re-deriving them.

There are 56 construction sites across 15 frontends, and 9 consumer sites that regex-parse the string (7 in executor.py, 1 in registry.py, 2 in type_inference.py).

## Decision

Replace the stringly-typed function reference with a **symbol table** (constant pool) keyed by label. The IR carries plain label strings; structured data lives in the symbol table.

### Data types

```python
@dataclass(frozen=True)
class FuncRef:
    name: str   # "add", "new", "__lambda"
    label: str  # "func_add_0"

@dataclass(frozen=True)
class BoundFuncRef:
    func_ref: FuncRef     # compile-time reference
    closure_id: str       # "closure_42" (runtime-only)
```

`FuncRef` is the compile-time record. `BoundFuncRef` composes `FuncRef` with a runtime closure binding. No inheritance — composition only.

### Symbol table

A `dict[str, FuncRef]` keyed by label. Lives on `TreeSitterEmitContext` during lowering.

A new `emit_func_ref(func_name, func_label, result_reg)` method on `TreeSitterEmitContext`:
1. Registers `FuncRef(name=func_name, label=func_label)` in the symbol table
2. Emits `CONST func_label` (plain label string, no angle brackets)

All 56 frontend construction sites replace `FUNC_REF_TEMPLATE.format(...)` with `ctx.emit_func_ref(...)`.

### Pipeline flow

The symbol table flows from frontend → `run()` → downstream consumers:

```
frontend.lower() → (instructions, func_symbol_table)
    ↓
run() passes func_symbol_table to:
    ├── build_registry(instructions, cfg, func_symbol_table)
    ├── infer_types(instructions, ..., func_symbol_table)
    └── execute_cfg(cfg, ..., func_symbol_table)
```

### Consumer changes

**Registry scanning** (`build_registry`): Instead of regex-matching CONST operands, checks if a CONST operand string exists in the symbol table. Extracts `FuncRef.name` for class method discovery.

**Type inference** (`infer_types`): Instead of `_FUNC_REF_EXTRACT` regex, looks up the CONST operand in the symbol table. Gets `FuncRef.name` and `FuncRef.label` for `FunctionType` construction.

**Executor** — 7 call sites in `executor.py` currently use `_parse_func_ref()`. All switch to `isinstance(val, BoundFuncRef)`:

1. `_handle_const` (line ~88): Looks up the CONST operand in the symbol table. If found, creates `BoundFuncRef(func_ref, closure_id)` — with closure capture when depth > 1, with `closure_id=""` at top level. Always stores a `BoundFuncRef` in the register. One type everywhere, no mixed dispatch.
2. `_try_user_function_call` (line ~1111): Checks `isinstance(val, BoundFuncRef)`. Accesses `.func_ref.name`, `.func_ref.label`, `.closure_id` directly. No regex parsing.
3. `_handle_address_of` / `&` operator (line ~239): Function reference identity — `&func_ref` returns the reference unchanged. Switch from `_parse_func_ref(current_val).matched` to `isinstance(current_val, BoundFuncRef)`.
4. `_handle_load_field` with `field_name == "*"` (line ~440): Pointer dereference on function ref — pass through unchanged. Switch to `isinstance(obj_val, BoundFuncRef)`.
5. `_handle_unop` / `&` unary (line ~788): Address-of on function ref. Switch to `isinstance(operand, BoundFuncRef)`.
6. `_handle_call_method` / `.call()/.apply()` (line ~1308): Invoking a function ref as an object with `.call()`. Switch to `isinstance(obj_val.value, BoundFuncRef)`.
7. Import: `from interpreter.registry import _parse_func_ref` — delete this import.

### Deletions

- `FUNC_REF_PATTERN` (constants.py)
- `FUNC_REF_TEMPLATE` (constants.py)
- `RefPatterns.FUNC_RE` (registry.py)
- `_parse_func_ref()` (registry.py)
- `_FUNC_REF_EXTRACT` (type_inference.py)
- `_FUNC_REF_PATTERN` (type_inference.py) — the `re.compile(r"<function:")` prefix-check pattern, separate from `_FUNC_REF_EXTRACT`

### LLM frontend boundary

The LLM frontend continues to instruct the LLM to emit `<function:name@label>` strings. The LLM frontend's IR parser converts these to symbol table entries + plain labels. The string format is a serialization format at the LLM boundary only — it does not flow through the pipeline.

The chunked LLM renumberer similarly stays string-based at the boundary, converting after reassembly.

### Backward compatibility

No shim. Clean break:
- IR output changes from `CONST "<function:add@func_add_0>"` to `CONST "func_add_0"`
- `TypedValue.value` holds `BoundFuncRef` instead of a string
- `_format_val` in `run.py` gets a `BoundFuncRef` branch for display
- Unit tests checking IR shape (~50+ assertions) update to plain labels
- Integration tests are transparent — they test final VM state

## Scope

- **In scope:** Function references (`FuncRef`, `BoundFuncRef`, symbol table, all 15 tree-sitter frontends, registry, type inference, executor, LLM frontend boundary conversion)
- **Out of scope:** Class references (`CLASS_REF_PATTERN`) — separate issue red-dragon-wgb, same approach applied after this is complete

## Files

- `interpreter/func_ref.py` — `FuncRef` and `BoundFuncRef` dataclasses (new)
- `interpreter/constants.py` — delete `FUNC_REF_PATTERN`, `FUNC_REF_TEMPLATE`
- `interpreter/frontends/context.py` — add `func_symbol_table` dict and `emit_func_ref()` method
- `interpreter/frontends/` (all 15 language dirs) — replace `FUNC_REF_TEMPLATE.format(...)` with `ctx.emit_func_ref(...)`
- `interpreter/registry.py` — delete `_parse_func_ref()`, `RefPatterns.FUNC_RE`; accept symbol table in `build_registry()`
- `interpreter/type_inference.py` — delete `_FUNC_REF_EXTRACT`; accept symbol table in `infer_types()`
- `interpreter/executor.py` — `_handle_const` uses symbol table lookup + `BoundFuncRef`; `_try_user_function_call` uses `isinstance` check
- `interpreter/run.py` — thread symbol table through pipeline; `_format_val` handles `BoundFuncRef`
- `interpreter/llm_frontend.py` — parse `<function:...>` strings into symbol table entries
- `interpreter/chunked_llm_frontend.py` — convert after reassembly
- `tests/unit/` — update IR shape assertions
- `tests/integration/` — no changes expected

## Testing

- Unit tests: verify `FuncRef`/`BoundFuncRef` construction, symbol table population, `emit_func_ref` emits correct IR
- Unit tests: verify registry, type inference, executor work with symbol table (not regex)
- Integration tests: all existing tests pass unchanged (they test VM output, not IR shape)
- Regression: full test suite (11666 tests)
