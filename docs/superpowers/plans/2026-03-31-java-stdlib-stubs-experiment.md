# Java Stdlib Stubs — Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained experiment that implements Java stdlib contracts as hand-written RedDragon IR `ModuleUnit`s, executes them through the VM via `run_linked()`, and confirms concrete values replace SYMBOLIC for stdlib method calls.

**Architecture:** Each stdlib class is a `ModuleUnit` whose IR mirrors the exact structure the Java frontend produces for class definitions: `class_X_N`/`end_class_X_N` boundary labels, hoisted method bodies declared via `Branch`/`Label_`/`Return_`, and `Const(value="func_label") + DeclVar(method_name)` pairs that `_scan_classes()` detects to build `class_methods`. The `ExportTable` has both `functions` (unqualified `FuncName` → method label) and `classes` (`ClassName` → class body label). Tests compile minimal Java programs via `JavaFrontend`, inject stdlib `ModuleUnit`s at link time via `link_modules()`, execute via `run_linked()`, and assert concrete values.

**Tech Stack:** `interpreter/` (read-only library), `interpreter.frontends.java.JavaFrontend`, `interpreter.project.linker.link_modules`, `interpreter.run.run_linked`, `pytest`, `poetry`

---

## Calling Convention Summary (from investigation)

These are facts confirmed by running the Java frontend — all stub IR must follow these patterns exactly.

**Static method call** (`Math.sqrt(9.0)`):
```
%0 = const 9.0
%1 = load_var Math        ← Math is a ClassRef variable in scope
%2 = call_method %1 sqrt %0   ← unqualified method name, no "Math." prefix
```

**Instance method call** (`list.add(42)`):
```
%0 = call_method %list add %42   ← receiver obj, unqualified method name, args
```

**Constructor** (`new ArrayList()`):
```
%0 = call_ctor ArrayList   ← CallCtorFunction, looks up ArrayList ClassRef in scope,
                               then calls class_methods[ClassName("ArrayList")][FuncName("__init__")]
```

**Class IR structure** (what _scan_classes() expects):
```
entry:
branch end_class_Foo_1      ← skip class body
class_Foo_0:                ← class start label → registered in classes dict
end_class_Foo_1:            ← class end (in_class state persists after this)
%0 = const class_Foo_0      ← declares Foo as ClassRef variable
decl_var Foo %0
branch end_methodA_3        ← skip method body
func_methodA_2:             ← method body
  ... IR ...
  return %r
end_methodA_3:
%N = const func_methodA_2   ← Const value in func_symbol_table → registered as class method
decl_var methodA %N
```

**ExportTable must have:**
- `functions`: `{FuncName("methodA"): CodeLabel("func_methodA_2"), ...}` — unqualified names
- `classes`: `{ClassName("Foo"): CodeLabel("class_Foo_0")}` — class body label

**Register numbering**: global within a ModuleUnit — increment a counter across all instructions in all function bodies. Do not restart at %0 for each method.

**String literals**: `String s = "hello"` lowers to `const "hello"` (plain Python str). String stub methods won't dispatch on plain strings. Tests must use `new String("hello")` to get a heap object with `type_hint="String"`.

---

## Task 1: Scaffold + investigate (DONE)

Completed in prior session. The scaffold exists at `experiments/java_stdlib/` with `conftest.py` providing `run_with_stdlib()` and `locals_of()`.

**Key correction from investigation**: `JavaFrontend()` cannot be instantiated directly — use `get_deterministic_frontend(Language.JAVA)` from `interpreter.run`. `unwrap_locals` is in `interpreter.types.typed_value`, not `interpreter.run`. `VMState` is in `interpreter.vm.vm_types`.

The conftest has been committed with these corrections applied.

---

## Task 2: java.lang.Math stubs

**Files:**
- Create: `experiments/java_stdlib/stubs/java_lang_math.py`
- Create: `experiments/java_stdlib/tests/test_java_lang_math.py`

- [ ] **Step 1: Write failing export test**

`experiments/java_stdlib/tests/test_java_lang_math.py`:

```python
from interpreter.class_name import ClassName
from interpreter.func_name import FuncName
from experiments.java_stdlib.stubs.java_lang_math import MATH_MODULE


class TestMathModuleExports:
    def test_exports_sqrt(self):
        assert FuncName("sqrt") in MATH_MODULE.exports.functions

    def test_exports_abs(self):
        assert FuncName("abs") in MATH_MODULE.exports.functions

    def test_exports_pow(self):
        assert FuncName("pow") in MATH_MODULE.exports.functions

    def test_exports_min(self):
        assert FuncName("min") in MATH_MODULE.exports.functions

    def test_exports_max(self):
        assert FuncName("max") in MATH_MODULE.exports.functions

    def test_exports_math_class(self):
        assert ClassName("Math") in MATH_MODULE.exports.classes
```

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_lang_math.py -v
```

Expected: `ImportError` (module doesn't exist yet)

- [ ] **Step 3: Implement Math stub**

`experiments/java_stdlib/stubs/java_lang_math.py`:

```python
from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    Branch,
    CallFunction,
    Const,
    DeclVar,
    Label_,
    LoadVar,
    Return_,
    Symbolic,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register
from interpreter.var_name import VarName

# ── Labels ───────────────────────────────────────────────────────────────────
_CLS        = "class_Math_0"
_END_CLS    = "end_class_Math_1"
_SQRT_F     = "func_sqrt_2"
_SQRT_END   = "end_sqrt_3"
_ABS_F      = "func_abs_4"
_ABS_END    = "end_abs_5"
_POW_F      = "func_pow_6"
_POW_END    = "end_pow_7"
_MIN_F      = "func_min_8"
_MIN_END    = "end_min_9"
_MAX_F      = "func_max_10"
_MAX_END    = "end_max_11"

# ── IR ───────────────────────────────────────────────────────────────────────
# Register numbers are global across the whole module — never restart at %0.
MATH_IR = (
    # ── top-level: declare Math class ────────────────────────────────────────
    Label_(label=CodeLabel("entry_Math")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    Const(result_reg=Register("%0"), value=_CLS),
    DeclVar(name=VarName("Math"), value_reg=Register("%0")),

    # ── sqrt(x) → x ** 0.5 ──────────────────────────────────────────────────
    Branch(label=CodeLabel(_SQRT_END)),
    Label_(label=CodeLabel(_SQRT_F)),
    Symbolic(result_reg=Register("%1"), hint="param:x"),
    DeclVar(name=VarName("x"), value_reg=Register("%1")),
    LoadVar(result_reg=Register("%2"), name=VarName("x")),
    Const(result_reg=Register("%3"), value="0.5"),
    Binop(result_reg=Register("%4"), operator=BinopKind.POWER, left=Register("%2"), right=Register("%3")),
    Return_(value_reg=Register("%4")),
    Label_(label=CodeLabel(_SQRT_END)),
    Const(result_reg=Register("%5"), value=_SQRT_F),
    DeclVar(name=VarName("sqrt"), value_reg=Register("%5")),

    # ── abs(x) → builtin abs ────────────────────────────────────────────────
    Branch(label=CodeLabel(_ABS_END)),
    Label_(label=CodeLabel(_ABS_F)),
    Symbolic(result_reg=Register("%6"), hint="param:x"),
    DeclVar(name=VarName("x"), value_reg=Register("%6")),
    LoadVar(result_reg=Register("%7"), name=VarName("x")),
    CallFunction(result_reg=Register("%8"), func_name=FuncName("abs"), args=(Register("%7"),)),
    Return_(value_reg=Register("%8")),
    Label_(label=CodeLabel(_ABS_END)),
    Const(result_reg=Register("%9"), value=_ABS_F),
    DeclVar(name=VarName("abs"), value_reg=Register("%9")),

    # ── pow(x, y) → x ** y ──────────────────────────────────────────────────
    Branch(label=CodeLabel(_POW_END)),
    Label_(label=CodeLabel(_POW_F)),
    Symbolic(result_reg=Register("%10"), hint="param:x"),
    DeclVar(name=VarName("x"), value_reg=Register("%10")),
    Symbolic(result_reg=Register("%11"), hint="param:y"),
    DeclVar(name=VarName("y"), value_reg=Register("%11")),
    LoadVar(result_reg=Register("%12"), name=VarName("x")),
    LoadVar(result_reg=Register("%13"), name=VarName("y")),
    Binop(result_reg=Register("%14"), operator=BinopKind.POWER, left=Register("%12"), right=Register("%13")),
    Return_(value_reg=Register("%14")),
    Label_(label=CodeLabel(_POW_END)),
    Const(result_reg=Register("%15"), value=_POW_F),
    DeclVar(name=VarName("pow"), value_reg=Register("%15")),

    # ── min(x, y) → builtin min ─────────────────────────────────────────────
    Branch(label=CodeLabel(_MIN_END)),
    Label_(label=CodeLabel(_MIN_F)),
    Symbolic(result_reg=Register("%16"), hint="param:x"),
    DeclVar(name=VarName("x"), value_reg=Register("%16")),
    Symbolic(result_reg=Register("%17"), hint="param:y"),
    DeclVar(name=VarName("y"), value_reg=Register("%17")),
    LoadVar(result_reg=Register("%18"), name=VarName("x")),
    LoadVar(result_reg=Register("%19"), name=VarName("y")),
    CallFunction(result_reg=Register("%20"), func_name=FuncName("min"), args=(Register("%18"), Register("%19"))),
    Return_(value_reg=Register("%20")),
    Label_(label=CodeLabel(_MIN_END)),
    Const(result_reg=Register("%21"), value=_MIN_F),
    DeclVar(name=VarName("min"), value_reg=Register("%21")),

    # ── max(x, y) → builtin max ─────────────────────────────────────────────
    Branch(label=CodeLabel(_MAX_END)),
    Label_(label=CodeLabel(_MAX_F)),
    Symbolic(result_reg=Register("%22"), hint="param:x"),
    DeclVar(name=VarName("x"), value_reg=Register("%22")),
    Symbolic(result_reg=Register("%23"), hint="param:y"),
    DeclVar(name=VarName("y"), value_reg=Register("%23")),
    LoadVar(result_reg=Register("%24"), name=VarName("x")),
    LoadVar(result_reg=Register("%25"), name=VarName("y")),
    CallFunction(result_reg=Register("%26"), func_name=FuncName("max"), args=(Register("%24"), Register("%25"))),
    Return_(value_reg=Register("%26")),
    Label_(label=CodeLabel(_MAX_END)),
    Const(result_reg=Register("%27"), value=_MAX_F),
    DeclVar(name=VarName("max"), value_reg=Register("%27")),
)

MATH_MODULE = ModuleUnit(
    path=Path("java/lang/Math.java"),
    language=Language.JAVA,
    ir=MATH_IR,
    exports=ExportTable(
        functions={
            FuncName("sqrt"): CodeLabel(_SQRT_F),
            FuncName("abs"):  CodeLabel(_ABS_F),
            FuncName("pow"):  CodeLabel(_POW_F),
            FuncName("min"):  CodeLabel(_MIN_F),
            FuncName("max"):  CodeLabel(_MAX_F),
        },
        classes={
            ClassName("Math"): CodeLabel(_CLS),
        },
    ),
    imports=(),
)
```

- [ ] **Step 4: Run export tests — confirm pass**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_lang_math.py::TestMathModuleExports -v
```

Expected: 6 passed

- [ ] **Step 5: Write execution tests**

Add to `experiments/java_stdlib/tests/test_java_lang_math.py`:

```python
from pathlib import Path
from interpreter.var_name import VarName
from experiments.java_stdlib.stubs.java_lang_math import MATH_MODULE
from experiments.java_stdlib.tests.conftest import run_with_stdlib, locals_of

_STDLIB = {Path("java/lang/Math.java"): MATH_MODULE}


class TestMathExecution:
    def test_sqrt_nine(self):
        vm = run_with_stdlib("double x = Math.sqrt(9.0);", _STDLIB)
        assert locals_of(vm)[VarName("x")] == 3.0

    def test_abs_negative(self):
        vm = run_with_stdlib("double x = Math.abs(-5.0);", _STDLIB)
        assert locals_of(vm)[VarName("x")] == 5.0

    def test_pow_two_cubed(self):
        vm = run_with_stdlib("double x = Math.pow(2.0, 3.0);", _STDLIB)
        assert locals_of(vm)[VarName("x")] == 8.0

    def test_min_picks_smaller(self):
        vm = run_with_stdlib("double x = Math.min(3.0, 7.0);", _STDLIB)
        assert locals_of(vm)[VarName("x")] == 3.0

    def test_max_picks_larger(self):
        vm = run_with_stdlib("double x = Math.max(3.0, 7.0);", _STDLIB)
        assert locals_of(vm)[VarName("x")] == 7.0
```

- [ ] **Step 6: Run all Math tests**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_lang_math.py -v
```

Expected: 11 passed. If execution tests fail because the stub functions aren't being found by the VM (i.e. still returning SYMBOLIC), debug by checking:
1. That `class_methods` contains `ClassName("Math")` after linking — add a temporary assertion in conftest
2. That the `Const` value strings match the `func_symbol_table` keys after namespacing

- [ ] **Step 7: Commit**

```bash
bd backup
git add experiments/java_stdlib/stubs/java_lang_math.py experiments/java_stdlib/tests/test_java_lang_math.py
git commit -m "feat(experiment): add java.lang.Math IR stubs with execution tests"
```

---

## Task 3: java.lang.String stubs

**Files:**
- Create: `experiments/java_stdlib/stubs/java_lang_string.py`
- Create: `experiments/java_stdlib/tests/test_java_lang_string.py`

**Important**: Java string literals (`"hello"`) lower to plain Python strings (not heap objects). String stub methods only work on heap `String` objects created via `new String("hello")`. Tests must use `new String(...)` — not string literals — to exercise these stubs.

String methods load the internal `value` field (a Python str), call the corresponding Python string method, and wrap the result in a new `String` heap object.

- [ ] **Step 1: Write failing export test**

`experiments/java_stdlib/tests/test_java_lang_string.py`:

```python
from interpreter.class_name import ClassName
from interpreter.func_name import FuncName
from experiments.java_stdlib.stubs.java_lang_string import STRING_MODULE


class TestStringModuleExports:
    def test_exports_to_upper_case(self):
        assert FuncName("toUpperCase") in STRING_MODULE.exports.functions

    def test_exports_to_lower_case(self):
        assert FuncName("toLowerCase") in STRING_MODULE.exports.functions

    def test_exports_length(self):
        assert FuncName("length") in STRING_MODULE.exports.functions

    def test_exports_trim(self):
        assert FuncName("trim") in STRING_MODULE.exports.functions

    def test_exports_contains(self):
        assert FuncName("contains") in STRING_MODULE.exports.functions

    def test_exports_init(self):
        assert FuncName("__init__") in STRING_MODULE.exports.functions

    def test_exports_string_class(self):
        assert ClassName("String") in STRING_MODULE.exports.classes
```

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_lang_string.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement String stub**

`experiments/java_stdlib/stubs/java_lang_string.py`:

```python
from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Branch,
    CallFunction,
    CallMethod,
    Const,
    DeclVar,
    Label_,
    LoadField,
    LoadVar,
    NewObject,
    Return_,
    StoreField,
    Symbolic,
)
from interpreter.ir import CodeLabel
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register
from interpreter.var_name import VarName

_VALUE = FieldName("value")

_CLS         = "class_String_0"
_END_CLS     = "end_class_String_1"
_INIT_F      = "func___init___2"
_INIT_END    = "end___init___3"
_UPPER_F     = "func_toUpperCase_4"
_UPPER_END   = "end_toUpperCase_5"
_LOWER_F     = "func_toLowerCase_6"
_LOWER_END   = "end_toLowerCase_7"
_LEN_F       = "func_length_8"
_LEN_END     = "end_length_9"
_TRIM_F      = "func_trim_10"
_TRIM_END    = "end_trim_11"
_CONTAINS_F  = "func_contains_12"
_CONTAINS_END = "end_contains_13"

STRING_IR = (
    # ── declare String class ─────────────────────────────────────────────────
    Label_(label=CodeLabel("entry_String")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    Const(result_reg=Register("%0"), value=_CLS),
    DeclVar(name=VarName("String"), value_reg=Register("%0")),

    # ── __init__(this, value) — store value field ─────────────────────────────
    Branch(label=CodeLabel(_INIT_END)),
    Label_(label=CodeLabel(_INIT_F)),
    Symbolic(result_reg=Register("%1"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%1")),
    Symbolic(result_reg=Register("%2"), hint="param:value"),
    DeclVar(name=VarName("value"), value_reg=Register("%2")),
    LoadVar(result_reg=Register("%3"), name=VarName("this")),
    LoadVar(result_reg=Register("%4"), name=VarName("value")),
    StoreField(obj_reg=Register("%3"), field_name=_VALUE, value_reg=Register("%4")),
    Const(result_reg=Register("%5"), value="None"),
    Return_(value_reg=Register("%5")),
    Label_(label=CodeLabel(_INIT_END)),
    Const(result_reg=Register("%6"), value=_INIT_F),
    DeclVar(name=VarName("__init__"), value_reg=Register("%6")),

    # ── toUpperCase() → new String(this.value.upper()) ───────────────────────
    Branch(label=CodeLabel(_UPPER_END)),
    Label_(label=CodeLabel(_UPPER_F)),
    Symbolic(result_reg=Register("%7"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%7")),
    LoadVar(result_reg=Register("%8"), name=VarName("this")),
    LoadField(result_reg=Register("%9"), obj_reg=Register("%8"), field_name=_VALUE),
    CallMethod(result_reg=Register("%10"), obj_reg=Register("%9"), method_name=FuncName("upper"), args=()),
    NewObject(result_reg=Register("%11"), type_hint="String"),
    StoreField(obj_reg=Register("%11"), field_name=_VALUE, value_reg=Register("%10")),
    Return_(value_reg=Register("%11")),
    Label_(label=CodeLabel(_UPPER_END)),
    Const(result_reg=Register("%12"), value=_UPPER_F),
    DeclVar(name=VarName("toUpperCase"), value_reg=Register("%12")),

    # ── toLowerCase() → new String(this.value.lower()) ───────────────────────
    Branch(label=CodeLabel(_LOWER_END)),
    Label_(label=CodeLabel(_LOWER_F)),
    Symbolic(result_reg=Register("%13"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%13")),
    LoadVar(result_reg=Register("%14"), name=VarName("this")),
    LoadField(result_reg=Register("%15"), obj_reg=Register("%14"), field_name=_VALUE),
    CallMethod(result_reg=Register("%16"), obj_reg=Register("%15"), method_name=FuncName("lower"), args=()),
    NewObject(result_reg=Register("%17"), type_hint="String"),
    StoreField(obj_reg=Register("%17"), field_name=_VALUE, value_reg=Register("%16")),
    Return_(value_reg=Register("%17")),
    Label_(label=CodeLabel(_LOWER_END)),
    Const(result_reg=Register("%18"), value=_LOWER_F),
    DeclVar(name=VarName("toLowerCase"), value_reg=Register("%18")),

    # ── length() → len(this.value) ────────────────────────────────────────────
    Branch(label=CodeLabel(_LEN_END)),
    Label_(label=CodeLabel(_LEN_F)),
    Symbolic(result_reg=Register("%19"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%19")),
    LoadVar(result_reg=Register("%20"), name=VarName("this")),
    LoadField(result_reg=Register("%21"), obj_reg=Register("%20"), field_name=_VALUE),
    CallFunction(result_reg=Register("%22"), func_name=FuncName("len"), args=(Register("%21"),)),
    Return_(value_reg=Register("%22")),
    Label_(label=CodeLabel(_LEN_END)),
    Const(result_reg=Register("%23"), value=_LEN_F),
    DeclVar(name=VarName("length"), value_reg=Register("%23")),

    # ── trim() → new String(this.value.strip()) ──────────────────────────────
    Branch(label=CodeLabel(_TRIM_END)),
    Label_(label=CodeLabel(_TRIM_F)),
    Symbolic(result_reg=Register("%24"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%24")),
    LoadVar(result_reg=Register("%25"), name=VarName("this")),
    LoadField(result_reg=Register("%26"), obj_reg=Register("%25"), field_name=_VALUE),
    CallMethod(result_reg=Register("%27"), obj_reg=Register("%26"), method_name=FuncName("strip"), args=()),
    NewObject(result_reg=Register("%28"), type_hint="String"),
    StoreField(obj_reg=Register("%28"), field_name=_VALUE, value_reg=Register("%27")),
    Return_(value_reg=Register("%28")),
    Label_(label=CodeLabel(_TRIM_END)),
    Const(result_reg=Register("%29"), value=_TRIM_F),
    DeclVar(name=VarName("trim"), value_reg=Register("%29")),

    # ── contains(s) → this.value.__contains__(s.value) ───────────────────────
    Branch(label=CodeLabel(_CONTAINS_END)),
    Label_(label=CodeLabel(_CONTAINS_F)),
    Symbolic(result_reg=Register("%30"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%30")),
    Symbolic(result_reg=Register("%31"), hint="param:s"),
    DeclVar(name=VarName("s"), value_reg=Register("%31")),
    LoadVar(result_reg=Register("%32"), name=VarName("this")),
    LoadField(result_reg=Register("%33"), obj_reg=Register("%32"), field_name=_VALUE),
    LoadVar(result_reg=Register("%34"), name=VarName("s")),
    LoadField(result_reg=Register("%35"), obj_reg=Register("%34"), field_name=_VALUE),
    CallMethod(result_reg=Register("%36"), obj_reg=Register("%33"), method_name=FuncName("__contains__"), args=(Register("%35"),)),
    Return_(value_reg=Register("%36")),
    Label_(label=CodeLabel(_CONTAINS_END)),
    Const(result_reg=Register("%37"), value=_CONTAINS_F),
    DeclVar(name=VarName("contains"), value_reg=Register("%37")),
)

STRING_MODULE = ModuleUnit(
    path=Path("java/lang/String.java"),
    language=Language.JAVA,
    ir=STRING_IR,
    exports=ExportTable(
        functions={
            FuncName("__init__"):    CodeLabel(_INIT_F),
            FuncName("toUpperCase"): CodeLabel(_UPPER_F),
            FuncName("toLowerCase"): CodeLabel(_LOWER_F),
            FuncName("length"):      CodeLabel(_LEN_F),
            FuncName("trim"):        CodeLabel(_TRIM_F),
            FuncName("contains"):    CodeLabel(_CONTAINS_F),
        },
        classes={
            ClassName("String"): CodeLabel(_CLS),
        },
    ),
    imports=(),
)
```

- [ ] **Step 4: Run export tests — confirm pass**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_lang_string.py::TestStringModuleExports -v
```

Expected: 7 passed

- [ ] **Step 5: Write execution tests**

Add to `experiments/java_stdlib/tests/test_java_lang_string.py`:

```python
from pathlib import Path
from interpreter.field_name import FieldName
from interpreter.var_name import VarName
from experiments.java_stdlib.stubs.java_lang_string import STRING_MODULE
from experiments.java_stdlib.tests.conftest import run_with_stdlib, locals_of

_STDLIB = {Path("java/lang/String.java"): STRING_MODULE}
_VALUE = FieldName("value")


class TestStringExecution:
    def test_length(self):
        vm = run_with_stdlib(
            'String s = new String("hello"); int n = s.length();',
            _STDLIB,
        )
        assert locals_of(vm)[VarName("n")] == 5

    def test_to_upper_case(self):
        vm = run_with_stdlib(
            'String s = new String("hello"); String u = s.toUpperCase();',
            _STDLIB,
        )
        result_obj = locals_of(vm)[VarName("u")]
        # u is a heap String object; access its value field via heap
        assert result_obj.fields[_VALUE] == "HELLO"

    def test_trim(self):
        vm = run_with_stdlib(
            'String s = new String("  hi  "); String t = s.trim();',
            _STDLIB,
        )
        result_obj = locals_of(vm)[VarName("t")]
        assert result_obj.fields[_VALUE] == "hi"
```

Note: `result_obj.fields[_VALUE]` — adjust to the actual heap object field access API if it differs. For methods that return a plain int/bool (like `length`, `contains`), `locals_of(vm)[VarName("n")]` returns a plain Python value. For methods that return a new String object, access the heap field.

- [ ] **Step 6: Run all String tests**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_lang_string.py -v
```

Expected: all passed.

- [ ] **Step 7: Commit**

```bash
bd backup
git add experiments/java_stdlib/stubs/java_lang_string.py experiments/java_stdlib/tests/test_java_lang_string.py
git commit -m "feat(experiment): add java.lang.String IR stubs with execution tests"
```

---

## Task 4: java.util.ArrayList stubs

**Files:**
- Create: `experiments/java_stdlib/stubs/java_util_array_list.py`
- Create: `experiments/java_stdlib/tests/test_java_util_array_list.py`

Constructor (`__init__`) initializes a `elements` field as a Python list (via `NewArray`). Methods operate on that field.

- [ ] **Step 1: Write failing export test**

`experiments/java_stdlib/tests/test_java_util_array_list.py`:

```python
from interpreter.class_name import ClassName
from interpreter.func_name import FuncName
from experiments.java_stdlib.stubs.java_util_array_list import ARRAY_LIST_MODULE


class TestArrayListExports:
    def test_exports_init(self):
        assert FuncName("__init__") in ARRAY_LIST_MODULE.exports.functions

    def test_exports_add(self):
        assert FuncName("add") in ARRAY_LIST_MODULE.exports.functions

    def test_exports_get(self):
        assert FuncName("get") in ARRAY_LIST_MODULE.exports.functions

    def test_exports_size(self):
        assert FuncName("size") in ARRAY_LIST_MODULE.exports.functions

    def test_exports_is_empty(self):
        assert FuncName("isEmpty") in ARRAY_LIST_MODULE.exports.functions

    def test_exports_class(self):
        assert ClassName("ArrayList") in ARRAY_LIST_MODULE.exports.classes
```

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_util_array_list.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement ArrayList stub**

`experiments/java_stdlib/stubs/java_util_array_list.py`:

```python
from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    Branch,
    CallFunction,
    CallMethod,
    Const,
    DeclVar,
    Label_,
    LoadField,
    LoadIndex,
    LoadVar,
    NewArray,
    Return_,
    StoreField,
    Symbolic,
)
from interpreter.instructions import NO_REGISTER
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register
from interpreter.var_name import VarName

_ELEMENTS = FieldName("elements")

_CLS         = "class_ArrayList_0"
_END_CLS     = "end_class_ArrayList_1"
_INIT_F      = "func___init___2"
_INIT_END    = "end___init___3"
_ADD_F       = "func_add_4"
_ADD_END     = "end_add_5"
_GET_F       = "func_get_6"
_GET_END     = "end_get_7"
_SIZE_F      = "func_size_8"
_SIZE_END    = "end_size_9"
_EMPTY_F     = "func_isEmpty_10"
_EMPTY_END   = "end_isEmpty_11"

ARRAY_LIST_IR = (
    # ── declare ArrayList class ───────────────────────────────────────────────
    Label_(label=CodeLabel("entry_ArrayList")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    Const(result_reg=Register("%0"), value=_CLS),
    DeclVar(name=VarName("ArrayList"), value_reg=Register("%0")),

    # ── __init__(this) — initialise self.elements = [] ────────────────────────
    Branch(label=CodeLabel(_INIT_END)),
    Label_(label=CodeLabel(_INIT_F)),
    Symbolic(result_reg=Register("%1"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%1")),
    NewArray(result_reg=Register("%2"), type_hint="list", size_reg=NO_REGISTER),
    LoadVar(result_reg=Register("%3"), name=VarName("this")),
    StoreField(obj_reg=Register("%3"), field_name=_ELEMENTS, value_reg=Register("%2")),
    Const(result_reg=Register("%4"), value="None"),
    Return_(value_reg=Register("%4")),
    Label_(label=CodeLabel(_INIT_END)),
    Const(result_reg=Register("%5"), value=_INIT_F),
    DeclVar(name=VarName("__init__"), value_reg=Register("%5")),

    # ── add(this, element) → append to elements, return True ─────────────────
    Branch(label=CodeLabel(_ADD_END)),
    Label_(label=CodeLabel(_ADD_F)),
    Symbolic(result_reg=Register("%6"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%6")),
    Symbolic(result_reg=Register("%7"), hint="param:element"),
    DeclVar(name=VarName("element"), value_reg=Register("%7")),
    LoadVar(result_reg=Register("%8"), name=VarName("this")),
    LoadField(result_reg=Register("%9"), obj_reg=Register("%8"), field_name=_ELEMENTS),
    LoadVar(result_reg=Register("%10"), name=VarName("element")),
    CallMethod(result_reg=Register("%11"), obj_reg=Register("%9"), method_name=FuncName("append"), args=(Register("%10"),)),
    Const(result_reg=Register("%12"), value="True"),
    Return_(value_reg=Register("%12")),
    Label_(label=CodeLabel(_ADD_END)),
    Const(result_reg=Register("%13"), value=_ADD_F),
    DeclVar(name=VarName("add"), value_reg=Register("%13")),

    # ── get(this, index) → elements[index] ────────────────────────────────────
    Branch(label=CodeLabel(_GET_END)),
    Label_(label=CodeLabel(_GET_F)),
    Symbolic(result_reg=Register("%14"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%14")),
    Symbolic(result_reg=Register("%15"), hint="param:index"),
    DeclVar(name=VarName("index"), value_reg=Register("%15")),
    LoadVar(result_reg=Register("%16"), name=VarName("this")),
    LoadField(result_reg=Register("%17"), obj_reg=Register("%16"), field_name=_ELEMENTS),
    LoadVar(result_reg=Register("%18"), name=VarName("index")),
    LoadIndex(result_reg=Register("%19"), arr_reg=Register("%17"), index_reg=Register("%18")),
    Return_(value_reg=Register("%19")),
    Label_(label=CodeLabel(_GET_END)),
    Const(result_reg=Register("%20"), value=_GET_F),
    DeclVar(name=VarName("get"), value_reg=Register("%20")),

    # ── size(this) → len(elements) ────────────────────────────────────────────
    Branch(label=CodeLabel(_SIZE_END)),
    Label_(label=CodeLabel(_SIZE_F)),
    Symbolic(result_reg=Register("%21"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%21")),
    LoadVar(result_reg=Register("%22"), name=VarName("this")),
    LoadField(result_reg=Register("%23"), obj_reg=Register("%22"), field_name=_ELEMENTS),
    CallFunction(result_reg=Register("%24"), func_name=FuncName("len"), args=(Register("%23"),)),
    Return_(value_reg=Register("%24")),
    Label_(label=CodeLabel(_SIZE_END)),
    Const(result_reg=Register("%25"), value=_SIZE_F),
    DeclVar(name=VarName("size"), value_reg=Register("%25")),

    # ── isEmpty(this) → len(elements) == 0 ────────────────────────────────────
    Branch(label=CodeLabel(_EMPTY_END)),
    Label_(label=CodeLabel(_EMPTY_F)),
    Symbolic(result_reg=Register("%26"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%26")),
    LoadVar(result_reg=Register("%27"), name=VarName("this")),
    LoadField(result_reg=Register("%28"), obj_reg=Register("%27"), field_name=_ELEMENTS),
    CallFunction(result_reg=Register("%29"), func_name=FuncName("len"), args=(Register("%28"),)),
    Const(result_reg=Register("%30"), value="0"),
    Binop(result_reg=Register("%31"), operator=BinopKind.EQ, left=Register("%29"), right=Register("%30")),
    Return_(value_reg=Register("%31")),
    Label_(label=CodeLabel(_EMPTY_END)),
    Const(result_reg=Register("%32"), value=_EMPTY_F),
    DeclVar(name=VarName("isEmpty"), value_reg=Register("%32")),
)

ARRAY_LIST_MODULE = ModuleUnit(
    path=Path("java/util/ArrayList.java"),
    language=Language.JAVA,
    ir=ARRAY_LIST_IR,
    exports=ExportTable(
        functions={
            FuncName("__init__"): CodeLabel(_INIT_F),
            FuncName("add"):      CodeLabel(_ADD_F),
            FuncName("get"):      CodeLabel(_GET_F),
            FuncName("size"):     CodeLabel(_SIZE_F),
            FuncName("isEmpty"):  CodeLabel(_EMPTY_F),
        },
        classes={
            ClassName("ArrayList"): CodeLabel(_CLS),
        },
    ),
    imports=(),
)
```

- [ ] **Step 4: Run export tests — confirm pass**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_util_array_list.py::TestArrayListExports -v
```

Expected: 6 passed

- [ ] **Step 5: Write execution tests**

Add to `experiments/java_stdlib/tests/test_java_util_array_list.py`:

```python
from pathlib import Path
from interpreter.var_name import VarName
from experiments.java_stdlib.stubs.java_util_array_list import ARRAY_LIST_MODULE
from experiments.java_stdlib.tests.conftest import run_with_stdlib, locals_of

_STDLIB = {Path("java/util/ArrayList.java"): ARRAY_LIST_MODULE}
_SRC = """
import java.util.ArrayList;
ArrayList list = new ArrayList();
list.add(42);
list.add(99);
int first = list.get(0);
int second = list.get(1);
int sz = list.size();
"""


class TestArrayListExecution:
    def test_get_first_element(self):
        vm = run_with_stdlib(_SRC, _STDLIB)
        assert locals_of(vm)[VarName("first")] == 42

    def test_get_second_element(self):
        vm = run_with_stdlib(_SRC, _STDLIB)
        assert locals_of(vm)[VarName("second")] == 99

    def test_size_after_two_adds(self):
        vm = run_with_stdlib(_SRC, _STDLIB)
        assert locals_of(vm)[VarName("sz")] == 2

    def test_is_empty_on_fresh_list(self):
        vm = run_with_stdlib(
            "import java.util.ArrayList; ArrayList list = new ArrayList(); boolean empty = list.isEmpty();",
            _STDLIB,
        )
        assert locals_of(vm)[VarName("empty")] is True
```

- [ ] **Step 6: Run all ArrayList tests**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_util_array_list.py -v
```

Expected: all passed.

- [ ] **Step 7: Commit**

```bash
bd backup
git add experiments/java_stdlib/stubs/java_util_array_list.py experiments/java_stdlib/tests/test_java_util_array_list.py
git commit -m "feat(experiment): add java.util.ArrayList IR stubs with execution tests"
```

---

## Task 5: java.util.HashMap stubs

**Files:**
- Create: `experiments/java_stdlib/stubs/java_util_hash_map.py`
- Create: `experiments/java_stdlib/tests/test_java_util_hash_map.py`

HashMap stores an `entries` field initialised as a `NewObject(type_hint="dict")`. `put`/`get` use `StoreIndex`/`LoadIndex`. `containsKey` calls `keys()` builtin then `__contains__`.

- [ ] **Step 1: Write failing export test**

`experiments/java_stdlib/tests/test_java_util_hash_map.py`:

```python
from interpreter.class_name import ClassName
from interpreter.func_name import FuncName
from experiments.java_stdlib.stubs.java_util_hash_map import HASH_MAP_MODULE


class TestHashMapExports:
    def test_exports_init(self):
        assert FuncName("__init__") in HASH_MAP_MODULE.exports.functions

    def test_exports_put(self):
        assert FuncName("put") in HASH_MAP_MODULE.exports.functions

    def test_exports_get(self):
        assert FuncName("get") in HASH_MAP_MODULE.exports.functions

    def test_exports_contains_key(self):
        assert FuncName("containsKey") in HASH_MAP_MODULE.exports.functions

    def test_exports_size(self):
        assert FuncName("size") in HASH_MAP_MODULE.exports.functions

    def test_exports_class(self):
        assert ClassName("HashMap") in HASH_MAP_MODULE.exports.classes
```

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_util_hash_map.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement HashMap stub**

`experiments/java_stdlib/stubs/java_util_hash_map.py`:

```python
from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Branch,
    CallFunction,
    CallMethod,
    Const,
    DeclVar,
    Label_,
    LoadField,
    LoadIndex,
    LoadVar,
    NewObject,
    Return_,
    StoreField,
    StoreIndex,
    Symbolic,
)
from interpreter.ir import CodeLabel
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register
from interpreter.var_name import VarName

_ENTRIES = FieldName("entries")

_CLS            = "class_HashMap_0"
_END_CLS        = "end_class_HashMap_1"
_INIT_F         = "func___init___2"
_INIT_END       = "end___init___3"
_PUT_F          = "func_put_4"
_PUT_END        = "end_put_5"
_GET_F          = "func_get_6"
_GET_END        = "end_get_7"
_CONTAINS_F     = "func_containsKey_8"
_CONTAINS_END   = "end_containsKey_9"
_SIZE_F         = "func_size_10"
_SIZE_END       = "end_size_11"

HASH_MAP_IR = (
    # ── declare HashMap class ─────────────────────────────────────────────────
    Label_(label=CodeLabel("entry_HashMap")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    Const(result_reg=Register("%0"), value=_CLS),
    DeclVar(name=VarName("HashMap"), value_reg=Register("%0")),

    # ── __init__(this) — initialise self.entries = {} ─────────────────────────
    Branch(label=CodeLabel(_INIT_END)),
    Label_(label=CodeLabel(_INIT_F)),
    Symbolic(result_reg=Register("%1"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%1")),
    NewObject(result_reg=Register("%2"), type_hint="dict"),
    LoadVar(result_reg=Register("%3"), name=VarName("this")),
    StoreField(obj_reg=Register("%3"), field_name=_ENTRIES, value_reg=Register("%2")),
    Const(result_reg=Register("%4"), value="None"),
    Return_(value_reg=Register("%4")),
    Label_(label=CodeLabel(_INIT_END)),
    Const(result_reg=Register("%5"), value=_INIT_F),
    DeclVar(name=VarName("__init__"), value_reg=Register("%5")),

    # ── put(this, key, value) → entries[key] = value ──────────────────────────
    Branch(label=CodeLabel(_PUT_END)),
    Label_(label=CodeLabel(_PUT_F)),
    Symbolic(result_reg=Register("%6"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%6")),
    Symbolic(result_reg=Register("%7"), hint="param:key"),
    DeclVar(name=VarName("key"), value_reg=Register("%7")),
    Symbolic(result_reg=Register("%8"), hint="param:value"),
    DeclVar(name=VarName("value"), value_reg=Register("%8")),
    LoadVar(result_reg=Register("%9"), name=VarName("this")),
    LoadField(result_reg=Register("%10"), obj_reg=Register("%9"), field_name=_ENTRIES),
    LoadVar(result_reg=Register("%11"), name=VarName("key")),
    LoadVar(result_reg=Register("%12"), name=VarName("value")),
    StoreIndex(arr_reg=Register("%10"), index_reg=Register("%11"), value_reg=Register("%12")),
    Const(result_reg=Register("%13"), value="None"),
    Return_(value_reg=Register("%13")),
    Label_(label=CodeLabel(_PUT_END)),
    Const(result_reg=Register("%14"), value=_PUT_F),
    DeclVar(name=VarName("put"), value_reg=Register("%14")),

    # ── get(this, key) → entries[key] ─────────────────────────────────────────
    Branch(label=CodeLabel(_GET_END)),
    Label_(label=CodeLabel(_GET_F)),
    Symbolic(result_reg=Register("%15"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%15")),
    Symbolic(result_reg=Register("%16"), hint="param:key"),
    DeclVar(name=VarName("key"), value_reg=Register("%16")),
    LoadVar(result_reg=Register("%17"), name=VarName("this")),
    LoadField(result_reg=Register("%18"), obj_reg=Register("%17"), field_name=_ENTRIES),
    LoadVar(result_reg=Register("%19"), name=VarName("key")),
    LoadIndex(result_reg=Register("%20"), arr_reg=Register("%18"), index_reg=Register("%19")),
    Return_(value_reg=Register("%20")),
    Label_(label=CodeLabel(_GET_END)),
    Const(result_reg=Register("%21"), value=_GET_F),
    DeclVar(name=VarName("get"), value_reg=Register("%21")),

    # ── containsKey(this, key) → key in keys(entries) ─────────────────────────
    Branch(label=CodeLabel(_CONTAINS_END)),
    Label_(label=CodeLabel(_CONTAINS_F)),
    Symbolic(result_reg=Register("%22"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%22")),
    Symbolic(result_reg=Register("%23"), hint="param:key"),
    DeclVar(name=VarName("key"), value_reg=Register("%23")),
    LoadVar(result_reg=Register("%24"), name=VarName("this")),
    LoadField(result_reg=Register("%25"), obj_reg=Register("%24"), field_name=_ENTRIES),
    LoadVar(result_reg=Register("%26"), name=VarName("key")),
    CallFunction(result_reg=Register("%27"), func_name=FuncName("keys"), args=(Register("%25"),)),
    CallMethod(result_reg=Register("%28"), obj_reg=Register("%27"), method_name=FuncName("__contains__"), args=(Register("%26"),)),
    Return_(value_reg=Register("%28")),
    Label_(label=CodeLabel(_CONTAINS_END)),
    Const(result_reg=Register("%29"), value=_CONTAINS_F),
    DeclVar(name=VarName("containsKey"), value_reg=Register("%29")),

    # ── size(this) → len(entries) ─────────────────────────────────────────────
    Branch(label=CodeLabel(_SIZE_END)),
    Label_(label=CodeLabel(_SIZE_F)),
    Symbolic(result_reg=Register("%30"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%30")),
    LoadVar(result_reg=Register("%31"), name=VarName("this")),
    LoadField(result_reg=Register("%32"), obj_reg=Register("%31"), field_name=_ENTRIES),
    CallFunction(result_reg=Register("%33"), func_name=FuncName("len"), args=(Register("%32"),)),
    Return_(value_reg=Register("%33")),
    Label_(label=CodeLabel(_SIZE_END)),
    Const(result_reg=Register("%34"), value=_SIZE_F),
    DeclVar(name=VarName("size"), value_reg=Register("%34")),
)

HASH_MAP_MODULE = ModuleUnit(
    path=Path("java/util/HashMap.java"),
    language=Language.JAVA,
    ir=HASH_MAP_IR,
    exports=ExportTable(
        functions={
            FuncName("__init__"):    CodeLabel(_INIT_F),
            FuncName("put"):         CodeLabel(_PUT_F),
            FuncName("get"):         CodeLabel(_GET_F),
            FuncName("containsKey"): CodeLabel(_CONTAINS_F),
            FuncName("size"):        CodeLabel(_SIZE_F),
        },
        classes={
            ClassName("HashMap"): CodeLabel(_CLS),
        },
    ),
    imports=(),
)
```

- [ ] **Step 4: Run export tests — confirm pass**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_util_hash_map.py::TestHashMapExports -v
```

Expected: 6 passed

- [ ] **Step 5: Write execution tests**

Add to `experiments/java_stdlib/tests/test_java_util_hash_map.py`:

```python
from pathlib import Path
from interpreter.var_name import VarName
from experiments.java_stdlib.stubs.java_util_hash_map import HASH_MAP_MODULE
from experiments.java_stdlib.tests.conftest import run_with_stdlib, locals_of

_STDLIB = {Path("java/util/HashMap.java"): HASH_MAP_MODULE}
_SRC = """
import java.util.HashMap;
HashMap map = new HashMap();
map.put("a", 1);
map.put("b", 2);
int val = map.get("a");
int sz = map.size();
boolean has = map.containsKey("b");
boolean missing = map.containsKey("c");
"""


class TestHashMapExecution:
    def test_get_value(self):
        vm = run_with_stdlib(_SRC, _STDLIB)
        assert locals_of(vm)[VarName("val")] == 1

    def test_size(self):
        vm = run_with_stdlib(_SRC, _STDLIB)
        assert locals_of(vm)[VarName("sz")] == 2

    def test_contains_key_present(self):
        vm = run_with_stdlib(_SRC, _STDLIB)
        assert locals_of(vm)[VarName("has")] is True

    def test_contains_key_absent(self):
        vm = run_with_stdlib(_SRC, _STDLIB)
        assert locals_of(vm)[VarName("missing")] is False
```

- [ ] **Step 6: Run all HashMap tests**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_util_hash_map.py -v
```

Expected: all passed.

- [ ] **Step 7: Commit**

```bash
bd backup
git add experiments/java_stdlib/stubs/java_util_hash_map.py experiments/java_stdlib/tests/test_java_util_hash_map.py
git commit -m "feat(experiment): add java.util.HashMap IR stubs with execution tests"
```

---

## Task 6: java.io.PrintStream + java.lang.System stubs

**Files:**
- Create: `experiments/java_stdlib/stubs/java_io_print_stream.py`
- Create: `experiments/java_stdlib/stubs/java_lang_system.py`
- Create: `experiments/java_stdlib/tests/test_java_lang_system.py`

`System.out.println("hello")` lowers as: `load_var System` → `load_field System out` → `call_method %out println %msg`. The System stub declares a `System` class with an `out` field. PrintStream is a class with `println`/`print` methods that call the `print` builtin.

- [ ] **Step 1: Write failing export test**

`experiments/java_stdlib/tests/test_java_lang_system.py`:

```python
from interpreter.class_name import ClassName
from interpreter.func_name import FuncName
from experiments.java_stdlib.stubs.java_io_print_stream import PRINT_STREAM_MODULE
from experiments.java_stdlib.stubs.java_lang_system import SYSTEM_MODULE


class TestSystemAndPrintStreamExports:
    def test_system_has_class(self):
        assert ClassName("System") in SYSTEM_MODULE.exports.classes

    def test_print_stream_exports_println(self):
        assert FuncName("println") in PRINT_STREAM_MODULE.exports.functions

    def test_print_stream_exports_print(self):
        assert FuncName("print") in PRINT_STREAM_MODULE.exports.functions

    def test_print_stream_has_class(self):
        assert ClassName("PrintStream") in PRINT_STREAM_MODULE.exports.classes
```

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_lang_system.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement PrintStream stub**

`experiments/java_stdlib/stubs/java_io_print_stream.py`:

```python
from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Branch,
    CallFunction,
    Const,
    DeclVar,
    Label_,
    Return_,
    Symbolic,
)
from interpreter.ir import CodeLabel
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register
from interpreter.var_name import VarName

_CLS        = "class_PrintStream_0"
_END_CLS    = "end_class_PrintStream_1"
_PRINTLN_F  = "func_println_2"
_PRINTLN_END = "end_println_3"
_PRINT_F    = "func_print_4"
_PRINT_END  = "end_print_5"

PRINT_STREAM_IR = (
    # ── declare PrintStream class ─────────────────────────────────────────────
    Label_(label=CodeLabel("entry_PrintStream")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    Const(result_reg=Register("%0"), value=_CLS),
    DeclVar(name=VarName("PrintStream"), value_reg=Register("%0")),

    # ── println(this, msg) → print(msg) ───────────────────────────────────────
    Branch(label=CodeLabel(_PRINTLN_END)),
    Label_(label=CodeLabel(_PRINTLN_F)),
    Symbolic(result_reg=Register("%1"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%1")),
    Symbolic(result_reg=Register("%2"), hint="param:msg"),
    DeclVar(name=VarName("msg"), value_reg=Register("%2")),
    LoadVar(result_reg=Register("%3"), name=VarName("msg")),  # noqa: F821
    CallFunction(result_reg=Register("%4"), func_name=FuncName("print"), args=(Register("%3"),)),
    Const(result_reg=Register("%5"), value="None"),
    Return_(value_reg=Register("%5")),
    Label_(label=CodeLabel(_PRINTLN_END)),
    Const(result_reg=Register("%6"), value=_PRINTLN_F),
    DeclVar(name=VarName("println"), value_reg=Register("%6")),

    # ── print(this, msg) → print(msg) ─────────────────────────────────────────
    Branch(label=CodeLabel(_PRINT_END)),
    Label_(label=CodeLabel(_PRINT_F)),
    Symbolic(result_reg=Register("%7"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%7")),
    Symbolic(result_reg=Register("%8"), hint="param:msg"),
    DeclVar(name=VarName("msg"), value_reg=Register("%8")),
    LoadVar(result_reg=Register("%9"), name=VarName("msg")),
    CallFunction(result_reg=Register("%10"), func_name=FuncName("print"), args=(Register("%9"),)),
    Const(result_reg=Register("%11"), value="None"),
    Return_(value_reg=Register("%11")),
    Label_(label=CodeLabel(_PRINT_END)),
    Const(result_reg=Register("%12"), value=_PRINT_F),
    DeclVar(name=VarName("print"), value_reg=Register("%12")),
)

# Missing LoadVar import — add to imports above
from interpreter.instructions import LoadVar  # noqa: E402

PRINT_STREAM_MODULE = ModuleUnit(
    path=Path("java/io/PrintStream.java"),
    language=Language.JAVA,
    ir=PRINT_STREAM_IR,
    exports=ExportTable(
        functions={
            FuncName("println"): CodeLabel(_PRINTLN_F),
            FuncName("print"):   CodeLabel(_PRINT_F),
        },
        classes={
            ClassName("PrintStream"): CodeLabel(_CLS),
        },
    ),
    imports=(),
)
```

Note: move the `LoadVar` import to the top-level imports block — the inline import above is just a reminder to include it.

- [ ] **Step 4: Implement System stub**

`System.out.println("hello")` lowers as field access + method call: `load_var System → load_field out → call_method %out println`. System stub declares a `System` class and initialises its `out` field as a new `PrintStream` instance.

`experiments/java_stdlib/stubs/java_lang_system.py`:

```python
from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Branch,
    CallCtorFunction,
    Const,
    DeclVar,
    Label_,
    LoadVar,
    Return_,
    StoreField,
    Symbolic,
)
from interpreter.ir import CodeLabel
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register
from interpreter.types.type_expr import scalar
from interpreter.var_name import VarName

_OUT = FieldName("out")

_CLS        = "class_System_0"
_END_CLS    = "end_class_System_1"
_INIT_F     = "func___init___2"
_INIT_END   = "end___init___3"

SYSTEM_IR = (
    # ── declare System class ──────────────────────────────────────────────────
    Label_(label=CodeLabel("entry_System")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    Const(result_reg=Register("%0"), value=_CLS),
    DeclVar(name=VarName("System"), value_reg=Register("%0")),

    # ── __init__(this) — create System.out = new PrintStream() ───────────────
    Branch(label=CodeLabel(_INIT_END)),
    Label_(label=CodeLabel(_INIT_F)),
    Symbolic(result_reg=Register("%1"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%1")),
    # Allocate a PrintStream heap object and assign to this.out
    CallCtorFunction(
        result_reg=Register("%2"),
        func_name=FuncName("PrintStream"),
        type_hint=scalar("PrintStream"),
        args=(),
    ),
    LoadVar(result_reg=Register("%3"), name=VarName("this")),
    StoreField(obj_reg=Register("%3"), field_name=_OUT, value_reg=Register("%2")),
    Const(result_reg=Register("%4"), value="None"),
    Return_(value_reg=Register("%4")),
    Label_(label=CodeLabel(_INIT_END)),
    Const(result_reg=Register("%5"), value=_INIT_F),
    DeclVar(name=VarName("__init__"), value_reg=Register("%5")),
)

SYSTEM_MODULE = ModuleUnit(
    path=Path("java/lang/System.java"),
    language=Language.JAVA,
    ir=SYSTEM_IR,
    exports=ExportTable(
        functions={
            FuncName("__init__"): CodeLabel(_INIT_F),
        },
        classes={
            ClassName("System"): CodeLabel(_CLS),
        },
    ),
    imports=(),
)
```

- [ ] **Step 5: Run export tests — confirm pass**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_lang_system.py::TestSystemAndPrintStreamExports -v
```

Expected: 4 passed

- [ ] **Step 6: Write execution test**

Add to `experiments/java_stdlib/tests/test_java_lang_system.py`:

```python
from pathlib import Path
from experiments.java_stdlib.stubs.java_io_print_stream import PRINT_STREAM_MODULE
from experiments.java_stdlib.stubs.java_lang_system import SYSTEM_MODULE
from experiments.java_stdlib.tests.conftest import run_with_stdlib

_STDLIB = {
    Path("java/io/PrintStream.java"): PRINT_STREAM_MODULE,
    Path("java/lang/System.java"):    SYSTEM_MODULE,
}


class TestSystemExecution:
    def test_println_produces_output(self, capsys):
        run_with_stdlib('System.out.println("hello");', _STDLIB)
        assert capsys.readouterr().out.strip() == "hello"
```

- [ ] **Step 7: Run all System tests**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_java_lang_system.py -v
```

Expected: all passed.

- [ ] **Step 8: Commit**

```bash
bd backup
git add experiments/java_stdlib/stubs/java_io_print_stream.py experiments/java_stdlib/stubs/java_lang_system.py experiments/java_stdlib/tests/test_java_lang_system.py
git commit -m "feat(experiment): add System/PrintStream IR stubs with execution tests"
```

---

## Task 7: Registry + interface aliases

**Files:**
- Create: `experiments/java_stdlib/registry.py`
- Create: `experiments/java_stdlib/tests/test_registry.py`

- [ ] **Step 1: Write failing registry test**

`experiments/java_stdlib/tests/test_registry.py`:

```python
from pathlib import Path
from experiments.java_stdlib.registry import STDLIB_REGISTRY


class TestRegistry:
    def test_array_list_present(self):
        assert Path("java/util/ArrayList.java") in STDLIB_REGISTRY

    def test_hash_map_present(self):
        assert Path("java/util/HashMap.java") in STDLIB_REGISTRY

    def test_math_present(self):
        assert Path("java/lang/Math.java") in STDLIB_REGISTRY

    def test_list_interface_aliases_array_list(self):
        assert STDLIB_REGISTRY[Path("java/util/List.java")] is STDLIB_REGISTRY[Path("java/util/ArrayList.java")]

    def test_map_interface_aliases_hash_map(self):
        assert STDLIB_REGISTRY[Path("java/util/Map.java")] is STDLIB_REGISTRY[Path("java/util/HashMap.java")]

    def test_collection_interface_aliases_array_list(self):
        assert STDLIB_REGISTRY[Path("java/util/Collection.java")] is STDLIB_REGISTRY[Path("java/util/ArrayList.java")]
```

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_registry.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement registry**

`experiments/java_stdlib/registry.py`:

```python
from pathlib import Path

from interpreter.project.types import ModuleUnit

from experiments.java_stdlib.stubs.java_io_print_stream import PRINT_STREAM_MODULE
from experiments.java_stdlib.stubs.java_lang_math import MATH_MODULE
from experiments.java_stdlib.stubs.java_lang_string import STRING_MODULE
from experiments.java_stdlib.stubs.java_lang_system import SYSTEM_MODULE
from experiments.java_stdlib.stubs.java_util_array_list import ARRAY_LIST_MODULE
from experiments.java_stdlib.stubs.java_util_hash_map import HASH_MAP_MODULE

STDLIB_REGISTRY: dict[Path, ModuleUnit] = {
    # Concrete classes
    Path("java/lang/Math.java"):       MATH_MODULE,
    Path("java/lang/String.java"):     STRING_MODULE,
    Path("java/lang/System.java"):     SYSTEM_MODULE,
    Path("java/io/PrintStream.java"):  PRINT_STREAM_MODULE,
    Path("java/util/ArrayList.java"):  ARRAY_LIST_MODULE,
    Path("java/util/HashMap.java"):    HASH_MAP_MODULE,
    # Interface aliases — same ModuleUnit as concrete implementation
    Path("java/util/List.java"):       ARRAY_LIST_MODULE,
    Path("java/util/Collection.java"): ARRAY_LIST_MODULE,
    Path("java/util/Map.java"):        HASH_MAP_MODULE,
}
```

- [ ] **Step 4: Run registry tests — confirm pass**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_registry.py -v
```

Expected: all passed

- [ ] **Step 5: Commit**

```bash
bd backup
git add experiments/java_stdlib/registry.py experiments/java_stdlib/tests/test_registry.py
git commit -m "feat(experiment): add stdlib registry with interface aliases"
```

---

## Task 8: End-to-end integration tests

**Files:**
- Create: `experiments/java_stdlib/tests/test_integration.py`

- [ ] **Step 1: Write integration tests**

`experiments/java_stdlib/tests/test_integration.py`:

```python
from pathlib import Path

from interpreter.var_name import VarName

from experiments.java_stdlib.registry import STDLIB_REGISTRY
from experiments.java_stdlib.tests.conftest import locals_of, run_with_stdlib

_ALL = STDLIB_REGISTRY


class TestEndToEnd:
    def test_arraylist_produces_concrete_not_symbolic(self):
        """Core success criterion: stdlib call returns concrete value, not SYMBOLIC."""
        vm = run_with_stdlib(
            """
            import java.util.ArrayList;
            ArrayList list = new ArrayList();
            list.add(10);
            list.add(20);
            int x = list.get(0);
            int y = list.get(1);
            int total = x + y;
            """,
            _ALL,
            max_steps=1000,
        )
        locs = locals_of(vm)
        assert locs[VarName("x")] == 10
        assert locs[VarName("y")] == 20
        assert locs[VarName("total")] == 30

    def test_math_result_flows_into_arithmetic(self):
        """Math.sqrt result is concrete and usable in subsequent operations."""
        vm = run_with_stdlib(
            "double root = Math.sqrt(16.0); double doubled = root + root;",
            _ALL,
        )
        locs = locals_of(vm)
        assert locs[VarName("root")] == 4.0
        assert locs[VarName("doubled")] == 8.0

    def test_hashmap_roundtrip(self):
        """HashMap put/get roundtrip produces concrete value."""
        vm = run_with_stdlib(
            """
            import java.util.HashMap;
            HashMap map = new HashMap();
            map.put("score", 42);
            int result = map.get("score");
            """,
            _ALL,
            max_steps=1000,
        )
        assert locals_of(vm)[VarName("result")] == 42

    def test_system_out_println(self, capsys):
        """System.out.println produces output, not SYMBOLIC."""
        run_with_stdlib('System.out.println("experiment works");', _ALL)
        assert "experiment works" in capsys.readouterr().out
```

- [ ] **Step 2: Run integration tests**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/test_integration.py -v
```

Expected: all passed.

- [ ] **Step 3: Run full experiment suite**

```bash
poetry run python -m pytest experiments/java_stdlib/tests/ -v
```

Expected: all tests in all files pass.

- [ ] **Step 4: Confirm main test suite unaffected**

```bash
poetry run python -m pytest tests/ -x -q
```

Expected: 13168 passed, 1 skipped, 22 xfailed. No regressions.

- [ ] **Step 5: Commit**

```bash
bd backup
git add experiments/java_stdlib/tests/test_integration.py
git commit -m "feat(experiment): add end-to-end integration tests for java stdlib stubs"
```
