# Design: Remove str() wrapping from Register-typed instruction fields (v11s)

## Problem

37 sites across frontend files explicitly call `str()` on Register objects when constructing typed instructions:

```python
# Current — passes bare string
ctx.emit_inst(StoreField(obj_reg=str(obj_reg), value_reg=str(val_reg), ...))

# Correct — passes Register directly
ctx.emit_inst(StoreField(obj_reg=obj_reg, value_reg=val_reg, ...))
```

This was historically needed because instruction fields were `str`. They are now `Register` in the dataclass definitions but receive strings at runtime, which breaks the `reads()` and `writes()` methods (added in cv82) that call `.is_present()`.

## Root Cause

The `str()` calls exist in direct typed-instruction construction sites across `common/expressions.py` and 17 other frontend files. They are NOT in the `IRInstruction()` → `_to_typed` conversion path (which correctly wraps with `Register()`).

## Design

**Remove `str()` at the 37 direct construction sites.** Pass `Register` objects through unchanged.

The `IRInstruction()` factory and `_to_typed` converters remain as the LLM/legacy boundary layer. They correctly handle the flat JSON → typed instruction conversion and are not affected.

### Scope

- 37 `str()` wrapping sites across 18 frontend files
- No new abstractions, no new types, no architectural changes
- Mechanical find-and-replace with verification

### Verification

After removal:
1. All 13,108 tests must pass
2. Re-apply the `_defs_of`/`_uses_of` rewrite from cv82 and verify `reads()`/`writes()` work without `AttributeError`

### Unblocks

- `lybv`: Migrate Definition.variable / Use.variable to StorageIdentifier
- Enables `_defs_of`/`_uses_of` to delegate to `instruction.reads()`/`instruction.writes()`
