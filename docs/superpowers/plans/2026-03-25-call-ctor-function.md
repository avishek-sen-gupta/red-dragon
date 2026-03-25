# CallCtorFunction Instruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `CallCtorFunction` instruction with `Opcode.CALL_CTOR` that carries a `TypeExpr` type_hint for constructor calls. All constructor-via-`CallFunction` sites switch to `CallCtorFunction`.

**Architecture:** New instruction class `CallCtorFunction` with `func_name: str`, `type_hint: TypeExpr`, `args: tuple`. VM handler dispatches `CALL_CTOR` to the existing `_try_class_constructor_call`, passing `type_hint` as `TypeExpr`. Six frontends switch from `CallFunction` to `CallCtorFunction` at constructor sites.

**Tech Stack:** Python 3.13+, pytest, Poetry

**Issue:** red-dragon-wkv1

---

## Task 1: Add CallCtorFunction instruction and Opcode.CALL_CTOR

**Files:**
- Modify: `interpreter/ir.py` — add `CALL_CTOR` to Opcode enum
- Modify: `interpreter/instructions.py` — add `CallCtorFunction` class, update Instruction union, add to _to_typed converter
- Test: `tests/unit/test_type_hint_type_expr.py` — add CallCtorFunction tests

- [ ] **Step 1: Write failing tests**

```python
class TestCallCtorFunction:
    def test_is_instruction(self):
        from interpreter.instructions import CallCtorFunction
        inst = CallCtorFunction(
            result_reg=Register("%r0"),
            func_name="ArrayList",
            type_hint=ParameterizedType("ArrayList", (scalar("Integer"),)),
            args=(Register("%r1"),),
        )
        assert isinstance(inst, InstructionBase)
        assert inst.opcode == Opcode.CALL_CTOR

    def test_non_generic_constructor(self):
        from interpreter.instructions import CallCtorFunction
        inst = CallCtorFunction(
            result_reg=Register("%r0"),
            func_name="Foo",
            type_hint=scalar("Foo"),
            args=(),
        )
        assert inst.type_hint == scalar("Foo")
        assert str(inst) == "%r0 = call_ctor Foo"
```

- [ ] **Step 2: Add CALL_CTOR to Opcode enum**

In `interpreter/ir.py`:
```python
CALL_CTOR = "CALL_CTOR"
```

- [ ] **Step 3: Add CallCtorFunction class**

In `interpreter/instructions.py`:
```python
@dataclass(frozen=True)
class CallCtorFunction(InstructionBase):
    """CALL_CTOR: call a class constructor with typed type hint."""

    result_reg: Register = NO_REGISTER
    func_name: str = ""
    type_hint: TypeExpr = UNKNOWN
    args: tuple[Register | SpreadArguments, ...] = ()

    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.CALL_CTOR

    @property
    def operands(self) -> list[Any]:
        return [self.func_name, *(str(a) if isinstance(a, Register) else a for a in self.args)]
```

Add `CallCtorFunction` to the `Instruction` union type.

- [ ] **Step 4: Add _to_typed converter for CALL_CTOR**

```python
def _call_ctor(inst):
    ops = inst.operands
    raw_args = ops[1:]
    args = tuple(
        a if isinstance(a, SpreadArguments) else _as_register(a)
        for a in raw_args
    )
    raw_hint = str(ops[0]) if ops else ""
    return CallCtorFunction(
        result_reg=inst.result_reg,
        func_name=raw_hint,
        type_hint=scalar(raw_hint) if raw_hint else UNKNOWN,
        args=args,
        source_location=inst.source_location,
    )
```

Add to `_TO_TYPED`: `Opcode.CALL_CTOR: _call_ctor`

- [ ] **Step 5: Run tests, verify gate, commit**

---

## Task 2: Wire VM handler for CALL_CTOR

**Files:**
- Modify: `interpreter/handlers/calls.py` — add `_handle_call_ctor` handler
- Modify: `interpreter/vm/executor.py` — add CALL_CTOR to dispatch table
- Modify: `interpreter/handlers/calls.py` — change `type_hint_source: str` to `type_hint: TypeExpr` on `_try_class_constructor_call`

- [ ] **Step 1: Add _handle_call_ctor handler**

The handler delegates to `_try_class_constructor_call` with the `type_hint` from the instruction. It follows the same pattern as `_handle_call_function` but passes the typed type_hint.

- [ ] **Step 2: Change `_try_class_constructor_call` signature**

`type_hint_source: str = ""` → `type_hint: TypeExpr = UNKNOWN`
Line 145: `type_hint = parse_type(type_hint_source) if type_hint_source else scalar(class_name)` → `type_hint = type_hint if type_hint else scalar(class_name)`

- [ ] **Step 3: Add CALL_CTOR to executor dispatch**

- [ ] **Step 4: Run tests, verify gate, commit**

---

## Task 3: Migrate frontends

**Files:** 6 frontend expression files

For each frontend, change constructor lowering from:
```python
CallFunction(result_reg=reg, func_name=type_name, args=tuple(arg_regs))
```
to:
```python
CallCtorFunction(result_reg=reg, func_name=type_name, type_hint=scalar(type_name), args=tuple(arg_regs))
```

For now, all pass `scalar(type_name)` as type_hint. Parameterized type parsing (e.g., parsing `ArrayList<Integer>` from the tree-sitter generic_type node) is a follow-up per frontend.

Sites:
- `interpreter/frontends/java/expressions.py:77`
- `interpreter/frontends/csharp/expressions.py:133`
- `interpreter/frontends/scala/expressions.py:389`
- `interpreter/frontends/cpp/expressions.py:42`
- `interpreter/frontends/pascal/declarations.py:159`
- `interpreter/frontends/go/expressions.py:262`

Add `from interpreter.instructions import CallCtorFunction` to each file.

- [ ] **Step 1: Migrate all 6 sites**
- [ ] **Step 2: Run full test suite**
- [ ] **Step 3: Verify gate, commit, close issue**

---

## Task 4: Update infrastructure (CFG, dataflow, etc.)

Any code that pattern-matches on `CallFunction` for constructor detection may need to also handle `CallCtorFunction`. Check:
- `interpreter/cfg.py` — does it special-case CALL_FUNCTION?
- `interpreter/interprocedural/*` — call graph extraction
- `interpreter/types/type_inference.py` — function call type inference
- `interpreter/registry.py` — function scanning

Add `CallCtorFunction` alongside `CallFunction` in isinstance checks where needed.

- [ ] **Step 1: Grep for isinstance(inst, CallFunction) and opcode == Opcode.CALL_FUNCTION**
- [ ] **Step 2: Add CallCtorFunction to relevant checks**
- [ ] **Step 3: Run full test suite, verify gate, commit**
