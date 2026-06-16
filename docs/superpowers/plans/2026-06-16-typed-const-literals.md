# Typed `Const` Literals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the IR `Const` carry a **required, non-optional** `TypeExpr` so a literal's type is fixed at emit time, deleting `_parse_const`'s runtime type-guessing.

**Architecture:** `Const.type_expr` becomes a required keyword-only field (no default, never `None`, never `UNKNOWN`-as-sentinel) plus typed factory classmethods. `_handle_const` builds `TypedValue(value, type_expr)` directly. Migration is **atomic**: the required field breaks every un-migrated `Const(...)` site at once, so all producers, the LLM/text builder, and the `_parse_const`/`Const.value` consumers are migrated on one branch. Per the agreed tradeoff there is **no partial-migration safety net** — the *global* suite is red mid-branch, but each area's own tests are green immediately after that area is converted, and the branch is fully green before merge.

**Tech Stack:** Python 3.13, Poetry, pytest. `poetry run python -m pytest`; export `PROLEAP_BRIDGE_JAR` for bridge/COBOL tests; format with `poetry run python -m black`.

**Spec:** `docs/superpowers/specs/2026-06-16-typed-const-literals-design.md`
**Issue:** red-dragon-v0l2

---

## Background an implementer needs

- **Run tests:** `export PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"` first.
- **The bug:** `_handle_const` (`interpreter/handlers/variables.py:50`) calls `_parse_const(inst.operands[0])` (`interpreter/vm/vm.py:378`): `int(raw)`→`float(raw)`→quote-strip→str. A Python `str` `"10"` becomes `int 10`.
- **Type vocabulary (reuse):** `interpreter/types/type_expr.py`: `scalar(name)->ScalarType` (284), `UnknownType`/`UNKNOWN` (46/72), `FunctionType` (201), `metatype(t)` (319), `_NULL=ScalarType(TypeName("Null"))` (346). `interpreter/constants.py:106` `FoundationTypeName` (`INT/FLOAT/STRING/BOOL/VOID/...`). `interpreter/types/typed_value.py`: `TypedValue(value, type)`.
- **`Const` today** (`interpreter/instructions.py:201-214`): `result_reg=NO_REGISTER`, `value: Any = ""`; `operands` returns `[self.value] if self.value != "" else []` (drops empty strings — fix).
- **`_const` builder** (`interpreter/instructions.py:1069`) rebuilds `Const` from LLM/text JSON. The LLM prompt (`interpreter/llm/llm_frontend.py`) documents the string conventions.
- **String convention `_parse_const` decodes** (all to be replaced by explicit type): numeric→bare string; string literal→quoted `'"x"'`; `None`/`True`/`False`→canonical words; func→`"<function:name@label>"`; class→`"<class:Cls@label>"`.

## File / responsibility map

| File | Change |
|------|--------|
| `interpreter/constants.py` | add `FoundationTypeName.NULL` |
| `interpreter/types/type_expr.py` | export canonical `NULL` scalar; `_NULL` aliases it |
| `interpreter/instructions.py` | `Const.type_expr` required (kw-only); typed factory classmethods; `operands` fix; `_const` decodes `literal_type` |
| `interpreter/handlers/variables.py` | `_handle_const` → `TypedValue(value, type_expr)`; ref resolution keys on `type_expr`; drop `_parse_const` |
| `interpreter/handlers/memory.py`, `interpreter/handlers/calls.py`, `interpreter/vm/executor.py` | drop `_parse_const` use/import/re-export |
| `interpreter/types/type_inference.py`, `interpreter/registry.py`, `interpreter/project/linker.py` | read `Const.type_expr`, not inferred-from-`value` |
| `interpreter/cobol/*`, `interpreter/frontends/<lang>/*`, `_base.py`, `common/*` | migrate `Const(...)` / `const_to_reg(...)` to factories |
| `interpreter/llm/llm_frontend.py` | prompt: CONST carries `literal_type` |
| `interpreter/vm/vm.py` | delete `_parse_const` (last) |
| `interpreter/cobol/lower_io.py` | delete `_status_const_reg` |

**Branch:** `typed-const-literals`; merge only when the full suite is green.

---

## Task 1: Add the `Null` foundation type

**Files:** `interpreter/constants.py`, `interpreter/types/type_expr.py`, Test: `tests/unit/types/test_type_expr_null.py`

- [ ] **Step 1: Failing test** — create `tests/unit/types/test_type_expr_null.py`:

```python
# pyright: standard
from interpreter.constants import FoundationTypeName
from interpreter.types.type_expr import scalar, NULL


def test_null_foundation_name_exists():
    assert str(FoundationTypeName.NULL) == "Null"


def test_null_scalar_is_canonical():
    assert NULL == scalar(FoundationTypeName.NULL)
```

- [ ] **Step 2: Run → FAIL** — `poetry run python -m pytest tests/unit/types/test_type_expr_null.py -p no:randomly -q` (AttributeError/ImportError).

- [ ] **Step 3:** In `interpreter/constants.py`, after `VOID = TypeName("Void")` in `FoundationTypeName`:

```python
    VOID = TypeName("Void")
    NULL = TypeName("Null")
```

- [ ] **Step 4:** In `interpreter/types/type_expr.py`, replace `_NULL = ScalarType(TypeName("Null"))` (line 346) with:

```python
NULL = ScalarType(FoundationTypeName.NULL)
_NULL = NULL  # alias kept for optional_of / union helpers
```

Add `from interpreter.constants import FoundationTypeName` at the top if absent (confirm no import cycle: `constants.py` must not import `type_expr`; today it does not).

- [ ] **Step 5: Run → PASS.** **Step 6: Commit** `feat(types): add FoundationTypeName.NULL and canonical NULL scalar (red-dragon-v0l2)`.

---

## Task 2: `Const.type_expr` required + typed factories + `operands` fix

After this task, **`Const(...)` without `type_expr` raises `TypeError`** — this is the intended atomic break. The factory unit tests pass in isolation; the global suite goes red until producers are migrated (Tasks 5–9).

**Files:** `interpreter/instructions.py`, Test: `tests/unit/test_typed_const.py`

- [ ] **Step 1: Failing test** — create `tests/unit/test_typed_const.py`:

```python
# pyright: standard
from interpreter.instructions import Const, Label_, Return_
from interpreter.types.type_expr import scalar, NULL
from interpreter.constants import FoundationTypeName
from interpreter.cfg import build_cfg
from interpreter.registry import build_registry
from interpreter.run import execute_cfg
from interpreter.run_types import VMConfig
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.types.typed_value import unwrap


def _run(const_inst):
    instrs = [Label_(label=CodeLabel("entry")), const_inst,
              Return_(value_reg=const_inst.result_reg)]
    cfg = build_cfg(instrs)
    vm, _ = execute_cfg(cfg, "entry", build_registry(instrs, cfg), VMConfig(max_steps=10))
    return unwrap(vm.current_frame.registers.get(const_inst.result_reg))


def test_string_const_stays_string():
    c = Const.string(Register("%r"), "10")
    assert _run(c) == "10" and c.type_expr == scalar(FoundationTypeName.STRING)


def test_int_const_is_int():
    c = Const.int_(Register("%r"), 10)
    assert _run(c) == 10 and c.type_expr == scalar(FoundationTypeName.INT)


def test_null_const_has_null_type():
    c = Const.null_(Register("%r"))
    assert _run(c) is None and c.type_expr == NULL


def test_raw_const_requires_type_expr():
    import pytest
    with pytest.raises(TypeError):
        Const(result_reg=Register("%r"), value="x")  # no type_expr → error
```

- [ ] **Step 2: Run → FAIL** (`Const.string` missing; `Const(...)` still allowed).

- [ ] **Step 3:** Confirm the `TypeName` import path: `grep -rn "class TypeName" interpreter/`. Then in `interpreter/instructions.py` add imports (top, after existing):

```python
from interpreter.types.type_expr import (
    TypeExpr, scalar, NULL, FunctionType, metatype,
)
from interpreter.constants import FoundationTypeName
from interpreter.type_name import TypeName  # use the path found above
```

If importing `type_expr` into `instructions.py` creates a cycle, move these imports inside the factory classmethods (local import).

- [ ] **Step 4:** Replace the `Const` class (lines 201-214):

```python
@dataclass(frozen=True)
class Const(InstructionBase):
    """CONST: load a typed literal into a register.

    `value` is the real Python payload (int 0, str "10", True, None, or a label
    string for refs). `type_expr` is the authoritative, required type — the VM
    never re-infers it from `value`.
    """

    result_reg: Register = NO_REGISTER
    value: Any = ""
    type_expr: TypeExpr = field(kw_only=True)  # required: no default
    has_value: bool = True  # False only for a value-less const

    @property
    def opcode(self) -> Opcode:
        return Opcode.CONST

    @property
    def operands(self) -> list[Any]:
        return [self.value] if self.has_value else []

    @classmethod
    def int_(cls, result_reg: Register, n: int, **kw: Any) -> "Const":
        return cls(result_reg=result_reg, value=int(n),
                   type_expr=scalar(FoundationTypeName.INT), **kw)

    @classmethod
    def float_(cls, result_reg: Register, x: float, **kw: Any) -> "Const":
        return cls(result_reg=result_reg, value=float(x),
                   type_expr=scalar(FoundationTypeName.FLOAT), **kw)

    @classmethod
    def string(cls, result_reg: Register, s: str, **kw: Any) -> "Const":
        return cls(result_reg=result_reg, value=str(s),
                   type_expr=scalar(FoundationTypeName.STRING), **kw)

    @classmethod
    def bool_(cls, result_reg: Register, b: bool, **kw: Any) -> "Const":
        return cls(result_reg=result_reg, value=bool(b),
                   type_expr=scalar(FoundationTypeName.BOOL), **kw)

    @classmethod
    def null_(cls, result_reg: Register, **kw: Any) -> "Const":
        return cls(result_reg=result_reg, value=None, type_expr=NULL, **kw)

    @classmethod
    def func_ref(cls, result_reg: Register, label: str, **kw: Any) -> "Const":
        return cls(result_reg=result_reg, value=str(label),
                   type_expr=FunctionType((), scalar(FoundationTypeName.ANY)), **kw)

    @classmethod
    def class_ref(cls, result_reg: Register, label: str, **kw: Any) -> "Const":
        return cls(result_reg=result_reg, value=str(label),
                   type_expr=metatype(scalar(TypeName(str(label)))), **kw)
```

Confirm `field` is imported from `dataclasses` in this module (it uses `@dataclass`; add `from dataclasses import field` if not present). Confirm `FunctionType((), ...)` matches the actual `FunctionType` constructor signature (`grep -n "class FunctionType" -A6 interpreter/types/type_expr.py`); adjust arg shape if needed.

- [ ] **Step 5: Run the factory test → PASS** — `poetry run python -m pytest tests/unit/test_typed_const.py -p no:randomly -q`. (Global suite is now red — expected.)

- [ ] **Step 6: Commit** `feat(ir): Const requires TypeExpr; add typed factories (red-dragon-v0l2)`.

---

## Task 3: `_handle_const` typed-only + migrate the LLM `_const` builder & prompt

These land together because the `_const` builder is itself a `Const` construction site (now requires `type_expr`) and `_handle_const` must stop calling `_parse_const`. After this task no code path produces an untyped const.

**Files:** `interpreter/handlers/variables.py`, `interpreter/instructions.py` (`_const`), `interpreter/llm/llm_frontend.py`, Tests: `tests/unit/test_typed_const.py`, `tests/unit/llm/test_const_wire.py`

- [ ] **Step 1: Failing builder test** — create `tests/unit/llm/test_const_wire.py`:

```python
# pyright: standard
from interpreter.instructions import _const
from interpreter.types.type_expr import scalar, NULL
from interpreter.constants import FoundationTypeName


class _Raw:
    def __init__(self, result_reg, operands, literal_type, source_location=None):
        self.result_reg, self.operands = result_reg, operands
        self.literal_type, self.source_location = literal_type, source_location


def test_builder_string():
    c = _const(_Raw("%1", ["10"], "String"))
    assert c.value == "10" and c.type_expr == scalar(FoundationTypeName.STRING)


def test_builder_int():
    c = _const(_Raw("%1", ["10"], "Int"))
    assert c.value == 10 and c.type_expr == scalar(FoundationTypeName.INT)


def test_builder_null():
    assert _const(_Raw("%1", [], "Null")).type_expr == NULL
```

- [ ] **Step 2: Run → FAIL** (`_const` ignores `literal_type`).

- [ ] **Step 3:** Replace `_const` (`interpreter/instructions.py:1069`):

```python
def _const(inst: Any) -> Const:
    lit = getattr(inst, "literal_type", None)
    reg = inst.result_reg
    raw = inst.operands[0] if inst.operands else None
    sl = inst.source_location
    if lit == "Int":
        return Const.int_(reg, int(raw), source_location=sl)
    if lit == "Float":
        return Const.float_(reg, float(raw), source_location=sl)
    if lit == "String":
        return Const.string(reg, str(raw), source_location=sl)
    if lit == "Bool":
        return Const.bool_(reg, str(raw) == "True", source_location=sl)
    if lit == "Null":
        return Const.null_(reg, source_location=sl)
    if lit == "FuncRef":
        return Const.func_ref(reg, str(raw), source_location=sl)
    if lit == "ClassRef":
        return Const.class_ref(reg, str(raw), source_location=sl)
    raise ValueError(f"CONST missing/unknown literal_type: {lit!r}")
```

- [ ] **Step 4:** Rewrite `_handle_const` head (`interpreter/handlers/variables.py:49-50`) to use the typed value, with ref resolution keyed on `type_expr`:

```python
    val = t.value
    te = t.type_expr
    # Function reference: resolve label -> BoundFuncRef (closure capture preserved).
    if isinstance(te, FunctionType) and isinstance(val, str) and val in func_symbol_table:
        ...  # keep the existing closure-capture block, but gate it on FunctionType
    # Class reference: metatype -> ClassRef.
    elif _is_metatype(te) and isinstance(val, str) and val in class_symbol_table:
        val = class_symbol_table[val]
    return ExecutionResult.success(
        StateUpdate(
            register_writes={t.result_reg: TypedValue(value=val, type=te)},
            reasoning=f"const {val!r}:{te} → {t.result_reg}",
        )
    )
```

Remove the `_parse_const` import (line 28) and call. Import `FunctionType` from `type_expr`; add a small `_is_metatype(te)` helper (`isinstance(te, ParameterizedType) and te.name == "Type"`) or reuse an existing predicate (`grep -rn "metatype\|ParameterizedType" interpreter/types/type_expr.py`). Add `TypedValue` to the `typed_value` import.

- [ ] **Step 5:** Update the prompt in `interpreter/llm/llm_frontend.py`: document that every CONST carries `"literal_type"` (`Int`/`Float`/`String`/`Bool`/`Null`/`FuncRef`/`ClassRef`) with `operands:[value]` (unquoted string; label for refs). Update the worked examples (~lines 187-210).

- [ ] **Step 6: Run** `tests/unit/llm/test_const_wire.py` and `tests/unit/test_typed_const.py` → PASS. **Commit** `refactor(ir): typed _handle_const + literal_type wire format; drop _parse_const from handler (red-dragon-v0l2)`.

---

## Tasks 4–8: Migrate producers (one area per task; that area's tests green at end)

**Uniform transformation** (apply to every `Const(...)` / `const_to_reg(...)`; preserve `source_location=` and other kwargs via the factories' `**kw`):

| Old | New |
|-----|-----|
| `Const(result_reg=r, value="0")` / bare-digit string / python int | `Const.int_(r, 0)` |
| `Const(result_reg=r, value=str(i))` | `Const.int_(r, i)` |
| python float / float-string | `Const.float_(r, x)` |
| `value='"text"'` (quoted) or string literal | `Const.string(r, "text")` |
| `value="None"` | `Const.null_(r)` |
| `value="True"/"False"` | `Const.bool_(r, True/False)` |
| `"<function:..@label>"` | `Const.func_ref(r, "label")` |
| `"<class:..@label>"` | `Const.class_ref(r, "label")` |

Discovery: `grep -rnE "Const\(|const_to_reg\(" <area>`.

### Task 4: COBOL (`interpreter/cobol/`)
- [ ] **Step 1:** Replace `const_to_reg` in `interpreter/cobol/emit_context.py:142` to dispatch on payload type:

```python
    def const_to_reg(self, value: Any) -> Register:
        reg = self.fresh_reg()
        if isinstance(value, bool):
            inst = Const.bool_(reg, value)
        elif isinstance(value, int):
            inst = Const.int_(reg, value)
        elif isinstance(value, float):
            inst = Const.float_(reg, value)
        elif value is None:
            inst = Const.null_(reg)
        else:
            inst = Const.string(reg, str(value))
        self.emit_inst(inst)
        return reg
```

- [ ] **Step 2:** Delete `_status_const_reg` from `interpreter/cobol/lower_io.py`; its two call sites become `ctx.const_to_reg("10")` / `ctx.const_to_reg("23")` (now `Const.string`). Audit any `const_to_reg("<digits>")` that must be numeric (`grep -rnE 'const_to_reg\("[0-9]' interpreter/cobol/`) → pass an int. Migrate any direct `Const(...)` in `interpreter/cobol/`.
- [ ] **Step 3:** `poetry run python -m pytest tests/unit/cobol/ tests/integration/ -q` (env exported) → PASS. **Commit.**

### Task 5: Frontends batch 1 — `python`, `javascript`, `typescript`, `ruby`, `php`, `lua`
Per language dir: apply the table to every `Const(...)`; run `poetry run python -m pytest tests/ -k "<lang>" -q` → PASS; commit per language (`refactor(<lang>): typed Const literals (red-dragon-v0l2)`).

### Task 6: Frontends batch 2 — `java`, `kotlin`, `scala`, `csharp`, `go`, `rust`, `cpp`, `c`, `pascal`
Same procedure, per language; commit per language.

### Task 7: Shared layers — `interpreter/frontends/_base.py`, `interpreter/frontends/common/`
Apply the table (note `_base.py:1248` `value="1"` → `Const.int_(r, 1)`). Run the broad suite for affected languages; commit.

### Task 8: Consumers — `memory.py`, `calls.py`, `type_inference.py`, `registry.py`, `linker.py`, `executor.py`
- [ ] **Step 1:** `interpreter/types/type_inference.py` — read `inst.type_expr` instead of inferring a literal's type from `value`. Add a unit test: `INT` const → `Int`, `STRING` const → `String`.
- [ ] **Step 2:** `interpreter/handlers/memory.py:424` — replace `_parse_const(raw)` with the operand register's typed value (index/figurative). Test: indexed load/store with an `INT` const index.
- [ ] **Step 3:** `registry.py`, `project/linker.py` — audit `Const.value` reads (func/class label collection); key on `type_expr` being `FunctionType`/metatype. Behavior unchanged; add a linking test if absent.
- [ ] **Step 4:** Remove unused `_parse_const` imports in `calls.py` and the `executor.py` re-export.
- [ ] **Step 5:** Full suite (minus nist/external) → PASS. **Commit.**

---

## Task 9: Delete `_parse_const`; confirm fully typed

**Files:** `interpreter/vm/vm.py`, Test: `tests/unit/test_typed_const.py`

- [ ] **Step 1:** Add guard test:

```python
def test_parse_const_is_gone():
    import interpreter.vm.vm as vm
    assert not hasattr(vm, "_parse_const")
```

- [ ] **Step 2:** Delete `_parse_const` (and `CanonicalLiteral`-decoding helpers it solely used, if any) from `interpreter/vm/vm.py`. `grep -rn "_parse_const" interpreter/` must return nothing.

- [ ] **Step 3: Full suite green** — `export PROLEAP_BRIDGE_JAR=...; poetry run python -m pytest -q -m 'not external and not nist'` → all pass. Then run NIST sanity: `poetry run python -m pytest tests/nist/ -m nist -q` → unchanged (17 pass / behavior identical; SQ102A still completes at high steps).

- [ ] **Step 4: Commit + close**

```bash
git add -A
git commit -m "refactor(ir): delete _parse_const; Const.type_expr fully required (red-dragon-v0l2)"
bd close red-dragon-v0l2 --reason "Const carries a required, non-optional TypeExpr (kw-only, no default); null literal typed Null; _parse_const deleted; all producers + LLM wire path + consumers migrated; suite green."
```

---

## Self-review notes
- **No default / non-optional:** `type_expr` is `field(kw_only=True)` with no default from Task 2 onward — there is never an `UNKNOWN` sentinel or `None`. Raw `Const(...)` without it raises `TypeError` (Task 2 test asserts this). This matches the spec's atomic decision exactly; the only consequence is the *global* suite being red between Tasks 2 and 9, which is the accepted tradeoff.
- **Spec coverage:** Null type (T1) ✓; required field + factories + `operands` fix (T2) ✓; `_handle_const` typed + LLM wire `literal_type` (T3) ✓; COBOL incl. `_status_const_reg` removal (T4) ✓; all 15 frontends (T5–6) ✓; shared layers (T7) ✓; consumers memory/calls/type_inference/registry/linker/executor (T8) ✓; delete `_parse_const` (T9) ✓.
- **Type consistency:** factories `int_/float_/string/bool_/null_/func_ref/class_ref` referenced identically T2–T8; `NULL`/`scalar(FoundationTypeName.X)` consistent with T1.
- **Verify-before-code flags:** `TypeName` import path (T2 S3), `FunctionType`/`metatype` constructor shapes (T2 S4), `field(kw_only=True)` ordering with `InstructionBase` (T2 S4), and `_is_metatype` predicate (T3 S4) are each flagged to confirm against real code, not assumed.
