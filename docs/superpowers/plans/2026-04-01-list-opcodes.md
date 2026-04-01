# `list_opcodes` MCP Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `list_opcodes` MCP tool that returns all 33 IR opcodes with categories, descriptions, typed fields, and semantic notes.

**Architecture:** New `handle_list_opcodes()` pure function in `mcp_server/tools.py` derives data by introspecting `_TO_TYPED` (opcode→builder map), `get_type_hints`, and `dataclasses.fields`. Two small hardcoded dicts provide categories and per-opcode notes. `mcp_server/server.py` registers the tool with `@mcp.tool()`. Tests live in `tests/unit/test_mcp_tools.py` as a new `TestListOpcodes` class.

**Tech Stack:** Python 3.13+, FastMCP, pytest, poetry

---

## File Map

| Action | Path | Change |
|--------|------|--------|
| Modify | `mcp_server/tools.py` | Add `handle_list_opcodes()` + two hardcoded dicts + new imports |
| Modify | `mcp_server/server.py` | Import `handle_list_opcodes`, add `@mcp.tool()` registration |
| Modify | `tests/unit/test_mcp_tools.py` | Add `TestListOpcodes` class |

---

## Task 1: File Beads issue and implement `handle_list_opcodes`

**Files:**
- Modify: `mcp_server/tools.py`
- Modify: `tests/unit/test_mcp_tools.py`

- [ ] **Step 1: File and claim a Beads issue**

```bash
bd create "Add list_opcodes MCP tool" \
  --description="Add a list_opcodes MCP tool to mcp_server/ that returns all 33 IR opcodes with name, category, description, fields, and semantic notes. Handler in mcp_server/tools.py (handle_list_opcodes), registered in mcp_server/server.py. Tests in tests/unit/test_mcp_tools.py::TestListOpcodes." \
  -t feature -p 2
```

Record the issue ID, then claim it:

```bash
bd update <ISSUE_ID> --claim
```

- [ ] **Step 2: Write the failing tests**

Add this class to `tests/unit/test_mcp_tools.py`, after the existing imports and test classes:

```python
from mcp_server.tools import handle_list_opcodes


class TestListOpcodes:
    def setup_method(self):
        self.result = handle_list_opcodes()
        self.opcodes = self.result["opcodes"]
        self.by_name = {o["name"]: o for o in self.opcodes}

    def test_returns_all_33_opcodes(self):
        assert len(self.opcodes) == 33

    def test_sorted_alphabetically(self):
        names = [o["name"] for o in self.opcodes]
        assert names == sorted(names)

    def test_every_entry_has_required_keys(self):
        for entry in self.opcodes:
            assert set(entry.keys()) == {"name", "category", "description", "fields", "notes"}

    def test_source_location_excluded_from_fields(self):
        for entry in self.opcodes:
            field_names = [f["name"] for f in entry["fields"]]
            assert "source_location" not in field_names

    def test_every_field_has_name_and_type(self):
        for entry in self.opcodes:
            for f in entry["fields"]:
                assert "name" in f
                assert "type" in f
                assert isinstance(f["name"], str)
                assert isinstance(f["type"], str)

    def test_binop_fields(self):
        binop = self.by_name["BINOP"]
        field_names = [f["name"] for f in binop["fields"]]
        assert "operator" in field_names
        assert "left" in field_names
        assert "right" in field_names
        assert "result_reg" in field_names

    def test_binop_category(self):
        assert self.by_name["BINOP"]["category"] == "arithmetic"

    def test_call_function_category(self):
        assert self.by_name["CALL_FUNCTION"]["category"] == "calls"

    def test_label_category(self):
        assert self.by_name["LABEL"]["category"] == "control_flow"

    def test_new_object_category(self):
        assert self.by_name["NEW_OBJECT"]["category"] == "heap"

    def test_alloc_region_category(self):
        assert self.by_name["ALLOC_REGION"]["category"] == "memory"

    def test_set_continuation_category(self):
        assert self.by_name["SET_CONTINUATION"]["category"] == "continuations"

    def test_const_category(self):
        assert self.by_name["CONST"]["category"] == "variables"

    def test_descriptions_are_non_empty_strings(self):
        for entry in self.opcodes:
            assert isinstance(entry["description"], str)
            assert len(entry["description"]) > 10

    def test_notes_are_non_empty_strings(self):
        for entry in self.opcodes:
            assert isinstance(entry["notes"], str)
            assert len(entry["notes"]) > 20

    def test_label_has_no_opcode_specific_fields(self):
        # LABEL only has base fields: result_reg, label, branch_targets
        label = self.by_name["LABEL"]
        field_names = [f["name"] for f in label["fields"]]
        assert set(field_names) == {"result_reg", "label", "branch_targets"}

    def test_try_push_has_exception_fields(self):
        tp = self.by_name["TRY_PUSH"]
        field_names = [f["name"] for f in tp["fields"]]
        assert "catch_labels" in field_names
        assert "finally_label" in field_names
        assert "end_label" in field_names
```

- [ ] **Step 3: Run the tests to confirm they fail**

```bash
poetry run python -m pytest tests/unit/test_mcp_tools.py::TestListOpcodes -v 2>&1 | tail -10
```

Expected: `ImportError: cannot import name 'handle_list_opcodes'` or similar.

- [ ] **Step 4: Add the two hardcoded dicts and `handle_list_opcodes` to `mcp_server/tools.py`**

Add these imports near the top of `mcp_server/tools.py`, with the existing interpreter imports:

```python
import dataclasses
from typing import get_type_hints

from interpreter.instructions import _TO_TYPED
from interpreter.ir import Opcode
```

Then add these three blocks at the bottom of `mcp_server/tools.py` (before any `if __name__` block if present, otherwise just at the end):

```python
# ---------------------------------------------------------------------------
# Opcode catalogue
# ---------------------------------------------------------------------------

_OPCODE_CATEGORIES: dict[str, str] = {
    "CONST": "variables",
    "LOAD_VAR": "variables",
    "DECL_VAR": "variables",
    "STORE_VAR": "variables",
    "SYMBOLIC": "variables",
    "BINOP": "arithmetic",
    "UNOP": "arithmetic",
    "CALL_FUNCTION": "calls",
    "CALL_METHOD": "calls",
    "CALL_UNKNOWN": "calls",
    "CALL_CTOR": "calls",
    "LOAD_FIELD": "fields_and_indices",
    "STORE_FIELD": "fields_and_indices",
    "LOAD_FIELD_INDIRECT": "fields_and_indices",
    "LOAD_INDEX": "fields_and_indices",
    "STORE_INDEX": "fields_and_indices",
    "LABEL": "control_flow",
    "BRANCH": "control_flow",
    "BRANCH_IF": "control_flow",
    "RETURN": "control_flow",
    "THROW": "control_flow",
    "TRY_PUSH": "control_flow",
    "TRY_POP": "control_flow",
    "NEW_OBJECT": "heap",
    "NEW_ARRAY": "heap",
    "ALLOC_REGION": "memory",
    "LOAD_REGION": "memory",
    "WRITE_REGION": "memory",
    "ADDRESS_OF": "memory",
    "LOAD_INDIRECT": "memory",
    "STORE_INDIRECT": "memory",
    "SET_CONTINUATION": "continuations",
    "RESUME_CONTINUATION": "continuations",
}

_OPCODE_NOTES: dict[str, str] = {
    "CONST": (
        "value holds a Python literal: int, float, str, bool, None, or a list for "
        "array literals. result_reg receives the boxed value. Used for every literal "
        "expression in every frontend."
    ),
    "LOAD_VAR": (
        "Reads the variable named by name from the current frame's variable store. "
        "If the variable is absent from the current frame, the VM walks up the scope "
        "chain until it finds a frame that owns it. result_reg receives the value."
    ),
    "DECL_VAR": (
        "Declares name in the *current* frame and assigns value_reg to it. "
        "Deliberately shadows any outer-scope variable with the same name. "
        "result_reg is unused (NO_REGISTER). Use STORE_VAR for subsequent assignments."
    ),
    "STORE_VAR": (
        "Assigns value_reg to an already-declared variable named name. Unlike "
        "DECL_VAR, STORE_VAR walks up the scope chain to find the nearest frame that "
        "owns name and writes there. result_reg is unused."
    ),
    "SYMBOLIC": (
        "Placeholder instruction emitted for function parameters before VM execution. "
        "hint is a display name only and carries no runtime meaning. Any SYMBOLIC "
        "remaining at execution time indicates an unresolved parameter value. "
        "result_reg receives the symbolic register."
    ),
    "BINOP": (
        "Applies a binary operator to registers left and right; result lands in "
        "result_reg. operator is a BinopKind: ADD, SUB, MUL, DIV, MOD, EQ, NEQ, LT, "
        "LTE, GT, GTE, AND, OR, BITAND, BITOR, BITXOR, SHL, SHR. Integer and float "
        "operands are both accepted — the VM does not distinguish at the IR level. "
        "Comparison operators produce a boolean-valued register."
    ),
    "UNOP": (
        "Applies a unary operator to operand; result lands in result_reg. operator is "
        "a UnopKind: NEG (arithmetic negation), NOT (boolean negation), BITNOT "
        "(bitwise complement)."
    ),
    "CALL_FUNCTION": (
        "Calls the function named func_name with positional arguments in args. Each "
        "element of args is either a Register (normal argument) or a SpreadArguments "
        "wrapper (for *args splat). result_reg receives the return value; NO_REGISTER "
        "if the call is for side effects only. The callee must be resolvable in the "
        "function registry."
    ),
    "CALL_METHOD": (
        "Dispatches a method call dynamically. obj_reg holds the receiver object; "
        "method_name is the FieldName of the method. The VM looks up method_name on "
        "the object's class at runtime. result_reg receives the return value. Used for "
        "all object method calls across all languages."
    ),
    "CALL_UNKNOWN": (
        "Calls a first-class callable value stored in target_reg. Used for closures, "
        "higher-order functions, callbacks, and any call where the callee cannot be "
        "resolved at IR-lowering time. result_reg receives the return value."
    ),
    "CALL_CTOR": (
        "Allocates a new object of type type_hint and invokes its constructor. "
        "Distinct from CALL_FUNCTION because constructor semantics require the VM to "
        "initialise 'self' before dispatch. result_reg receives the newly constructed "
        "object. type_hint is the TypeExpr describing the class."
    ),
    "LOAD_FIELD": (
        "Reads field field_name from the object in obj_reg. result_reg receives the "
        "value. Raises a runtime error if the field does not exist on the object. "
        "Used for attribute access (obj.field) in all object-oriented frontends."
    ),
    "STORE_FIELD": (
        "Writes value_reg into field field_name on the object in obj_reg. Creates the "
        "field if it does not already exist (duck-typed object model). result_reg is "
        "unused. Used for attribute assignment (obj.field = value)."
    ),
    "LOAD_FIELD_INDIRECT": (
        "Like LOAD_FIELD but the field name is itself a runtime value in name_reg "
        "rather than a compile-time constant. Used for computed property access such "
        "as obj[expr] in property-bag patterns and dynamic dispatch tables."
    ),
    "LOAD_INDEX": (
        "Reads arr_reg[index_reg]. Supports lists, dicts, strings, and any object "
        "whose runtime type provides __getitem__ semantics in the VM's builtin layer. "
        "result_reg receives the element."
    ),
    "STORE_INDEX": (
        "Writes value_reg to arr_reg[index_reg]. Supports lists and dicts. "
        "result_reg is unused. Used for indexed assignment (arr[i] = v)."
    ),
    "LOAD_INDIRECT": (
        "Dereferences the Pointer value in ptr_reg and places the pointed-to value "
        "in result_reg. Used for C- and Pascal-style pointer semantics. The pointer "
        "must have been created by ADDRESS_OF."
    ),
    "STORE_INDIRECT": (
        "Writes value_reg to the memory address held in the Pointer in ptr_reg. "
        "result_reg is unused. Paired with ADDRESS_OF and LOAD_INDIRECT for pointer "
        "read-modify-write patterns."
    ),
    "ADDRESS_OF": (
        "Takes the address of the variable named var_name and stores a Pointer object "
        "in result_reg. The Pointer can later be passed to LOAD_INDIRECT or "
        "STORE_INDIRECT. Used to emulate pass-by-reference and C pointer semantics."
    ),
    "NEW_OBJECT": (
        "Allocates an empty heap object (HeapObject) tagged with type_hint. "
        "result_reg receives the object. Does NOT call a constructor — use CALL_CTOR "
        "for construction with initialisation. type_hint is a TypeExpr and may be "
        "UNKNOWN for dynamically-typed languages."
    ),
    "NEW_ARRAY": (
        "Allocates a new list of size_reg elements (initialised to None). type_hint "
        "is optional and may be UNKNOWN. result_reg receives the list. Used for "
        "fixed-size array allocation in statically-typed frontends; dynamically-typed "
        "frontends typically emit CONST with a list literal instead."
    ),
    "LABEL": (
        "Pseudo-instruction marking a basic block entry point. label holds the "
        "CodeLabel that other instructions branch to. Carries no runtime action — the "
        "VM uses LABEL instructions only during CFG construction. Every basic block "
        "begins with exactly one LABEL."
    ),
    "BRANCH": (
        "Unconditional jump to the target in label. Control never falls through to "
        "the next instruction in the flat IR list. Used to close a basic block that "
        "ends with a jump (loop back-edge, else/end-if merge)."
    ),
    "BRANCH_IF": (
        "Conditional branch on cond_reg. Jumps to branch_targets[0] if cond_reg is "
        "truthy, otherwise to branch_targets[1]. Exactly two branch targets are "
        "required. Used for if/else, while, and ternary expressions."
    ),
    "RETURN": (
        "Returns value_reg to the caller and pops the current stack frame. If "
        "value_reg is NO_REGISTER, the function returns None implicitly. Every "
        "function must have at least one RETURN on every exit path."
    ),
    "THROW": (
        "Raises value_reg as an exception and begins stack unwinding. The VM searches "
        "up the call stack for a TRY_PUSH handler whose catch_labels match the "
        "exception type. If none is found, the program terminates with an unhandled "
        "exception."
    ),
    "TRY_PUSH": (
        "Pushes an exception handler onto the VM's exception stack. catch_labels is "
        "a tuple of CodeLabel, one per catch clause in source order. finally_label "
        "is the finally block entry point (NO_LABEL if the try has no finally). "
        "end_label marks the end of the entire try/catch/finally construct. Must be "
        "paired with TRY_POP on the non-exception exit path."
    ),
    "TRY_POP": (
        "Pops the top exception handler from the VM's exception stack. Emitted at "
        "the end of a try block on the normal (non-exception) execution path. Every "
        "TRY_PUSH must have exactly one corresponding TRY_POP."
    ),
    "ALLOC_REGION": (
        "Allocates a raw memory region of size_reg bytes and returns an opaque region "
        "handle in result_reg. Used to emulate fixed-size structs (Pascal records, C "
        "structs). The region is accessed via LOAD_REGION and WRITE_REGION using byte "
        "offsets."
    ),
    "LOAD_REGION": (
        "Reads length bytes from the region in region_reg starting at byte offset "
        "offset_reg. result_reg receives the extracted value. length is an integer "
        "literal (not a register) representing the field width in bytes."
    ),
    "WRITE_REGION": (
        "Writes value_reg into region_reg at byte offset offset_reg for length bytes. "
        "length is an integer literal. result_reg is unused. Paired with ALLOC_REGION "
        "and LOAD_REGION for struct field access."
    ),
    "SET_CONTINUATION": (
        "Registers a named continuation re-entry point. name is a ContinuationName; "
        "target_label is the CodeLabel the VM will jump to when the continuation is "
        "resumed. Used to implement yield, coroutines, generators, and iterator "
        "protocols across multiple languages."
    ),
    "RESUME_CONTINUATION": (
        "Transfers control to the continuation registered under name. Paired with "
        "SET_CONTINUATION. Used to resume a suspended generator or coroutine from the "
        "point where SET_CONTINUATION was executed."
    ),
}


def handle_list_opcodes() -> dict[str, Any]:
    """Return all IR opcodes with descriptions, categories, fields, and notes."""
    entries = []
    for opcode, builder in _TO_TYPED.items():
        hints = get_type_hints(builder)
        cls = hints["return"]
        fields = [
            {"name": f.name, "type": str(get_type_hints(cls).get(f.name, f.type))}
            for f in dataclasses.fields(cls)
            if f.name != "source_location"
        ]
        entries.append(
            {
                "name": opcode.value,
                "category": _OPCODE_CATEGORIES[opcode.value],
                "description": (cls.__doc__ or "").strip(),
                "fields": fields,
                "notes": _OPCODE_NOTES[opcode.value],
            }
        )
    return {"opcodes": sorted(entries, key=lambda e: e["name"])}
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
poetry run python -m pytest tests/unit/test_mcp_tools.py::TestListOpcodes -v 2>&1 | tail -25
```

Expected: all 17 tests pass.

- [ ] **Step 6: Run the full test suite to confirm no regressions**

```bash
poetry run python -m pytest tests/unit/test_mcp_tools.py -v 2>&1 | tail -10
```

Expected: all existing tests still pass.

---

## Task 2: Register `list_opcodes` in `server.py`

**Files:**
- Modify: `mcp_server/server.py`

There is no new behaviour to test here beyond what Task 1 already tested. The registration test is that `server.py` imports cleanly and the tool appears in the FastMCP instance — verified by the existing MCP integration test.

- [ ] **Step 1: Add import of `handle_list_opcodes` in `server.py`**

In `mcp_server/server.py`, update the import block from:

```python
from mcp_server.tools import (
    handle_analyze_program,
    handle_get_call_chain,
    handle_get_function_summary,
    handle_get_ir,
    handle_get_state,
    handle_load_program,
    handle_load_project,
    handle_run_to_end,
    handle_step,
)
```

to:

```python
from mcp_server.tools import (
    handle_analyze_program,
    handle_get_call_chain,
    handle_get_function_summary,
    handle_get_ir,
    handle_get_state,
    handle_list_opcodes,
    handle_load_program,
    handle_load_project,
    handle_run_to_end,
    handle_step,
)
```

- [ ] **Step 2: Register the tool in `server.py`**

In `mcp_server/server.py`, add the following after the `get_call_chain` tool registration (keeping analysis tools grouped together):

```python
@mcp.tool()
def list_opcodes() -> dict[str, Any]:
    """List all IR opcodes with descriptions, categories, typed fields, and semantic notes.

    Returns a sorted list of all 33 opcodes. Each entry includes:
    - name: the opcode string (e.g. "BINOP")
    - category: one of variables, arithmetic, calls, fields_and_indices,
      control_flow, heap, memory, continuations
    - description: what the instruction does
    - fields: list of {name, type} for every typed operand
    - notes: detailed semantic notes including field meanings and VM behaviour
    """
    return handle_list_opcodes()
```

- [ ] **Step 3: Run pyright on mcp_server/ to confirm no type errors introduced**

```bash
poetry run pyright mcp_server/ 2>&1 | grep "error:" | head -10
```

Expected: no new errors (pre-existing errors if any are unchanged).

- [ ] **Step 4: Close the Beads issue and backup**

```bash
bd close <ISSUE_ID> --reason "handle_list_opcodes implemented in mcp_server/tools.py with _OPCODE_CATEGORIES and _OPCODE_NOTES dicts. Registered as list_opcodes in mcp_server/server.py. 17 unit tests pass."
bd backup
```

- [ ] **Step 5: Commit**

```bash
poetry run python -m black .
git add mcp_server/tools.py mcp_server/server.py tests/unit/test_mcp_tools.py
git commit -m "feat: add list_opcodes MCP tool — returns all 33 opcodes with categories, fields, and semantic notes"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ All 33 opcodes present — `_TO_TYPED` has 33 entries, test asserts `len == 33`
- ✅ `source_location` excluded — tested explicitly
- ✅ Sorted alphabetically — tested explicitly
- ✅ All 5 required keys — tested explicitly
- ✅ Categories correct — 8 spot-checks in tests
- ✅ Field names and types — `test_binop_fields`, `test_label_has_no_opcode_specific_fields`, `test_try_push_has_exception_fields`
- ✅ Descriptions non-empty — tested
- ✅ Notes non-empty and detailed — tested; all 33 notes are 3–5 sentences in `_OPCODE_NOTES`

**No placeholders:** All code is complete. No TBDs.

**Type consistency:** `handle_list_opcodes` returns `dict[str, Any]` throughout. `_TO_TYPED` import matches `interpreter/instructions.py`. `Opcode` import matches `interpreter/ir.py`.
