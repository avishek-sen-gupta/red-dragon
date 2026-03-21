# Symbol Table Executor Threading — Design Spec

**Date:** 2026-03-21
**Status:** Approved
**Scope:** Thread `symbol_table` through executor pipeline, replace `_resolve_class_static_field` IR scanning hack

## Problem

`_resolve_class_static_field` in `executor.py` scans IR instructions to find class constants (e.g., `Color.RED = 0`). The symbol table already has this information from the Phase 2 extractors. The symbol table just needs to be threaded to the executor.

## Design

Thread `symbol_table` following the exact same pattern as `func_symbol_table` / `class_symbol_table`:

1. **`BaseFrontend._lower_with_context`** — save `ctx.symbol_table` to `self._symbol_table` after lowering. Add `symbol_table` property.
2. **`run()`** — pass `frontend.symbol_table` to `execute_cfg()`
3. **`execute_cfg()`** — accept `symbol_table` parameter, pass to `_try_execute_locally`
4. **`_handle_load_field`** — receive `symbol_table` from kwargs, look up `symbol_table.classes.get(class_ref.name)` → `constants.get(field_name)` instead of scanning IR
5. **Delete** `_resolve_class_static_field`

### Files Changed

- `interpreter/frontends/_base.py` — save + expose `symbol_table`
- `interpreter/run.py` — pass `symbol_table` to `execute_cfg`
- `interpreter/executor.py` — add `symbol_table` kwarg to `_handle_load_field`, replace IR scan, delete `_resolve_class_static_field`

## Testing

All existing tests pass unchanged — behavior identical.
