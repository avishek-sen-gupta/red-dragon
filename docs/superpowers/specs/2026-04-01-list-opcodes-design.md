# `list_opcodes` MCP Tool — Design Spec

**Date:** 2026-04-01
**Status:** Approved

---

## Problem

MCP clients (LLMs, tools) interacting with the RedDragon interpreter have no way to discover which IR opcodes exist, what fields they carry, or what they mean. Every client must either read the source or guess.

---

## Solution

Add a `list_opcodes` MCP tool that returns the full opcode catalogue with rich, per-opcode descriptions. No parameters required.

---

## Response Shape

```json
{
  "opcodes": [
    {
      "name": "BINOP",
      "category": "arithmetic",
      "description": "Binary operation: apply operator to two register operands.",
      "fields": [
        {"name": "operator",   "type": "BinopKind"},
        {"name": "left",       "type": "Register"},
        {"name": "right",      "type": "Register"},
        {"name": "result_reg", "type": "Register"},
        {"name": "label",      "type": "CodeLabel"},
        {"name": "branch_targets", "type": "tuple[CodeLabel, ...]"}
      ],
      "notes": "operator is one of the BinopKind enum values: ADD, SUB, MUL, DIV, MOD, EQ, NEQ, LT, LTE, GT, GTE, AND, OR, BITAND, BITOR, BITXOR, SHL, SHR. The result lands in result_reg. Integer and float operands are both accepted — the VM does not distinguish at the IR level. Comparison operators (EQ, NEQ, LT, etc.) produce a boolean-valued register."
    }
  ]
}
```

Opcodes are sorted alphabetically by name.

---

## Data Sources

| Field | Source | Maintenance |
|-------|--------|-------------|
| `name` | `Opcode` enum value | Zero — enum is canonical |
| `category` | Hardcoded dict in `tools.py` (28 entries) | Low — add entry when new opcode added |
| `description` | `cls.__doc__` on the instruction class | Zero — docstring is canonical |
| `fields` | `get_type_hints(cls)` + `dataclasses.fields(cls)` | Zero — derived at runtime |
| `notes` | Hardcoded dict in `tools.py` (one entry per opcode) | Low — add when new opcode added |

The opcode→instruction class mapping is derived from `_TO_TYPED` in `instructions.py` via `get_type_hints(builder)["return"]`. `source_location` is excluded from `fields` — it is metadata, not a semantic operand.

---

## Categories

| Category | Opcodes |
|----------|---------|
| `variables` | CONST, LOAD_VAR, DECL_VAR, STORE_VAR, SYMBOLIC |
| `arithmetic` | BINOP, UNOP |
| `calls` | CALL_FUNCTION, CALL_METHOD, CALL_UNKNOWN, CALL_CTOR |
| `fields_and_indices` | LOAD_FIELD, STORE_FIELD, LOAD_FIELD_INDIRECT, LOAD_INDEX, STORE_INDEX |
| `control_flow` | LABEL, BRANCH, BRANCH_IF, RETURN, THROW, TRY_PUSH, TRY_POP |
| `heap` | NEW_OBJECT, NEW_ARRAY |
| `memory` | ALLOC_REGION, LOAD_REGION, WRITE_REGION, ADDRESS_OF, LOAD_INDIRECT, STORE_INDIRECT |
| `continuations` | SET_CONTINUATION, RESUME_CONTINUATION |

---

## Per-Opcode Notes

Handwritten semantic notes (3–5 sentences each) covering: what `result_reg` holds, what each non-obvious field means, VM behaviour, and common usage context.

| Opcode | Notes summary |
|--------|---------------|
| CONST | `value` is a Python literal (int, float, str, bool, None, or list for arrays). `result_reg` receives the boxed value. |
| LOAD_VAR | Reads `name` from the current frame's variable store. If the variable is not in the current frame, the VM walks up the scope chain. |
| DECL_VAR | Declares `name` in the *current* frame and assigns `value_reg` to it. Shadowing an outer-scope variable is intentional. `result_reg` is unused (NO_REGISTER). |
| STORE_VAR | Assigns `value_reg` to an already-declared `name`. Unlike DECL_VAR, STORE_VAR walks the scope chain to find the nearest frame that owns `name`. |
| SYMBOLIC | Placeholder emitted for function parameters before VM execution. Any SYMBOLIC remaining at runtime indicates an unresolved value. `hint` is a display name only. |
| BINOP | See response shape example above. |
| UNOP | `operator` is a UnopKind value: NEG, NOT, BITNOT. `operand` is the input register. `result_reg` receives the result. |
| CALL_FUNCTION | `func_name` is a FuncName (domain type). `args` is a tuple of Register or SpreadArguments (for `*args` spread). `result_reg` receives the return value; NO_REGISTER if the call is for side effects only. |
| CALL_METHOD | `obj_reg` holds the receiver object. `method_name` is a FieldName. Dispatch is dynamic — the VM looks up the method on the object's class at runtime. |
| CALL_UNKNOWN | Used when the callee is a first-class value (function stored in a variable). `target_reg` holds the callable. Used for closures, higher-order functions, and callbacks. |
| CALL_CTOR | Allocates a new object of `type_hint` type and invokes its constructor. `result_reg` receives the newly constructed object. Distinct from CALL_FUNCTION to support constructor semantics (initialising `self`). |
| LOAD_FIELD | Reads field `field_name` from `obj_reg`. `result_reg` receives the value. Raises at runtime if the field does not exist. |
| STORE_FIELD | Writes `value_reg` into field `field_name` on `obj_reg`. Creates the field if it does not exist (duck typing). `result_reg` is unused. |
| LOAD_FIELD_INDIRECT | Like LOAD_FIELD but the field name is itself a runtime value in `name_reg` (used for computed property access, e.g., `obj[expr]` in property-bag patterns). |
| LOAD_INDEX | Reads `arr_reg[index_reg]`. Supports lists, dicts, and any object that implements `__getitem__` in the VM's builtin layer. |
| STORE_INDEX | Writes `value_reg` to `arr_reg[index_reg]`. `result_reg` is unused. |
| LOAD_INDIRECT | Dereferences a Pointer value in `ptr_reg`. Used for C/Pascal-style pointer semantics. `result_reg` receives the pointed-to value. |
| STORE_INDIRECT | Writes `value_reg` to the address held in `ptr_reg`. |
| ADDRESS_OF | Takes the address of variable `var_name` and stores a Pointer object in `result_reg`. Paired with LOAD_INDIRECT/STORE_INDIRECT for pointer arithmetic. |
| NEW_OBJECT | Allocates an empty heap object tagged with `type_hint` class name. `result_reg` receives the HeapObject. Does not call a constructor — use CALL_CTOR for that. |
| NEW_ARRAY | Allocates a new array of `size_reg` elements. `type_hint` is optional. `result_reg` receives the list value. |
| LABEL | Pseudo-instruction marking a basic block entry point. `label` holds the CodeLabel. Carries no runtime action — the VM uses LABELs only for CFG construction. |
| BRANCH | Unconditional jump to `label`. Control never falls through to the next instruction. |
| BRANCH_IF | Jumps to `branch_targets[0]` if `cond_reg` is truthy, otherwise to `branch_targets[1]`. Exactly two branch targets are required. |
| RETURN | Returns `value_reg` to the caller. If `value_reg` is NO_REGISTER, the function returns None. Pops the current stack frame. |
| THROW | Raises `value_reg` as an exception. The VM unwinds the stack searching for a matching TRY_PUSH handler. |
| TRY_PUSH | Pushes an exception handler onto the VM's exception stack. `catch_labels` is a tuple of CodeLabel (one per catch clause). `finally_label` is the finally block entry (NO_LABEL if absent). `end_label` marks the end of the try/catch/finally block. |
| TRY_POP | Pops the top exception handler. Emitted at the end of a try block on the non-exception path. |
| ALLOC_REGION | Allocates a raw memory region of `size_reg` bytes. Returns an opaque region handle in `result_reg`. Used for fixed-size struct emulation (Pascal records, C structs). |
| LOAD_REGION | Reads `length` bytes from `region_reg` at byte offset `offset_reg`. `result_reg` receives the extracted value. |
| WRITE_REGION | Writes `value_reg` into `region_reg` at byte offset `offset_reg` for `length` bytes. `result_reg` is unused. |
| SET_CONTINUATION | Registers a named continuation point. `name` is a ContinuationName; `target_label` is the re-entry CodeLabel. Used to implement yield, coroutines, and iterator protocols. |
| RESUME_CONTINUATION | Transfers control to the continuation registered under `name`. Paired with SET_CONTINUATION. |

---

## Implementation

### `mcp_server/tools.py`

New function:

```python
def handle_list_opcodes() -> dict[str, Any]:
    ...
```

Derives the opcode list from `_TO_TYPED` + introspection. Returns `{"opcodes": [...]}` sorted by name.

### `mcp_server/server.py`

New registration:

```python
@mcp.tool()
def list_opcodes() -> dict[str, Any]:
    """List all IR opcodes with descriptions, categories, fields, and semantic notes."""
    return handle_list_opcodes()
```

---

## Testing

Unit test at `tests/unit/mcp_server/test_list_opcodes.py`:

- All 33 opcodes present in response
- Each entry has `name`, `category`, `description`, `fields`, `notes`
- No `source_location` in any `fields` list
- Opcodes are sorted alphabetically
- Spot-check: `BINOP` has fields `operator`, `left`, `right`, `result_reg`
- Spot-check: `LABEL` has no opcode-specific fields beyond base fields
- Spot-check: `CALL_FUNCTION` category is `calls`

---

## Out of Scope

- Filtering by category (query parameter) — can be done client-side
- Listing BinopKind / UnopKind enum values inline — separate tool if needed
- Describing the VM execution model — that belongs in documentation, not a tool response
