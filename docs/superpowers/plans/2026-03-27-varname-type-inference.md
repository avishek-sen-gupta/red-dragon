# VarName in type_inference.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `str(name)` stringification in type_inference.py with native VarName keys, pushing the domain type one layer deeper into the type system.

**Architecture:** Change 4 dict field key types and 1 frozenset from `str` to `VarName` on `_InferenceContext`. Update method signatures and the 2 inference functions that read/write these dicts. Cascade to `TypeEnvironment.scoped_var_types` and `type_env_builder`. Single commit.

**Tech Stack:** Python 3.13+, pytest, Poetry

**Issue:** red-dragon-d3gp

---

## Task 1: Change _InferenceContext dict key types and methods

**Files:**
- Modify: `interpreter/types/type_inference.py` (lines 179, 191, 195, 198, 205, 207-231, 233-247, 250-263, 270-290, 371-386, 419, 437, 574-617)
- Modify: `interpreter/types/type_environment.py` (line 43)

- [ ] **Step 1: Add VarName import to type_inference.py**

```python
from interpreter.var_name import VarName
```

- [ ] **Step 2: Change _InferenceContext field types**

```python
# line 179: inner dict key str → VarName
scoped_var_types: dict[str, dict[VarName, TypeExpr]] = field(default_factory=dict)

# line 191: key str → VarName
var_array_element_types: dict[VarName, TypeExpr] = field(default_factory=dict)

# line 195: key str → VarName
var_tuple_element_types: dict[VarName, dict[int, TypeExpr]] = field(
    default_factory=dict
)

# line 198: value str → VarName (register→var mapping)
register_source_var: dict[str, VarName] = field(default_factory=dict)

# line 205: frozenset[str] → frozenset[VarName]
_seeded_var_names: frozenset[VarName] = field(default_factory=frozenset)
```

- [ ] **Step 3: Update store_var_type and lookup_var_type signatures**

```python
# line 207
def store_var_type(self, name: VarName, type_expr: TypeExpr) -> None:
    # body unchanged — name is already used as dict key

# line 224
def lookup_var_type(self, name: VarName) -> TypeExpr:
    # body unchanged — name is already used as dict key
```

- [ ] **Step 4: Update flat_var_types return type**

```python
# line 233
def flat_var_types(self) -> dict[VarName, TypeExpr]:
    result: dict[VarName, TypeExpr] = {}
    # body unchanged
```

- [ ] **Step 5: Remove str(name) calls in _infer_load_var (lines 574-595)**

```python
def _infer_load_var(inst: LoadVar, ctx: _InferenceContext, type_resolver: TypeResolver) -> None:
    name = inst.name  # already VarName, no "if inst.name else ''" needed — NO_VAR_NAME is falsy
    if inst.result_reg.is_present() and name:
        ctx.register_source_var[str(inst.result_reg)] = name  # VarName, not str
    var_type = ctx.lookup_var_type(name) if name else UNKNOWN  # pass VarName directly
    if inst.result_reg.is_present() and var_type:
        ctx.register_types[inst.result_reg] = var_type
    if inst.result_reg.is_present() and name in ctx.var_array_element_types:  # VarName key
        ctx.array_element_types[str(inst.result_reg)] = ctx.var_array_element_types[name]
    if inst.result_reg.is_present() and name in ctx.var_tuple_element_types:  # VarName key
        ctx.tuple_element_types[str(inst.result_reg)] = ctx.var_tuple_element_types[name]
        ctx.tuple_registers.add(str(inst.result_reg))
```

- [ ] **Step 6: Remove str(name) calls in _infer_store_var (lines 598-617)**

```python
def _infer_store_var(inst: StoreVar | DeclVar, ctx: _InferenceContext, type_resolver: TypeResolver) -> None:
    name = inst.name  # already VarName
    if not name:
        return
    value_reg = _reg_key(inst.value_reg)
    if value_reg.is_present():
        if value_reg in ctx.register_types:
            ctx.store_var_type(name, ctx.register_types[value_reg])  # pass VarName
        str_reg = str(value_reg)
        if str_reg in ctx.array_element_types:
            ctx.var_array_element_types[name] = ctx.array_element_types[str_reg]  # VarName key
        if str_reg in ctx.tuple_element_types:
            ctx.var_tuple_element_types[name] = ctx.tuple_element_types[str_reg]  # VarName key
```

- [ ] **Step 7: Update _seeded_var_names construction (line 386)**

The builder's `var_types.keys()` are strings. Wrap them:

```python
_seeded_var_names=frozenset(VarName(k) for k in type_env_builder.var_types.keys()),
```

- [ ] **Step 8: Update TypeEnvironment.scoped_var_types (type_environment.py line 43)**

```python
# Add VarName import
from interpreter.var_name import VarName

# Change inner key type
scoped_var_types: MappingProxyType[str, MappingProxyType[VarName, TypeExpr]] = (
    MappingProxyType({})
)
```

- [ ] **Step 9: Update frozen_scoped construction (type_inference.py ~line 419/437)**

The code that freezes `scoped_var_types` into `MappingProxyType` should already work — keys are VarName after step 2. Just verify the dict comprehension produces `MappingProxyType[VarName, TypeExpr]`.

- [ ] **Step 10: Run full test suite**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
```

Expected: 13,017 passed. No test changes needed — tests don't access these internal dicts directly.

- [ ] **Step 11: Format, lint, commit**

```bash
poetry run python -m black .
poetry run lint-imports
bd backup
git add interpreter/types/type_inference.py interpreter/types/type_environment.py
git commit -m "Push VarName into type_inference.py internal dicts

Replace str(name) stringification with native VarName keys in
_InferenceContext: scoped_var_types inner key, var_array_element_types,
var_tuple_element_types, register_source_var value, _seeded_var_names.
Update store_var_type/lookup_var_type signatures. Cascade to
TypeEnvironment.scoped_var_types inner key.

Issue: red-dragon-d3gp

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push
bd close d3gp --reason "All str(name) calls replaced with native VarName keys in type_inference.py and TypeEnvironment"
```
