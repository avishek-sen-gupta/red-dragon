# Convention-neutral CALL_WITH_MEMORY Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `CALL_WITH_MEMORY` becomes "call the function found at this location, giving it this memory"; the COBOL lowering owns the naming convention by which programs register and CALLs find them.

**Architecture:** Each COBOL program's init block registers its entry function under `__entry_<PROGRAM-ID>`; the entry function declares its argument parameter with `SYMBOLIC param:__call_arguments`. The opcode carries two operands — a location (a `VarName`, or a `Register` holding that name for `CALL identifier`) and the memory register — and its handler only looks the location up, binds the memory to the callee's first declared parameter, and enters it. The convention's names live in one new module, `interpreter/cobol/program_object.py`, which the forge imports.

**Tech Stack:** Python 3.13, pytest, uv, pyright, python-fp-lint (ratchet), import-linter. Two repos: red-dragon (`~/code/red-dragon`, Tasks 1–3) and red-dragon-forge (`~/code/red-dragon-forge`, Task 4, after red-dragon is pushed).

**Spec:** `docs/superpowers/specs/2026-10-13-convention-neutral-call-with-memory-design.md`

## Global Constraints

- red-dragon may know COBOL only in the COBOL lowering layer and the hooks it takes; the VM reaches lowering-supplied behaviour only through indirection, never by name.
- `interpreter.handlers` must not import `interpreter.cobol` (import-linter contract `cobol-isolation`); the handler therefore cannot use `program_object.py`.
- Both operands always render, in fixed order: `%r = call_with_memory <location> <memory>`.
- `vendor/red-dragon` in the forge is never edited; forge changes come after red-dragon is pushed, with a submodule bump.
- Every commit runs the hooks: Black, pyright, python-fp-lint ratchet (a commit may not raise the violation count; touching a file adopts its violations), import-linter, the full suite, the terminology guard, Talisman. Hooks are never skipped.
- Talisman flags some ordinary English words. When it does so for incidental wording in a test, docstring or commit message, reword it ("gives", "hands", "succeeds"). When it flags an identifier, add or update the file's `.talismanrc` entry with the checksum Talisman reports.
- No comments beyond a one-line module/class header; existing docstrings are updated where they describe the old protocol.
- Assertions are not weakened. Expected values change only where the spec mandates it (each such change is named in its step).

## Review Focus

1. A `CALL identifier` whose field holds a lower-case program name (`'helper'`) — must still call HELPER: COBOL names ignore case. Pinned in Task 2, Step 1.
2. A program entered directly by a harness (cicada's COMMAREA, jackal's PARM), not by CALL — its LINKAGE must still bind from the arguments the harness injects under `ARGUMENTS_PARAM`. Covered by cicada and jackal suites in Task 4.
3. A literal CALL to a program that is not linked — must still produce a symbolic result, not raise. Pinned in Task 2, Step 1 (handler test).
4. A location bound to something other than a function reference — must be treated as unresolved, not crash. Pinned in Task 2, Step 1 (handler test).
5. The CardDemo screens over TN3270 — a regression here would not show in red-dragon's suite. Task 4 runs the c3270 recording and checks frames.

---

### Task 1: The convention module and self-registration

The init block registers each program's entry function under `__entry_<PID>`, and the entry function declares its argument parameter. Purely additive: the handler still dispatches through `__prog_<PID>.__init_params__`, which this task leaves in place.

**Files:**
- Create: `interpreter/cobol/program_object.py`
- Modify: `interpreter/cobol/lower_program_init.py`
- Modify: `interpreter/cobol/lower_data_division.py` (the `__prog_` load near line 133; the `__call_arguments` load near line 190)
- Test: `tests/unit/test_lower_program_init.py`

**Interfaces:**
- Produces:
  - `interpreter.cobol.program_object.ENTRY_PREFIX: str` = `"__entry_"`
  - `interpreter.cobol.program_object.ARGUMENTS_PARAM: VarName` = `VarName("__call_arguments")`
  - `interpreter.cobol.program_object.WORKING_STORAGE_FIELD: FieldName` = `FieldName("ws_handle")`
  - `interpreter.cobol.program_object.entry_var(program_id: str) -> VarName` — `__entry_<UPPER>`
  - `interpreter.cobol.program_object.program_var(program_id: str) -> VarName` — `__prog_<UPPER>`
  - IR: init block contains `store_var __entry_<PID> %e` where `%e` is the entry function's `CONST`; the entry function's block is `func_init_params_<pid>_0:`, `%s = symbolic param:__call_arguments`, `branch func_<pid>_0`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_lower_program_init.py` (add `Branch, Const, Label_, NewObject, Symbolic` to the `interpreter.instructions` import and `from interpreter.frontend import make_cobol_parser`, `from interpreter.ir import CodeLabel`, `from interpreter.project.cobol_compile import compile_cobol` at the top):

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_registers_the_program_and_its_entry_function():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "subprog", _ws_layout_5bytes())
    program_object = next(i for i in ctx.instructions if isinstance(i, NewObject))
    entry_ref = next(
        i
        for i in ctx.instructions
        if isinstance(i, Const) and i.value == "func_init_params_subprog_0"
    )
    registered = {
        str(i.name): i.value_reg
        for i in ctx.instructions
        if isinstance(i, StoreVar) and str(i.name).startswith(("__prog_", "__entry_"))
    }
    assert registered == {
        "__prog_SUBPROG": program_object.result_reg,
        "__entry_SUBPROG": entry_ref.result_reg,
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_entry_function_declares_the_call_arguments_parameter():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    start = next(
        n
        for n, i in enumerate(ctx.instructions)
        if isinstance(i, Label_) and str(i.label) == "func_init_params_subprog_0"
    )
    declaration, onward = ctx.instructions[start + 1], ctx.instructions[start + 2]
    assert (
        type(declaration),
        declaration.hint,
        type(onward),
        str(onward.label),
    ) == (Symbolic, "param:__call_arguments", Branch, "func_subprog_0")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_linked_entry_function_is_registered_with_its_parameter():
    source = (
        b"       IDENTIFICATION DIVISION.\n"
        b"       PROGRAM-ID. CALLER.\n"
        b"       PROCEDURE DIVISION.\n"
        b"           GOBACK.\n"
    )
    _, linked = compile_cobol(source, parser=make_cobol_parser())
    assert linked.merged_registry.func_params[
        CodeLabel("__main__.func_init_params_caller_0")
    ] == ["__call_arguments"]
```

- [ ] **Step 2: Run them and see them fail**

Run: `cd ~/code/red-dragon && uv run --no-sync python -m pytest tests/unit/test_lower_program_init.py -q`
Expected: the three new tests FAIL — the first with `__entry_SUBPROG` missing from `registered`, the second on `type(declaration)` being `Branch`, the third with `[]` instead of `["__call_arguments"]`. The existing tests succeed.

- [ ] **Step 3: Create the convention module**

`interpreter/cobol/program_object.py`:

```python
"""The convention by which a COBOL program registers itself and a CALL finds it."""

from __future__ import annotations

from interpreter.field_name import FieldName
from interpreter.var_name import VarName

ENTRY_PREFIX = "__entry_"
PROGRAM_PREFIX = "__prog_"
ARGUMENTS_PARAM = VarName("__call_arguments")
WORKING_STORAGE_FIELD = FieldName("ws_handle")


def entry_var(program_id: str) -> VarName:
    return VarName(f"{ENTRY_PREFIX}{program_id.upper()}")


def program_var(program_id: str) -> VarName:
    return VarName(f"{PROGRAM_PREFIX}{program_id.upper()}")
```

- [ ] **Step 4: Register the entry function and declare its parameter**

In `interpreter/cobol/lower_program_init.py`:

- Import `from interpreter import constants`, `Symbolic` from `interpreter.instructions`, and `ARGUMENTS_PARAM, WORKING_STORAGE_FIELD, entry_var, program_var` from `interpreter.cobol.program_object`.
- `singleton_var = VarName(f"__prog_{pid_upper}")` becomes `singleton_var = program_var(program_id)` in both `lower_program_init` and `lower_ws_from_singleton`; `FieldName("ws_handle")` becomes `WORKING_STORAGE_FIELD` in both. Drop `pid_upper` where it becomes unused.
- Replace the tail of `lower_program_init` (from `ctx.emit_inst(StoreVar(name=singleton_var, value_reg=ptr_reg))` to `return after_label`) with:

```python
    ctx.emit_inst(StoreVar(name=singleton_var, value_reg=ptr_reg))
    ctx.emit_inst(StoreVar(name=entry_var(program_id), value_reg=init_reg))
    ctx.emit_inst(Branch(label=after_label))

    ctx.emit_inst(Label_(label=init_params_label))
    ctx.emit_inst(
        Symbolic(
            result_reg=ctx.fresh_reg(),
            hint=f"{constants.PARAM_PREFIX}{ARGUMENTS_PARAM}",
        )
    )
    ctx.emit_inst(Branch(label=proc_label))

    return after_label
```

- Update the module docstring's IR listing: after `STORE_VAR __prog_<PID>, %ptr` add `STORE_VAR __entry_<PID>, %init_reg`, and in part 2 replace `BRANCH func_<pid>_0 → __call_arguments already injected by handler` with `SYMBOLIC param:__call_arguments` then `BRANCH func_<pid>_0`.

- [ ] **Step 5: Use the names in the LINKAGE binding**

In `interpreter/cobol/lower_data_division.py`, import `ARGUMENTS_PARAM, program_var` from `interpreter.cobol.program_object`; replace `VarName(f"__prog_{program_id.upper()}")` with `program_var(program_id)` and `VarName("__call_arguments")` with `ARGUMENTS_PARAM`. In the `lower_sectioned_data_division` docstring, "its argument in __call_arguments, which _handle_call_with_memory injects" becomes "its argument in the entry function's __call_arguments parameter".

- [ ] **Step 6: Run the tests**

Run: `uv run --no-sync python -m pytest tests/unit/test_lower_program_init.py tests/unit/test_handle_call_with_memory_singleton.py tests/unit/test_call_with_memory.py tests/integration/test_cobol_call_by_data_name.py tests/integration/test_cobol_programs.py -q`
Expected: all succeed (the handler still binds `__call_arguments` itself, and the symbolic parameter reads that binding).

- [ ] **Step 7: Mutation check**

Delete the new `StoreVar(name=entry_var(...))` line → the first new test fails. Change the `Symbolic` hint to `"param:__args"` → the second and third fail. Restore.

- [ ] **Step 8: Commit**

```bash
git add interpreter/cobol/program_object.py interpreter/cobol/lower_program_init.py interpreter/cobol/lower_data_division.py tests/unit/test_lower_program_init.py
git commit -m "feat(cobol): programs register their entry function under __entry_<PID>

The COBOL lowering now states the CALL convention in one module,
interpreter/cobol/program_object.py. Each init block stores its entry function
in __entry_<PID>, and the entry function declares param:__call_arguments, so
the convention is visible in IR. The handler still dispatches the old way
(red-dragon-qhun)."
```

---

### Task 2: The two-operand opcode, its neutral handler, and the CALL lowering

**Files:**
- Modify: `interpreter/instructions.py` (class `CallWithMemory` near line 581; `_call_with_memory` near line 1416)
- Modify: `interpreter/handlers/calls.py` (`UnresolvedProgramError` docstring near line 63; `_handle_call_with_memory` near line 712)
- Modify: `interpreter/cobol/lower_call.py` (`lower_call` near line 133; new `_emit_entry_var_name`)
- Modify: `interpreter/cobol/lower_program_init.py` (drop the `__init_params__` store)
- Modify: `interpreter/cobol/cobol_frontend.py:251` (comment wording)
- Modify: `docs/ir-reference.md` (CALL_WITH_MEMORY, near line 354), `docs/notes-on-vm-design.md` (§12.1, §12.2), `docs/frontend-design/cobol.md` (CALL row), `docs/architectural-design-decisions.md` (ADR-182, after ADR-181)
- Test: `tests/unit/test_call_with_memory.py`, `tests/unit/test_handle_call_with_memory_singleton.py`, `tests/unit/test_lower_call_with_memory.py`, `tests/unit/test_lower_program_init.py`, `tests/unit/test_typed_instructions.py`, `tests/integration/test_cobol_call_by_data_name.py`

**Interfaces:**
- Consumes: `entry_var`, `ENTRY_PREFIX` from Task 1; registration IR from Task 1.
- Produces: `CallWithMemory(result_reg: Register, location: VarName | Register, memory: Register)`; `operands == [str(location), str(memory)]`; `reads()` lists `location` (when a `Register`) and `memory`.

- [ ] **Step 1: Write the failing tests**

(a) `tests/integration/test_cobol_call_by_data_name.py` — a characterization test that succeeds today and must keep succeeding:

```python
@covers(CobolFeature.CALL_BY_IDENTIFIER, CobolFeature.CALL_USING)
def test_call_data_name_is_matched_without_regard_to_case(tmp_path):
    vm = _run(
        tmp_path,
        _main_src(
            "       01 WS-PROG PIC X(8) VALUE 'helper'.\n",
            "           CALL WS-PROG USING BY REFERENCE WS-TICKET.\n",
        ),
    )
    assert _ticket(vm) == 77
```

(b) In `tests/unit/test_call_with_memory.py`, replace `test_instruction_carries_the_callee_and_its_argument_array` with:

```python
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_instruction_carries_a_location_and_its_memory(self):
        from interpreter.instructions import CallWithMemory

        by_name = CallWithMemory(
            result_reg=Register("%r9"),
            location=VarName("__entry_SUBPROG"),
            memory=Register("%r1"),
        )
        by_register = CallWithMemory(location=Register("%r3"), memory=Register("%r1"))

        assert (
            by_name.opcode,
            by_name.operands,
            by_name.reads(),
            str(by_name),
            by_register.operands,
            by_register.reads(),
        ) == (
            Opcode.CALL_WITH_MEMORY,
            ["__entry_SUBPROG", "%r1"],
            [Register("%r1")],
            "%r9 = call_with_memory __entry_SUBPROG %r1",
            ["%r3", "%r1"],
            [Register("%r3"), Register("%r1")],
        )
```

(c) In the same file, replace `_make_vm_with_func_ref`, `_make_handler_ctx` and `TestHandleCallWithMemory` with:

```python
def _vm_with(bindings: dict, registers: dict):
    from interpreter.func_name import FuncName as FN
    from interpreter.types.typed_value import typed_from_runtime
    from interpreter.vm.vm_types import StackFrame, VMState

    vm = VMState()
    vm.call_stack.append(
        StackFrame(
            function_name=FN("main"),
            local_vars={name: typed_from_runtime(v) for name, v in bindings.items()},
        )
    )
    vm.current_frame.registers.update(
        {reg: typed_from_runtime(v) for reg, v in registers.items()}
    )
    return vm


def _ctx_with(label, params: list[str]):
    import dataclasses

    from interpreter.cfg import CFG, BasicBlock
    from interpreter.ir import CodeLabel
    from interpreter.registry import FunctionRegistry
    from interpreter.vm.executor import _default_handler_context

    return dataclasses.replace(
        _default_handler_context(),
        cfg=CFG(blocks={label: BasicBlock(label=label)}),
        registry=FunctionRegistry(func_params={label: params}),
        current_label=CodeLabel("caller"),
        ip=4,
    )


def _entry(label):
    from interpreter.refs.func_ref import BoundFuncRef, FuncRef

    return BoundFuncRef(func_ref=FuncRef(name=FuncName("start"), label=label))


class TestHandleCallWithMemory:
    @pytest.mark.parametrize(
        "location, registers",
        [
            (VarName("obj_start"), {}),
            (Register("%n"), {Register("%n"): "obj_start"}),
        ],
    )
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_handler_calls_the_function_registered_under_any_name(
        self, location, registers
    ):
        from interpreter.handlers.calls import _handle_call_with_memory
        from interpreter.instructions import CallWithMemory
        from interpreter.ir import CodeLabel

        label = CodeLabel("func_start_0")
        vm = _vm_with(
            {VarName("obj_start"): _entry(label)},
            {**registers, Register("%m"): "memory"},
        )

        result = _handle_call_with_memory(
            CallWithMemory(
                result_reg=Register("%r"), location=location, memory=Register("%m")
            ),
            vm,
            _ctx_with(label, ["args"]),
        )
        push = result.update.call_push

        assert (
            result.update.next_label,
            {name: tv.value for name, tv in result.update.var_writes.items()},
            (push.function_name, push.return_label, push.return_ip, push.result_reg),
        ) == (
            label,
            {VarName("args"): "memory"},
            (FuncName("start"), CodeLabel("caller"), 5, Register("%r")),
        )

    @pytest.mark.parametrize(
        "bindings",
        [{}, {VarName("obj_start"): "not a function"}],
    )
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_an_unresolved_literal_location_is_left_to_the_call_resolver(
        self, bindings
    ):
        from interpreter.handlers.calls import _handle_call_with_memory
        from interpreter.instructions import CallWithMemory
        from interpreter.ir import CodeLabel

        vm = _vm_with(bindings, {Register("%m"): "memory"})
        result = _handle_call_with_memory(
            CallWithMemory(
                result_reg=Register("%r"),
                location=VarName("obj_start"),
                memory=Register("%m"),
            ),
            vm,
            _ctx_with(CodeLabel("func_start_0"), ["args"]),
        )

        assert (
            result.update.call_push,
            result.update.register_writes[Register("%r")].value.constraints,
        ) == (None, ["obj_start()"])

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_an_unresolved_runtime_location_raises_naming_the_variable(self):
        from interpreter.handlers.calls import (
            UnresolvedProgramError,
            _handle_call_with_memory,
        )
        from interpreter.instructions import CallWithMemory
        from interpreter.ir import CodeLabel

        vm = _vm_with({}, {Register("%n"): "obj_missing", Register("%m"): "memory"})

        with pytest.raises(UnresolvedProgramError, match="obj_missing"):
            _handle_call_with_memory(
                CallWithMemory(location=Register("%n"), memory=Register("%m")),
                vm,
                _ctx_with(CodeLabel("func_start_0"), ["args"]),
            )
```

Add `import pytest` to the file's imports. Keep `TestCallWithMemoryOpcode` and `test_in_instruction_union` unchanged.

(d) `tests/unit/test_handle_call_with_memory_singleton.py`: in `_make_vm_with_singleton`, register the entry function the new way — add `vm.call_stack[0].local_vars[VarName(f"__entry_{pid_upper}")] = typed(init_params_ref)` and drop `FieldName("__init_params__")` from the singleton's fields. In both tests, build the instruction as `CallWithMemory(location=VarName(f"__entry_{pid}"), memory=params_reg)` (the second keeps `result_reg=result_reg`), and give the context a registry: `replace(_default_handler_context(), cfg=cfg, registry=FunctionRegistry(func_params={init_params_label: ["__call_arguments"]}), current_label=CodeLabel("entry"))` (import `FunctionRegistry` from `interpreter.registry`). Assertions unchanged. Module docstring: "dispatches via the entry function registered under __entry_<PID>".

(e) `tests/unit/test_lower_call_with_memory.py` — append (import `CallWithMemory, CallFunction, Const` from `interpreter.instructions`, `RefModOperand` from `cobol_asg.ref_mod`, `VarName` from `interpreter.var_name`):

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_literal_call_looks_up_the_callee_entry_var():
    ctx, materialised = _materialised_with_ws("WS-PARAM")
    stmt = CallStatement(
        target=CallTarget.of_literal("subprog"),
        using=[CallUsingParam(name="WS-PARAM", param_type="REFERENCE")],
        giving="",
    )
    lower_call(ctx, stmt, materialised)
    (call,) = [i for i in ctx.instructions if isinstance(i, CallWithMemory)]
    assert (call.location, call.operands) == (
        VarName("__entry_SUBPROG"),
        ["__entry_SUBPROG", str(call.memory)],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_data_name_call_computes_the_entry_var_in_ir():
    ctx, materialised = _materialised_with_ws("WS-PROG")
    stmt = CallStatement(
        target=CallTarget.of_identifier(RefModOperand(name="WS-PROG")),
        using=[],
        giving="",
    )
    lower_call(ctx, stmt, materialised)
    producers = {i.result_reg: i for i in ctx.instructions if i.result_reg.is_present()}
    (call,) = [i for i in ctx.instructions if isinstance(i, CallWithMemory)]
    concat = producers[call.location]
    prefix, upper = (producers[a] for a in concat.args)
    trim = producers[upper.args[0]]
    assert (
        str(concat.func_name),
        prefix.value,
        str(upper.func_name),
        str(trim.func_name),
    ) == ("__string_concat_pair", "__entry_", "__upper_case", "__cobol_trim")
```

If `RefModOperand` requires more constructor arguments than `name`, give `ref_mod_start=None, ref_mod_length=None` as its docstring shows.

(f) `tests/unit/test_lower_program_init.py::test_lower_program_init_publishes_every_singleton_field` — the spec removes the `__init_params__` field, so its expected list becomes `["ws_handle", "return_code_handle", "run"]` (spec-mandated change).

(g) `tests/unit/test_typed_instructions.py` — append:

```python
class TestCallWithMemoryToTyped:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_a_named_location_and_a_register_location(self):
        from interpreter.instructions import CallWithMemory
        from interpreter.var_name import VarName

        named = IRInstruction(
            opcode=Opcode.CALL_WITH_MEMORY,
            result_reg=Register("%9"),
            operands=["__entry_CALLEE", "%4"],
        )
        computed = IRInstruction(
            opcode=Opcode.CALL_WITH_MEMORY,
            result_reg=Register("%9"),
            operands=["%7", "%4"],
        )
        assert (
            type(named),
            named.location,
            named.memory,
            computed.location,
            str(computed),
        ) == (
            CallWithMemory,
            VarName("__entry_CALLEE"),
            Register("%4"),
            Register("%7"),
            "%9 = call_with_memory %7 %4",
        )
```

- [ ] **Step 2: Run them and see the right failures**

Run: `uv run --no-sync python -m pytest tests/unit/test_call_with_memory.py tests/unit/test_handle_call_with_memory_singleton.py tests/unit/test_lower_call_with_memory.py tests/unit/test_lower_program_init.py tests/unit/test_typed_instructions.py tests/integration/test_cobol_call_by_data_name.py -q`
Expected: FAIL for (b)–(g) with `TypeError: ... unexpected argument 'location'` or the old operand shape; (a) succeeds (characterization).

- [ ] **Step 3: Reshape the instruction**

In `interpreter/instructions.py`, replace the `CallWithMemory` body (keep its decorator):

```python
class CallWithMemory(InstructionBase):
    """CALL_WITH_MEMORY: call the function found at a location, giving it memory.

    location: a VarName naming the variable that holds the callee's function
        reference, or a Register holding that variable's name as a string
        computed at run time. Which variable is the lowering's convention; the
        VM only looks it up.
    memory: the argument array -- per argument, by position, a region and an
        offset into it (or an OMITTED marker), and a count. It is bound to the
        callee's first declared parameter.
    result_reg: inherited from InstructionBase -- the callee's return value.
    """

    location: VarName | Register = NO_REGISTER
    memory: Register = NO_REGISTER

    @property
    def opcode(self) -> Opcode:
        return Opcode.CALL_WITH_MEMORY

    @property
    def operands(self) -> list[Any]:
        return [str(self.location), str(self.memory)]

    def reads(self) -> list[StorageIdentifier]:
        return [
            operand
            for operand in (self.location, self.memory)
            if isinstance(operand, Register) and operand.is_present()
        ]
```

Replace `_call_with_memory`:

```python
def _call_with_memory(inst: Any) -> CallWithMemory:
    location, memory = (str(op) for op in inst.operands)
    return CallWithMemory(
        result_reg=inst.result_reg,
        location=Register(location) if location.startswith("%") else VarName(location),
        memory=Register(memory),
        source_location=inst.source_location,
    )
```

If `VarName` is not yet imported in `instructions.py`, import it from `interpreter.var_name`.

- [ ] **Step 4: Make the handler neutral**

In `interpreter/handlers/calls.py`, replace `_handle_call_with_memory` with:

```python
def _handle_call_with_memory(
    inst: InstructionBase,
    vm: VMState,
    ctx: HandlerContext,
) -> ExecutionResult:
    """Handle CALL_WITH_MEMORY: call the function found at a location.

    The location names a variable -- directly, or as the string a register
    holds. That variable holds the callee's function reference; its first
    declared parameter is bound to the memory operand, and control enters the
    callee in a new frame. A literal location that resolves to nothing goes to
    the configured call resolver; a computed one raises UnresolvedProgramError.
    """
    t = inst
    assert isinstance(t, CallWithMemory)
    target = _location_var(vm, t.location)
    match _bound(vm, target):
        case (BoundFuncRef() as entry, *_) if entry.func_ref.label in ctx.cfg.blocks:
            return _enter(entry, _resolve_reg(vm, t.memory), t, ctx)
        case _ if isinstance(t.location, Register):
            raise UnresolvedProgramError(
                f"CALL resolved at run time to {target}, but nothing in this run "
                "unit is registered under it"
            )
        case _:
            return ctx.call_resolver.resolve_call(str(target), [], inst, vm)


def _location_var(vm: VMState, location: VarName | Register) -> VarName:
    match location:
        case Register():
            return VarName(str(_resolve_reg(vm, location).value))
        case _:
            return location


def _bound(vm: VMState, name: VarName) -> tuple[Any, ...]:
    return tuple(
        frame.local_vars[name].value
        for frame in reversed(vm.call_stack)
        if name in frame.local_vars
    )


def _enter(
    entry: BoundFuncRef,
    memory: TypedValue,
    inst: CallWithMemory,
    ctx: HandlerContext,
) -> ExecutionResult:
    label = entry.func_ref.label
    params = ctx.registry.func_params.get(label, [])
    return ExecutionResult.success(
        StateUpdate(
            call_push=StackFramePush(
                function_name=entry.func_ref.name,
                return_label=ctx.current_label,
                return_ip=ctx.ip + 1,
                result_reg=inst.result_reg,
            ),
            next_label=label,
            reasoning=f"call_with_memory {inst.location} -> {label}",
            var_writes={VarName(name): memory for name in params[:1]},
        )
    )
```

Use the module's existing imports for `Any`, `TypedValue`, `Register`, `StackFramePush`, `StateUpdate`; add any that are missing. Reword `UnresolvedProgramError`'s docstring to "A CALL whose location was computed at run time named nothing registered in the run unit." with the rest of its explanation kept. If the ratchet reports a new violation in this file (complexity, `Any`), split or retype until the count does not rise.

- [ ] **Step 5: Lower CALL to a location**

In `interpreter/cobol/lower_call.py`, import `ENTRY_PREFIX, entry_var` from `interpreter.cobol.program_object`. Add below `_emit_callee_name`:

```python
def _emit_entry_var_name(
    ctx: EmitContext,
    operand: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    """The entry variable a ``CALL identifier`` names, computed in IR: the field's
    text trimmed of spaces, upper-cased (COBOL program names ignore case) and
    prefixed, so the VM looks it up as it is."""
    name_reg = _emit_callee_name(ctx, operand, materialised, span=span)
    trimmed = _emit_builtin(ctx, BuiltinName.TRIM, (name_reg,), span=span)
    upper = _emit_builtin(ctx, BuiltinName.UPPER_CASE, (trimmed,), span=span)
    prefix = ctx.const_to_reg(ENTRY_PREFIX, span=span)
    return _emit_builtin(
        ctx, BuiltinName.STRING_CONCAT_PAIR, (prefix, upper), span=span
    )


def _emit_builtin(
    ctx: EmitContext,
    name: str,
    args: tuple[Register, ...],
    *,
    span: SourceSpan | None,
) -> Register:
    result = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=result, func_name=FuncName(name), args=args),
        span=span,
    )
    return result
```

In `lower_call`, replace the `target_reg = (...)` block with:

```python
    location = (
        _emit_entry_var_name(ctx, target.identifier, materialised, span=span)
        if target.identifier is not None
        else entry_var(target.literal)
    )
```

and the instruction with:

```python
    ctx.emit_inst(
        CallWithMemory(result_reg=result_reg, location=location, memory=args_reg),
        span=span,
    )
```

Remove imports that become unused (`NO_REGISTER` if nothing else uses it).

- [ ] **Step 6: Stop storing the old entry field**

In `interpreter/cobol/lower_program_init.py`, delete the `StoreField(... FieldName("__init_params__") ...)` emission and its docstring line `STORE_FIELD %ptr, __init_params__, %init_reg`; keep `init_reg` (the `__entry_` registration stores it). In `interpreter/cobol/cobol_frontend.py:251`, the comment becomes `# Procedure division function — entered through the program's entry function`.

- [ ] **Step 7: Run the tests**

Run: `uv run --no-sync python -m pytest tests/unit/test_call_with_memory.py tests/unit/test_handle_call_with_memory_singleton.py tests/unit/test_lower_call_with_memory.py tests/unit/test_lower_program_init.py tests/unit/test_typed_instructions.py tests/integration/test_cobol_call_by_data_name.py tests/integration/test_cobol_return_code.py tests/integration/test_cobol_programs.py -q`
Expected: all succeed.

- [ ] **Step 8: Full suite**

Run: `uv run --no-sync python -m pytest tests -q -n auto --ignore=tests/external > /tmp/qhun-t2.log 2>&1; tail -3 /tmp/qhun-t2.log`
Expected: no failures. A failure asserting an unlinked COBOL callee's symbolic name as `NAME(...)` is the spec's documented change: its expected value becomes `__entry_NAME(...)` — ledger it as a ruling. Any other failure is a defect to debug, not to re-baseline.

- [ ] **Step 9: Mutation check**

(1) In `_enter`, bind `params[1:2]` instead of `params[:1]` → the neutrality test fails. (2) In `_emit_entry_var_name`, drop the UPPER-CASE call → `test_call_data_name_is_matched_without_regard_to_case` and the IR-chain test fail. (3) In the handler, swap the two unresolved arms' conditions → both unresolved tests fail. Restore after each.

- [ ] **Step 10: Docs**

- `docs/ir-reference.md`, CALL_WITH_MEMORY: first line "Call the function found at a location, giving it memory (an argument array)." Field table: `result_reg` (as now), `location` (`VarName | Register` — the variable holding the callee's function reference, or a register holding that variable's name), `memory` (`Register` — argument array). Keep the argument-array paragraph. Replace the dispatch list with: 1. Take the variable from `location`, or from the string its register holds. 2. Find it in the scope chain; it holds a `BoundFuncRef`. 3. Push a frame with the callee's first declared parameter bound to `memory`, and branch to its label. Then: "COBOL's convention, owned by `interpreter/cobol/program_object.py`: each program's init block stores its entry function in `__entry_<PROGRAM-ID>`; the entry function declares `param:__call_arguments`; a literal CALL's location is `__entry_<NAME>`, and `CALL identifier` computes it in IR (TRIM, UPPER-CASE, prefix)." Unresolved paragraph: literal → call resolver; register location → `UnresolvedProgramError`. Examples: `%r9 = call_with_memory __entry_SUBPROG %r8` and `%r9 = call_with_memory %r7 %r8     # location computed: %r7 holds "__entry_SUBPROG"`.
- `docs/notes-on-vm-design.md` §12.1: the singleton's fields are `ws_handle`, `return_code_handle`, `run`; add "and the init block registers the entry function `func_init_params_<PID>_0` under `__entry_<PID>`; that function declares `param:__call_arguments` and branches to the procedure." §12.2 step 2: "`_handle_call_with_memory` looks up the location's variable, binds the argument array to the callee's first declared parameter, and enters it; the COBOL lowering computes the location (`__entry_<NAME>`, trimmed and upper-cased in IR for `CALL identifier`)."
- `docs/frontend-design/cobol.md` CALL row: "dispatches via `CALL_WITH_MEMORY __entry_<NAME>`, binding the array to the callee entry function's `__call_arguments` parameter" in place of "whose handler injects it as `__call_arguments`".
- `docs/architectural-design-decisions.md`, after ADR-181:

```markdown
### ADR-182: CALL_WITH_MEMORY is convention-neutral; the COBOL lowering owns the CALL convention (2026-10-13)

**Context:** COBOL's CALL protocol is a naming convention: a program registers its entry under a name, a CALL looks the name up. `_handle_call_with_memory` spelled out half of it — it built `__prog_<NAME>`, applied COBOL's case and blank rules, read the `__init_params__` field and bound `__call_arguments` — so the language-neutral handler layer knew COBOL (red-dragon-qhun). The forge typed the same names again.

**Decision:** `CALL_WITH_MEMORY` takes two operands: a location (a `VarName`, or a register holding one as a string) and the memory argument array. The handler looks the location up, binds the memory to the callee's first declared parameter and enters it. The COBOL lowering owns the convention in `interpreter/cobol/program_object.py`: init blocks store the entry function in `__entry_<PID>`, entry functions declare `param:__call_arguments`, literal CALLs name `__entry_<NAME>`, and `CALL identifier` computes it in IR with TRIM and UPPER-CASE. The `__init_params__` field is gone.

**Consequences:** The handler holds no prefix, case rule, field name or variable name. An unlinked literal callee's symbolic result is named `__entry_<NAME>(...)`. Registrations are ordinary variables, relying on the `__` prefix not to collide; production toolchains keep symbols in a separate table. Resolving literal CALLs at link time is red-dragon-ajps.
```

- [ ] **Step 11: Commit**

```bash
git add interpreter/instructions.py interpreter/handlers/calls.py interpreter/cobol/lower_call.py interpreter/cobol/lower_program_init.py interpreter/cobol/cobol_frontend.py tests/unit/test_call_with_memory.py tests/unit/test_handle_call_with_memory_singleton.py tests/unit/test_lower_call_with_memory.py tests/unit/test_lower_program_init.py tests/unit/test_typed_instructions.py tests/integration/test_cobol_call_by_data_name.py docs/ir-reference.md docs/notes-on-vm-design.md docs/frontend-design/cobol.md docs/architectural-design-decisions.md
git commit -m "refactor(vm): CALL_WITH_MEMORY calls a location with memory; COBOL owns the convention

The opcode takes two operands, a location and the argument array. Its handler
looks the location up, binds the array to the callee's first declared parameter
and enters it; it no longer builds __prog_ names, applies COBOL case and blank
rules, or reads __init_params__ and __call_arguments by name. The COBOL lowering
names __entry_<NAME> for a literal CALL and computes it in IR for CALL
identifier. ADR-182; closes red-dragon-qhun's core half."
```

---

### Task 3: `entry_func_label` as a null object

**Files:**
- Modify: `interpreter/project/types.py:138`
- Modify: `tests/unit/cobol/test_arithmetic_decimal_precision.py:74-90`
- Test: `tests/unit/project/test_cobol_compile.py`

**Interfaces:**
- Produces: `LinkedProgram.entry_func_label: CodeLabel = NO_LABEL` (never `None`).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/project/test_cobol_compile.py` (import `NO_LABEL` from `interpreter.ir`, `Language` from `interpreter.constants`, `compile_directory` from `interpreter.project.compiler`):

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_program_without_an_entry_function_carries_the_null_label(tmp_path):
    (tmp_path / "main.py").write_text("x = 1\n")
    assert compile_directory(tmp_path, Language.PYTHON).entry_func_label is NO_LABEL
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run --no-sync python -m pytest tests/unit/project/test_cobol_compile.py -q -k null_label`
Expected: FAIL — `None is NO_LABEL`.

- [ ] **Step 3: Change the field**

`interpreter/project/types.py`: `entry_func_label: CodeLabel | None = None` → `entry_func_label: CodeLabel = NO_LABEL` (import `NO_LABEL` from `interpreter.ir`). Keep its docstring; where it says "None", say "NO_LABEL".

In `tests/unit/cobol/test_arithmetic_decimal_precision.py::_compile_and_run`, replace the `getattr` / `if` / `else` block and its comment with:

```python
    ep = EntryPoint.function(lambda ref: ref.label == linked.entry_func_label)
```

- [ ] **Step 4: Run tests**

Run: `uv run --no-sync python -m pytest tests/unit/project/test_cobol_compile.py tests/unit/cobol/test_arithmetic_decimal_precision.py tests/integration/test_cobol_cli.py -q`
Expected: all succeed. Then `uv run --no-sync pyright interpreter/project/types.py interpreter/run.py interpreter/__main__.py` — 0 errors.

- [ ] **Step 5: Commit**

```bash
git add interpreter/project/types.py tests/unit/project/test_cobol_compile.py tests/unit/cobol/test_arithmetic_decimal_precision.py
git commit -m "refactor(project): LinkedProgram.entry_func_label is NO_LABEL, never None"
```

- [ ] **Step 6: Close out red-dragon**

```bash
bd -C ~/code/red-dragon update red-dragon-qhun --notes "Core half done (ADR-182): CALL_WITH_MEMORY is location + memory; COBOL lowering owns the convention in interpreter/cobol/program_object.py. Forge call sites follow in the forge bump."
bd export -o issues/issues.jsonl
git add issues/issues.jsonl && git commit -m "chore(issues): record red-dragon-qhun's core half"
git push origin main
```

---

### Task 4: Forge — import the convention, select the recorded entry

Runs in `~/code/red-dragon-forge` after Task 3 is pushed.

**Files:**
- Modify: `vendor/red-dragon` (submodule pointer)
- Modify: `cicada/cics/vm_init.py`, `cicada/cics/conversational.py`
- Modify: `jackal/jackal/cobol_step.py`, `jackal/jackal/le_abend.py`
- Modify: `cicada/tests/integration/cics/test_ceedays_stub.py`, `squall/tests/integration/squall_cobol_helpers.py`, `tests/integration/test_sql_adapter.py`

**Interfaces:**
- Consumes: `ARGUMENTS_PARAM`, `WORKING_STORAGE_FIELD`, `program_var` from `interpreter.cobol.program_object`; `LinkedProgram.entry_func_label: CodeLabel`.

- [ ] **Step 1: Bump and see the forge break where it spells the old protocol**

```bash
cd ~/code/red-dragon-forge/vendor/red-dragon && git fetch -q origin && git checkout -q origin/main && cd ../..
. ./bridge-env.sh && make test-all > /tmp/qhun-forge-before.log 2>&1; grep -E "^=+ .* in [0-9.]+s" /tmp/qhun-forge-before.log
```

Expected: every suite still succeeds — harness frames inject `__call_arguments`, which is still the parameter's name, and entry selection still finds `func_<pid>_0`. The steps below remove the forge's copies of the convention; the suites are the regression check.

- [ ] **Step 2: cicada**

`cicada/cics/vm_init.py`: in `make_cics_initial_vm`, import `ARGUMENTS_PARAM` from `interpreter.cobol.program_object` alongside `call_arguments`, and name the injection `ARGUMENTS_PARAM: call_arguments(vm, [commarea_addr])`; its docstring says "argument 0 of the entry parameter". Replace `make_entry_point`'s body and docstring with:

```python
def make_entry_point(program: Any) -> Any:
    """Enter the program at the entry label its compile recorded."""
    from interpreter.run import EntryPoint  # noqa: PLC0415

    return EntryPoint.function(lambda ref: ref.label == program.entry_func_label)
```

`cicada/cics/conversational.py`: same injection change in `_build_initial_vm`; `_entry_point` becomes the same three-line body with docstring "Mirror run_cics()'s entry: the label the compile recorded."

`cicada/tests/integration/cics/test_ceedays_stub.py`: the run's entry predicate becomes `EntryPoint.function(lambda r: r.label == linked.entry_func_label)` (use the test's `LinkedProgram` variable); the WS lookup uses `program_var("DRIVER")` and `WORKING_STORAGE_FIELD` from `interpreter.cobol.program_object` in place of `VarName("__prog_DRIVER")` and `FieldName("ws_handle")`.

- [ ] **Step 3: jackal**

`jackal/jackal/cobol_step.py`: import `ARGUMENTS_PARAM`; the step frame's `local_vars={ARGUMENTS_PARAM: arguments}`. `_entry_point` becomes:

```python
def _entry_point(linked: LinkedProgram) -> EntryPoint:
    """Enter the program at the entry label its compile recorded."""
    return EntryPoint.function(lambda ref: ref.label == linked.entry_func_label)
```

`jackal/jackal/le_abend.py`: `_SINGLETON = program_var("CEE3ABD")` and `_WORKING_STORAGE = WORKING_STORAGE_FIELD`, imported from `interpreter.cobol.program_object`; drop now-unused `FieldName`/`VarName` imports.

- [ ] **Step 4: squall and root test helpers**

`squall/tests/integration/squall_cobol_helpers.py` and `tests/integration/test_sql_adapter.py`: replace the `entry_point = EntryPoint.top_level()` / `if linked.func_symbol_table:` / `next(...)` block with `entry_point = EntryPoint.function(lambda ref: ref.label == linked.entry_func_label)`, keeping the explanatory comment above it in the squall helper.

- [ ] **Step 5: Confirm nothing spells the convention**

Run: `grep -rn "__call_arguments\|func_init_params_\|__init_params__\|__prog_\|\"ws_handle\"" cicada squall jackal red_dragon_forge tests | grep -v "pycache\|third-party"`
Expected: no output.

- [ ] **Step 6: Gate**

Run: `make fmt && uv run pyright && uv run lint-imports && pre-commit run python-fp-lint-check --hook-stage manual --all-files`, then `. ./bridge-env.sh && make test-all > /tmp/qhun-forge.log 2>&1; grep -E "^=+ .* in [0-9.]+s" /tmp/qhun-forge.log`
Expected: every check clean; cicada, squall, jackal, cobble and root suites all succeed (Db2 must be healthy: `docker inspect -f '{{.State.Health.Status}}' squall-db2`).

- [ ] **Step 7: c3270 CardDemo**

Copy `docs/presentation/capture/carddemo_3270_video.sh` to the scratchpad with `ROOT` set to the forge root and `OUT` set to a scratchpad directory, run it, then build a 12-frame sheet: `ffmpeg -loglevel error -y -i <out>/carddemo-3270.mp4 -vf "fps=12/<duration>,scale=640:-1,tile=3x4" -frames:v 1 <out>/sheet.png` and read it.
Expected: sign-on, main menu, account update reaching "Changes validated", account view, list users, user USER0006 added, updated to CAROLINE, deleted, and the final list without USER0006 — the same frames as the 2026-10-13 baseline.

- [ ] **Step 8: Commit and push**

```bash
git add vendor/red-dragon cicada/cics/vm_init.py cicada/cics/conversational.py jackal/jackal/cobol_step.py jackal/jackal/le_abend.py cicada/tests/integration/cics/test_ceedays_stub.py squall/tests/integration/squall_cobol_helpers.py tests/integration/test_sql_adapter.py
git commit -m "chore(vendor): bump red-dragon; forge uses the COBOL CALL convention by import

cicada and jackal inject arguments under ARGUMENTS_PARAM and enter programs at
the recorded entry_func_label; le_abend finds CEE3ABD through program_var. No
forge file spells the convention's names (red-dragon-qhun)."
git push origin main
bd -C ~/code/red-dragon close red-dragon-qhun --reason "ADR-182: CALL_WITH_MEMORY is location + memory; the COBOL lowering owns the convention; the forge imports it."
```

Then in `~/code/red-dragon`: `bd export -o issues/issues.jsonl && git add issues/issues.jsonl && git commit -m "chore(issues): close red-dragon-qhun" && git push origin main`.
