# JS/TS Frontend Lowering Gaps — Design Spec

**Date:** 2026-03-11
**ADR:** ADR-101
**Beads:** red-dragon-gvu.2 (JS/TS modern features)

## Scope

Close 5 P1 gaps in JS/TS frontends: `optional_chain`, `computed_property_name`, `property_signature`, `call_signature`/`construct_signature` (already handled), `index_signature` (no-op).

## Changes

### 1. `optional_chain` — close gap, add test

**No code changes.** Tree-sitter parses `obj?.prop` as `member_expression` with an `optional_chain` child. Existing `lower_js_attribute`/`lower_js_subscript` already extract `object`/`property`/`index` fields correctly. The `optional_chain` node is an unnamed child that is skipped.

**Test:** Parse `obj?.prop`, `obj?.method()`, `obj?.[0]`, `a?.b?.c` — verify `LOAD_FIELD`, `CALL_METHOD`, `LOAD_INDEX` opcodes are emitted without SYMBOLIC.

### 2. `computed_property_name` — evaluate expression as key

**File:** `interpreter/frontends/javascript/expressions.py`

In `lower_js_object_literal`, when the `pair`'s `key` child has type `computed_property_name`, evaluate its inner expression via `ctx.lower_expr()` instead of `lower_const_literal()`. The inner expression is the first named child of `computed_property_name` (skipping `[` and `]` brackets).

```python
# In the pair handling loop:
if key_node.type == "computed_property_name":
    inner_expr = next(
        (c for c in key_node.children if c.is_named), None
    )
    key_reg = ctx.lower_expr(inner_expr) if inner_expr else lower_const_literal(ctx, key_node)
else:
    key_reg = lower_const_literal(ctx, key_node)
```

**Test:** Parse `{ [key]: 1, [1 + 2]: 'three' }` — verify `LOAD_VAR` for `key` and `BINOP` for `1 + 2` feed into `STORE_INDEX`.

### 3. `property_signature` — seed type for inference chain walk

**File:** `interpreter/frontends/typescript.py`

Add `_lower_ts_interface_property` that extracts name and type annotation, emits `STORE_VAR` with type seeding:

```python
def _lower_ts_interface_property(ctx, node):
    name_node = node.child_by_field_name("name")
    prop_name = ctx.node_text(name_node) if name_node else "__unknown_prop"
    raw_type = extract_type_from_field(ctx, node, "type")
    type_hint = normalize_type_hint(raw_type.lstrip(": "), ctx.type_map)
    val_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=val_reg, operands=[ctx.constants.none_literal])
    ctx.emit(Opcode.STORE_VAR, operands=[prop_name, val_reg], node=node)
    ctx.seed_var_type(prop_name, type_hint)
```

In `lower_interface_decl`, dispatch `property_signature` to this function (remove from skip list).

**Test:** Parse interface with `name: string; readonly id: number; optional?: boolean` — verify `STORE_VAR` emitted for each, type hints seeded.

### 4. `call_signature` / `construct_signature` — already handled

Already dispatched to `_lower_ts_interface_method` in `lower_interface_decl`. `call_signature` gets synthetic name `__iface_method` (from fallback when `name` field is absent). No changes needed.

### 5. `index_signature` — documented no-op

No IR representation for "any key returns type X." Skip silently. Already in the skip list at line 164 of `typescript.py`.

## Node Type Constants

Add to `javascript/node_types.py`:
- `COMPUTED_PROPERTY_NAME = "computed_property_name"`
- `OPTIONAL_CHAIN = "optional_chain"`

No new TS node type constants needed (signatures are matched by string in `lower_interface_decl`).

## Test Plan

| Test | File | Verifies |
|------|------|----------|
| `test_optional_chain_property` | `test_js_frontend.py` or `test_ts_frontend.py` | `obj?.prop` → LOAD_FIELD |
| `test_optional_chain_method` | same | `obj?.method()` → CALL_METHOD |
| `test_optional_chain_index` | same | `obj?.[0]` → LOAD_INDEX |
| `test_optional_chain_nested` | same | `a?.b?.c` → two LOAD_FIELDs |
| `test_computed_property_name_identifier` | `test_js_frontend.py` | `{ [key]: 1 }` → LOAD_VAR + STORE_INDEX |
| `test_computed_property_name_expression` | same | `{ [1+2]: 'x' }` → BINOP + STORE_INDEX |
| `test_interface_property_signature` | `test_ts_frontend.py` | `name: string` → STORE_VAR + type seeded |
| `test_interface_property_readonly` | same | `readonly id: number` → STORE_VAR + type seeded |
| `test_interface_property_optional` | same | `optional?: boolean` → STORE_VAR + type seeded |

## Gap Doc Updates

After implementation, flip status to DONE for:
- JS `optional_chain`
- JS `computed_property_name`
- TS `property_signature`

`call_signature`/`construct_signature` need separate entries or a note that they're handled via `method_signature` handler.
`index_signature` stays TODO with "(no-op, see ADR-101)" annotation.
