# Java Stdlib Stubs — Experiment Design

**Date:** 2026-03-31
**Status:** Draft
**Scope:** Independent experiment — not wired into execution pipeline

---

## Problem

When RedDragon executes real-world Java programs, calls to stdlib classes and
methods produce SYMBOLIC values because the VM has no definition for them.
SYMBOLIC propagates through downstream operations, destroying concrete
data flow.

## Goal

Validate that Java stdlib contracts can be implemented as hand-written
RedDragon IR, stored as `ModuleUnit`s in a registry, linked against a user
program, and executed through the VM to produce concrete values instead of
SYMBOLIC.

This directly validates the integration path: success here means wiring the
import resolver to look up the registry first is sufficient — no new VM
dispatch mechanism required.

---

## Non-Goals

- Integration with the import resolver, linker, or compiler pipeline
- VM dispatch changes
- Python stdlib stubs
- Versioning (JDK 11 vs 17 differences)
- Full stdlib coverage
- Inheritance machinery or interface dispatch

---

## Key Principle

The experiment imports from `interpreter/` as a read-only library — no
modifications to any production module. Deleting `experiments/java-stdlib/`
leaves the main codebase byte-for-byte identical.

---

## Structure

```
experiments/java-stdlib/
    stubs/
        java_io_print_stream.py
        java_lang_math.py
        java_lang_string.py
        java_lang_system.py
        java_util_array_list.py
        java_util_collection.py
        java_util_hash_map.py
        java_util_list.py
        java_util_map.py
    tests/
        test_java_io_print_stream.py
        test_java_lang_math.py
        test_java_lang_string.py
        test_java_lang_system.py
        test_java_util_array_list.py
        test_java_util_collection.py
        test_java_util_hash_map.py
        test_java_util_list.py
        test_java_util_map.py
    registry.py
```

---

## Stub Shape

Each stub file constructs and exports a `ModuleUnit`. The IR is built
programmatically from typed instruction dataclasses — the same types that
frontends produce. Each method is a labelled function body in the IR.

Example — `java.util.ArrayList.add`:

```python
from interpreter.instructions import (
    Label_, Branch, Const, LoadVar, StoreIndex,
    LoadField, StoreField, Binop, Return_
)
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import VarName
from interpreter.func_name import FuncName
from interpreter.field_name import FieldName
from interpreter.project.types import ModuleUnit, ExportTable
from interpreter.constants import Language
from pathlib import Path

# java.util.ArrayList stub
# Heap representation: object with field "elements" holding an array,
# and field "size" holding an int.

_ADD_LABEL   = CodeLabel("func_ArrayList_add_0")
_GET_LABEL   = CodeLabel("func_ArrayList_get_0")
_SIZE_LABEL  = CodeLabel("func_ArrayList_size_0")

ir = (
    Label_(label=CodeLabel("entry")),
    Branch(label=CodeLabel("func_ArrayList_add_0_end")),   # skip over bodies

    # --- add(self, element) → bool ---
    Label_(label=_ADD_LABEL),
    # ... instructions that append element to self.elements, return True
    Return_(value_reg=Register("%result")),
    Label_(label=CodeLabel("func_ArrayList_add_0_end")),

    # --- get(self, index) → element ---
    Label_(label=_GET_LABEL),
    # ... load self.elements[index], return it
    Return_(value_reg=Register("%result")),

    # --- size(self) → int ---
    Label_(label=_SIZE_LABEL),
    # ... load self.size, return it
    Return_(value_reg=Register("%result")),
)

ARRAY_LIST_MODULE = ModuleUnit(
    path=Path("java/util/ArrayList.java"),
    language=Language.JAVA,
    ir=ir,
    exports=ExportTable(
        functions={
            FuncName("ArrayList.add"):  _ADD_LABEL,
            FuncName("ArrayList.get"):  _GET_LABEL,
            FuncName("ArrayList.size"): _SIZE_LABEL,
        }
    ),
    imports=(),
)
```

`native` methods (e.g. `Object.hashCode`) are not stubbed — they are absent
from the export table and fall through to the existing LLM resolver at
runtime.

---

## Registry

`registry.py` exports a single dict:

```python
STDLIB_REGISTRY: dict[str, ModuleUnit]
```

Keys are qualified class names: `"java.util.ArrayList"`, `"java.lang.Math"`,
etc. Interface entries point to the same `ModuleUnit` as their concrete
implementation — `"java.util.List"` and `"java.util.ArrayList"` are the same
value. The registry is flat; no inheritance graph.

---

## Covered Classes and Methods

### Interfaces (alias to concrete `ModuleUnit` in registry)

| Class | Methods |
|---|---|
| `java.util.Collection` | `add`, `size`, `isEmpty`, `contains` |
| `java.util.List` | `add`, `get`, `size`, `remove`, `contains`, `isEmpty` |
| `java.util.Map` | `put`, `get`, `containsKey`, `size`, `isEmpty` |

### Concrete classes

| Class | Methods / Fields |
|---|---|
| `java.util.ArrayList` | `add`, `get`, `size`, `remove`, `contains`, `isEmpty` |
| `java.util.HashMap` | `put`, `get`, `containsKey`, `size`, `isEmpty` |
| `java.lang.Math` | `sqrt`, `abs`, `pow`, `min`, `max`, `floor`, `ceil` |
| `java.lang.String` | `toUpperCase`, `toLowerCase`, `substring`, `split`, `trim`, `length`, `contains`, `replace` |
| `java.lang.System` | field: `out` → `PrintStream` instance |
| `java.io.PrintStream` | `println`, `print` |

---

## Object Representation

Stdlib objects follow the same heap conventions as user objects. A new
`ArrayList` is a heap object with fields `elements` (array) and `size` (int).
A `HashMap` has fields `keys` (array) and `values` (array) and `size` (int).
`String` has field `value` (str).

These conventions are internal to the stubs and do not need to match any
existing VM representation — that mapping is deferred to the integration
phase.

---

## Testing Approach

Each test compiles a minimal Java snippet through the existing Java frontend,
manually links it against the relevant stdlib `ModuleUnit`(s) from the
registry using the existing `link_modules()`, runs it through the VM, and
asserts concrete output values.

```python
from interpreter.project.linker import link_modules
from interpreter.run import run
from experiments.java_stdlib.registry import STDLIB_REGISTRY

def test_arraylist_add_and_get():
    java_source = b"""
    import java.util.ArrayList;
    class Main {
        public static void main() {
            ArrayList list = new ArrayList();
            list.add(42);
            int x = list.get(0);
        }
    }
    """
    # Compile user program
    user_module = java_frontend.lower(java_source)

    # Link with stdlib stubs
    linked = link_modules(
        modules={
            Path("Main.java"): user_module,
            **{Path(k): v for k, v in STDLIB_REGISTRY.items()
               if k in ["java.util.ArrayList"]},
        },
        ...
    )

    result = run(linked, entry_point=...)
    assert result.get_var("x") == 42
```

No mocking. No Python-level assertions on intermediate IR state. The
assertion is always on a concrete value produced by VM execution.

---

## Success Criteria

1. At least one stdlib method call (`ArrayList.get`, `Math.sqrt`, etc.)
   produces a concrete value through VM execution instead of SYMBOLIC.
2. Interface registry entries (`java.util.List.*`) and concrete entries
   (`java.util.ArrayList.*`) resolve to the same `ModuleUnit` without
   duplication.
3. `System.out.println("hello")` produces `"hello\n"` on stdout via VM
   execution of linked IR.
4. The experiment directory is fully self-contained — no modifications to
   `interpreter/` or any production module.
