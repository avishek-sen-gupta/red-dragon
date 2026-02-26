# RedDragon VM Design Document

This document describes the design and internals of the RedDragon symbolic virtual machine (VM). It is intended for senior technical leads coming to the codebase from scratch. All file references are relative to the repository root.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Pipeline Architecture](#2-pipeline-architecture)
3. [Intermediate Representation (IR)](#3-intermediate-representation-ir)
4. [Control Flow Graph (CFG)](#4-control-flow-graph-cfg)
5. [VM State Model](#5-vm-state-model)
6. [Execution Engine](#6-execution-engine)
7. [Call Dispatch and Return](#7-call-dispatch-and-return)
8. [Symbolic Execution](#8-symbolic-execution)
9. [Closure Capture and Mutation](#9-closure-capture-and-mutation)
10. [Built-in Functions](#10-built-in-functions)
11. [LLM Backend (Oracle Fallback)](#11-llm-backend-oracle-fallback)
12. [Function and Class Registry](#12-function-and-class-registry)
13. [Dataflow Analysis](#13-dataflow-analysis)
14. [Module Map](#14-module-map)
15. [End-to-End Worked Example](#15-end-to-end-worked-example)

---

## 1. System Overview

RedDragon is a **multi-language symbolic code interpreter**. It parses source code in 15 languages (via tree-sitter) or any language (via LLM), lowers it to a universal intermediate representation, builds a control flow graph, and executes the program symbolically.

The core design principle: **execute as much as possible deterministically (0 LLM calls), and only fall back to an LLM oracle when the interpreter encounters truly unknown values**. For programs with concrete inputs and no missing dependencies, the entire execution is deterministic.

```
                         ┌──────────────────────────────────────────┐
                         │              Source Code                 │
                         │        (Python, JS, Java, ...)           │
                         └────────────────┬─────────────────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
           ┌────────────────┐   ┌────────────────┐   ┌─────────────────┐
           │  tree-sitter   │   │  LLM Frontend  │   │ Chunked LLM     │
           │  15 languages  │   │  any language   │   │ chunk→LLM×N     │
           └───────┬────────┘   └───────┬────────┘   └────────┬────────┘
                   │                    │                      │
                   └────────────────────┼──────────────────────┘
                                        ▼
                              ┌─────────────────┐
                              │  Flattened IR    │
                              │  (~20 opcodes)   │
                              └────────┬────────┘
                                       │
                          ┌────────────┼────────────┐
                          ▼            ▼            ▼
                   ┌────────────┐ ┌────────┐ ┌───────────────┐
                   │ Build CFG  │ │Registry│ │  Dataflow     │
                   │            │ │        │ │  Analysis     │
                   └─────┬──────┘ └───┬────┘ └───────────────┘
                         │            │
                         ▼            ▼
                    ┌──────────────────────┐
                    │   Symbolic VM        │
                    │ ┌──────────────────┐ │
                    │ │ Local Executor   │ │  ← handles all 19 opcodes
                    │ └───────┬──────────┘ │
                    │         │ not handled │
                    │         ▼            │
                    │ ┌──────────────────┐ │
                    │ │ LLM Oracle       │ │  ← fallback only
                    │ └──────────────────┘ │
                    └──────────────────────┘
```

---

## 2. Pipeline Architecture

The end-to-end pipeline is orchestrated by two functions in `interpreter/run.py`:

- **`run()`** (line 348): Full pipeline — parse, lower, build CFG, build registry, execute. Returns final `VMState`.
- **`execute_cfg()`** (line 234): Standalone VM execution on a pre-built CFG and registry.

### Pipeline stages and timing

Each stage is individually timed and reported via `PipelineStats` (defined in `interpreter/run_types.py:53`):

```python
@dataclass
class PipelineStats:
    source_bytes: int = 0
    source_lines: int = 0
    language: str = ""
    frontend_type: str = ""
    parse_time: float = 0.0        # tree-sitter parse
    lower_time: float = 0.0        # AST → IR lowering
    cfg_time: float = 0.0          # IR → CFG
    registry_time: float = 0.0     # function/class scan
    execution_time: float = 0.0    # VM step loop
    total_time: float = 0.0
    ...
```

### Execution configuration

All VM configuration is grouped in the frozen dataclass `VMConfig` (`interpreter/run_types.py:8`):

```python
@dataclass(frozen=True)
class VMConfig:
    backend: str = "claude"     # LLM provider for fallback
    max_steps: int = 100        # step budget
    verbose: bool = False       # print step-by-step trace
```

Being frozen prevents accidental mutation during execution.

---

## 3. Intermediate Representation (IR)

The IR is a **flattened high-level three-address code** defined in `interpreter/ir.py`. Every source language lowers to the same IR, which makes the VM language-agnostic.

### Opcodes

The `Opcode` enum (`interpreter/ir.py:11`) defines 20 opcodes in three categories:

| Category | Opcodes | Description |
|---|---|---|
| **Value producers** | `CONST`, `LOAD_VAR`, `LOAD_FIELD`, `LOAD_INDEX`, `NEW_OBJECT`, `NEW_ARRAY`, `BINOP`, `UNOP`, `CALL_FUNCTION`, `CALL_METHOD`, `CALL_UNKNOWN` | Write result to a register (`result_reg`) |
| **Consumers / Control** | `STORE_VAR`, `STORE_FIELD`, `STORE_INDEX`, `BRANCH_IF`, `BRANCH`, `RETURN`, `THROW` | Consume values, affect control flow |
| **Special** | `SYMBOLIC`, `LABEL` | Parameters, block boundaries |

### Instruction structure

Each instruction is a Pydantic model (`interpreter/ir.py:63`):

```python
class IRInstruction(BaseModel):
    opcode: Opcode
    result_reg: str | None = None          # e.g., "%0", "%1"
    operands: list[Any] = []               # resolved operands
    label: str | None = None               # for LABEL / branch targets
    source_location: SourceLocation = NO_SOURCE_LOCATION
```

**Key design choice**: registers use SSA-like naming (`%0`, `%1`, ...) for temporaries, while named variables use string names (`x`, `total`). The `STORE_VAR` / `LOAD_VAR` opcodes bridge between registers and variables.

### Source location traceability

Every IR instruction from deterministic (tree-sitter) frontends carries a `SourceLocation` (`interpreter/ir.py:38`) with the originating AST span:

```python
class SourceLocation(BaseModel):
    start_line: int
    start_col: int
    end_line: int
    end_col: int
```

LLM-generated instructions use `NO_SOURCE_LOCATION` (all zeros).

### Example IR

For `x = 2 + 3`:

```
%0 = const 2          # line 1:4-1:5
%1 = const 3          # line 1:8-1:9
%2 = binop + %0 %1    # line 1:4-1:9
store_var x %2         # line 1:0-1:9
```

---

## 4. Control Flow Graph (CFG)

### Data types

Defined in `interpreter/cfg_types.py`:

```python
@dataclass
class BasicBlock:
    label: str
    instructions: list[IRInstruction] = field(default_factory=list)
    successors: list[str] = field(default_factory=list)
    predecessors: list[str] = field(default_factory=list)

@dataclass
class CFG:
    blocks: dict[str, BasicBlock] = field(default_factory=dict)
    entry: str = constants.CFG_ENTRY_LABEL    # "entry"
```

### Build algorithm

`build_cfg()` in `interpreter/cfg.py:13` uses a classic three-phase algorithm:

**Phase 1 — Identify block boundaries** (lines 17-29):
Block starts occur at instruction 0, after every `LABEL` opcode, and after any terminator (`BRANCH`, `BRANCH_IF`, `RETURN`, `THROW`).

**Phase 2 — Create blocks** (lines 33-47):
Slice the instruction stream between consecutive starts. The leading `LABEL` pseudo-instruction is stripped from each block and used as the block's label. Blocks without a `LABEL` get a synthetic name (`__block_N`).

**Phase 3 — Wire edges** (lines 50-79):

```
BRANCH target       →  edge to target
BRANCH_IF t,f       →  edges to both t and f
RETURN / THROW      →  no successors (terminal)
(anything else)     →  fall through to next block
```

### CFG edge wiring

Edges are added via `_add_edge()` (`interpreter/cfg.py:280`), which maintains both `successors` and `predecessors` lists on each block:

```python
def _add_edge(cfg: CFG, src: str, dst: str):
    if dst not in cfg.blocks[src].successors:
        cfg.blocks[src].successors.append(dst)
    if src not in cfg.blocks[dst].predecessors:
        cfg.blocks[dst].predecessors.append(src)
```

### Label conventions

Functions and classes use structured labels defined in `interpreter/constants.py`:

| Pattern | Example | Meaning |
|---|---|---|
| `func_<name>_<N>` | `func_factorial_0` | Function entry |
| `end_<name>_<N>` | `end_factorial_1` | Function exit |
| `class_<name>_<N>` | `class_Point_0` | Class body entry |
| `end_class_<name>_<N>` | `end_class_Point_1` | Class body exit |

### Visual: CFG for an if/else

```
Source:                          CFG:
  if x > 0:                     ┌──────────────────────┐
      label = "pos"             │ entry                │
  else:                         │ LOAD x, CONST 0      │
      label = "neg"             │ BINOP >, BRANCH_IF   │
  return label                  └──────┬───────┬───────┘
                                   T   │       │ F
                                ┌──────▼──┐ ┌──▼──────┐
                                │if_true  │ │if_false │
                                │CONST pos│ │CONST neg│
                                │STORE    │ │STORE    │
                                └────┬────┘ └────┬────┘
                                     │           │
                                     ▼           ▼
                                ┌──────────────────────┐
                                │ merge                │
                                │ LOAD_VAR label       │
                                │ RETURN               │
                                └──────────────────────┘
```

---

## 5. VM State Model

All VM state types live in `interpreter/vm_types.py`. The state model is designed for serialisability (every type has a `to_dict()` method) so it can be sent to an LLM oracle.

### State hierarchy

```
VMState
├── heap: dict[str, HeapObject]
│   └── HeapObject
│       ├── type_hint: str         (e.g., "Point")
│       └── fields: dict[str, Any] (field name → value)
│
├── call_stack: list[StackFrame]
│   └── StackFrame
│       ├── function_name: str     (e.g., "factorial", "<main>")
│       ├── registers: dict        (%0 → value)
│       ├── local_vars: dict       (x → value)
│       ├── return_label: str      (caller's block to resume at)
│       ├── return_ip: int         (instruction index in caller's block)
│       ├── result_reg: str        (caller's register for return value)
│       ├── closure_env_id: str    (shared environment ID)
│       └── captured_var_names: frozenset[str]
│
├── path_conditions: list[str]     (assumptions from symbolic branches)
├── symbolic_counter: int          (gensym: sym_0, sym_1, ...)
│
└── closures: dict[str, ClosureEnvironment]
    └── ClosureEnvironment
        └── bindings: dict[str, Any]  (shared mutable captured vars)
```

### SymbolicValue

When the VM encounters an unknown (unresolvable variable, missing import, external call), it creates a `SymbolicValue` (`interpreter/vm_types.py:14`) rather than erroring:

```python
@dataclass
class SymbolicValue:
    name: str                                  # "sym_0", "sym_1", ...
    type_hint: str | None = None               # "int", "process(items)", ...
    constraints: list[str] = field(...)        # ["sym_0 + 1", "len(items)"]
```

Symbolic values propagate through arithmetic, comparisons, and function calls, accumulating constraints. This is the foundation of symbolic execution — the VM tracks *what the program would do* even when it doesn't know concrete values.

### Fresh symbolic generation

`VMState.fresh_symbolic()` (`interpreter/vm_types.py:92`) is a gensym — it monotonically increments `symbolic_counter` to produce unique names:

```python
def fresh_symbolic(self, hint: str = "") -> SymbolicValue:
    name = f"sym_{self.symbolic_counter}"
    self.symbolic_counter += 1
    return SymbolicValue(name=name, type_hint=hint or None)
```

The counter is also used to generate unique heap addresses (`obj_0`, `arr_1`, `env_2`), so it serves as a universal ID generator.

### StateUpdate — the instruction effect

Every instruction (whether locally executed or LLM-interpreted) produces a `StateUpdate` — a Pydantic model (`interpreter/vm_types.py:118`) describing the instruction's *effect* on the VM:

```python
class StateUpdate(BaseModel):
    register_writes: dict[str, Any] = {}     # {"%0": 42}
    var_writes: dict[str, Any] = {}          # {"x": 42}
    heap_writes: list[HeapWrite] = []        # [{obj_addr, field, value}]
    new_objects: list[NewObject] = []         # [{addr, type_hint}]
    next_label: str | None = None            # branch target
    call_push: StackFramePush | None = None  # push new call frame
    call_pop: bool = False                   # pop current frame
    return_value: Any | None = None          # value to return to caller
    path_condition: str | None = None        # assumption for symbolic branches
    reasoning: str = ""                      # human-readable explanation
```

This is the **central communication contract** between the executor and the VM. Both local execution and LLM fallback produce `StateUpdate`; the VM doesn't know or care which produced it.

### ExecutionResult — the handler outcome

Each opcode handler returns an `ExecutionResult` (`interpreter/vm_types.py:140`):

```python
@dataclass
class ExecutionResult:
    handled: bool
    update: StateUpdate = field(default_factory=...)

    @classmethod
    def not_handled(cls) -> ExecutionResult: ...
    @classmethod
    def success(cls, update: StateUpdate) -> ExecutionResult: ...
```

This is a **result type** that replaces the antipattern of returning `None` to mean "not handled". The `handled` flag tells the step loop whether to fall back to the LLM.

---

## 6. Execution Engine

### Step loop

The core execution loop lives in `execute_cfg()` (`interpreter/run.py:234`). Here is the simplified flow:

```
initialise VM with a single <main> StackFrame
set current_label = entry, ip = 0

for step in range(max_steps):
    block = cfg.blocks[current_label]

    if ip >= len(block.instructions):       ─── end of block
        if block has successors:
            current_label = first successor
            ip = 0; continue
        else:
            break                           ─── program terminates

    instruction = block.instructions[ip]
    if instruction is LABEL: ip++; continue ─── skip pseudo-instructions

    ┌─────────────────────────────────────┐
    │ result = _try_execute_locally(...)   │ ← try deterministic execution
    │ if result.handled:                   │
    │     update = result.update           │
    │ else:                                │
    │     update = llm.interpret(inst, vm) │ ← LLM fallback
    └─────────────────────────────────────┘

    apply_update(vm, update)                ─── mutate VM state

    handle control flow:
        RETURN/THROW → _handle_return_flow()
        next_label set → jump to target block
        default → ip++
```

### apply_update — the state mutator

`apply_update()` (`interpreter/vm.py:21`) is the **only function that mutates the VM**. The order of operations is critical and carefully designed:

```python
def apply_update(vm: VMState, update: StateUpdate):
    # 1. Create new heap objects
    for obj in update.new_objects:
        vm.heap[obj.addr] = HeapObject(type_hint=obj.type_hint)

    # 2. Register writes → CURRENT (caller's) frame
    for reg, val in update.register_writes.items():
        frame.registers[reg] = _deserialize_value(val, vm)

    # 3. Heap writes
    for hw in update.heap_writes:
        vm.heap[hw.obj_addr].fields[hw.field] = _deserialize_value(hw.value, vm)

    # 4. Path conditions
    if update.path_condition:
        vm.path_conditions.append(update.path_condition)

    # 5. Call push ← BEFORE var_writes!
    if update.call_push:
        vm.call_stack.append(StackFrame(...))

    # 6. Variable writes → CURRENT frame (new frame if call_push fired)
    target_frame = vm.current_frame
    for var, val in update.var_writes.items():
        target_frame.local_vars[var] = deserialized
        # Also sync to closure environment if captured
        if target_frame.closure_env_id and var in target_frame.captured_var_names:
            env.bindings[var] = deserialized

    # 7. Call pop
    if update.call_pop and len(vm.call_stack) > 1:
        vm.call_stack.pop()
```

**Why this order matters**: When dispatching a function call, the `StateUpdate` contains both `call_push` (new frame) *and* `var_writes` (parameter bindings). By pushing the frame (step 5) *before* writing variables (step 6), parameter bindings land in the *callee's* frame, not the caller's. This is the mechanism for passing arguments.

### Dispatch table

The local executor (`interpreter/executor.py:782`) uses a static dispatch table mapping opcodes to handler functions:

```python
class LocalExecutor:
    DISPATCH: dict[Opcode, Any] = {
        Opcode.CONST: _handle_const,
        Opcode.LOAD_VAR: _handle_load_var,
        Opcode.STORE_VAR: _handle_store_var,
        Opcode.BRANCH: _handle_branch,
        Opcode.BRANCH_IF: _handle_branch_if,
        Opcode.BINOP: _handle_binop,
        Opcode.UNOP: _handle_unop,
        Opcode.CALL_FUNCTION: _handle_call_function,
        Opcode.CALL_METHOD: _handle_call_method,
        ... # all 19 opcodes covered
    }
```

The entry point `_try_execute_locally()` (`interpreter/executor.py:830`) looks up the handler and calls it. If the opcode isn't in the table, it returns `ExecutionResult.not_handled()`, triggering LLM fallback.

---

## 7. Call Dispatch and Return

Function calls are the most complex part of the VM. The design supports user-defined functions, class constructors, built-in functions, methods, and closures — all through the same `StateUpdate` mechanism.

### CALL_FUNCTION dispatch chain

`_handle_call_function()` (`interpreter/executor.py:659`) tries four strategies in order:

```
1. BUILTIN?     → _try_builtin_call()           (len, range, print, ...)
   └─ if handled: return computed result

2. SCOPE LOOKUP → walk call_stack backwards for function variable
   └─ if not found: return symbolic result

3. CLASS CTOR?  → _try_class_constructor_call()  (parse <class:Name@label>)
   └─ if matched: allocate heap object, dispatch __init__

4. USER FUNC?   → _try_user_function_call()      (parse <function:Name@label>)
   └─ if matched: push frame, jump to function entry

5. UNKNOWN      → _symbolic_call_result()         (create symbolic value)
```

### How function references work

When the frontend lowers a function definition, it emits a `CONST` instruction with a **function reference string**:

```
%2 = const <function:factorial@func_factorial_0>
store_var factorial %2
```

This string encodes the function name and its CFG entry label. It is parsed by `_parse_func_ref()` (`interpreter/registry.py:33`) using the regex pattern `<function:(\w+)@(\w+)(?:#(\w+))?>`.

Class references follow a similar pattern: `<class:Point@class_Point_0>`.

### Call dispatch (user function)

When `_try_user_function_call()` (`interpreter/executor.py:596`) matches a function reference, it produces a `StateUpdate` with:

```python
StateUpdate(
    call_push=StackFramePush(
        function_name=fname,
        return_label=current_label,      # caller's block
    ),
    next_label=flabel,                    # callee's entry block
    var_writes=param_vars,                # parameter bindings
)
```

Remember `apply_update`'s ordering: the frame is pushed *before* `var_writes`, so parameters land in the new frame.

### Call dispatch setup

After `apply_update`, the step loop calls `_handle_call_dispatch_setup()` (`interpreter/run.py:172`) to write return info into the new frame:

```python
def _handle_call_dispatch_setup(vm, instruction, update, current_label, ip):
    apply_update(vm, update)
    new_frame = vm.current_frame
    new_frame.return_label = call_return_label    # where to resume
    new_frame.return_ip = ip + 1                  # next instruction in caller
    new_frame.result_reg = call_result_reg        # where to write return value
```

### Return flow

On `RETURN`, `_handle_return_flow()` (`interpreter/run.py:199`) pops the callee frame and resumes the caller:

```
caller frame:                   callee frame:
  return_label = "entry"          function_name = "factorial"
  return_ip = 4                   result_reg = "%4"  (caller's register)
  ...                             return_value = 120

After RETURN:
  1. Pop callee frame
  2. Write return_value (120) to caller's result_reg (%4)
  3. Jump to return_label:return_ip (entry:4)
```

### Parameter binding via SYMBOLIC

Parameters in function bodies are represented as `SYMBOLIC` instructions with `param:` hints:

```
LABEL func_factorial_0
%0 = SYMBOLIC param:n        ← parameter declaration
```

When the executor handles `SYMBOLIC` (`interpreter/executor.py:191`), it checks whether the parameter was pre-bound by the caller:

```python
def _handle_symbolic(inst, vm, **kwargs):
    hint = inst.operands[0]
    if hint.startswith(constants.PARAM_PREFIX):
        param_name = hint[len(constants.PARAM_PREFIX):]
        if param_name in frame.local_vars:
            val = frame.local_vars[param_name]
            return ExecutionResult.success(
                StateUpdate(register_writes={inst.result_reg: val}, ...)
            )
    # Not pre-bound → create fresh symbolic
    sym = vm.fresh_symbolic(hint=hint)
    return ExecutionResult.success(...)
```

This is how the VM handles both concrete calls (where the caller pre-binds `n=5`) and top-level function analysis (where `n` becomes `sym_0`).

### Class constructor flow

`_try_class_constructor_call()` (`interpreter/executor.py:538`) handles `<class:Point@class_Point_0>`:

```
1. Allocate heap object: vm.heap["obj_0"] = HeapObject(type_hint="Point")
2. Write object address to result_reg: %4 = "obj_0"
3. If __init__ exists in registry:
   a. Push frame with function_name="Point.__init__"
   b. Bind self=obj_0, other params from args
   c. Dispatch to __init__ label
4. If no __init__: just return the allocated address
```

### Method dispatch

`_handle_call_method()` (`interpreter/executor.py:704`) resolves the object's type from the heap, looks up the method in the registry, and dispatches:

```python
addr = _heap_addr(obj_val)
type_hint = vm.heap[addr].type_hint         # e.g., "Point"
methods = registry.class_methods[type_hint]  # {"__init__": "func___init___4", "move": "func_move_6"}
func_label = methods[method_name]
# Push frame with self bound to object address
```

---

## 8. Symbolic Execution

The VM's symbolic execution is the mechanism that enables analysis of programs with incomplete information.

### When symbolic values arise

| Situation | Example | What happens |
|---|---|---|
| Unresolved variable | `process(items)` where `process` not in scope | `LOAD_VAR` creates `sym_N` with hint `"process"` |
| Missing function | calling unknown function | `_symbolic_call_result` creates `sym_N` with constraint `"process(sym_M)"` |
| Symbolic arithmetic | `sym_0 + 1` | `_handle_binop` creates `sym_N` with constraint `"sym_0 + 1"` |
| Symbolic field access | `sym_0.field` | `_handle_load_field` creates `sym_N` with hint `"sym_0.field"` |
| Symbolic branch | `if sym_0:` | Takes true branch, records path condition |

### Symbolic propagation through BINOP

`_handle_binop()` (`interpreter/executor.py:437`):

```python
def _handle_binop(inst, vm, **kwargs):
    oper = inst.operands[0]
    lhs = _resolve_reg(vm, inst.operands[1])
    rhs = _resolve_reg(vm, inst.operands[2])

    if _is_symbolic(lhs) or _is_symbolic(rhs):
        # Either operand is symbolic → result must be symbolic
        sym = vm.fresh_symbolic(hint=f"{lhs_desc} {oper} {rhs_desc}")
        sym.constraints = [f"{lhs_desc} {oper} {rhs_desc}"]
        return ExecutionResult.success(
            StateUpdate(register_writes={inst.result_reg: sym.to_dict()}, ...)
        )

    # Both concrete → compute
    result = Operators.eval_binop(oper, lhs, rhs)
    if result is Operators.UNCOMPUTABLE:
        # Edge case: concrete but uncomputable (e.g., division by zero)
        sym = vm.fresh_symbolic(...)
        ...
    return ExecutionResult.success(
        StateUpdate(register_writes={inst.result_reg: result}, ...)
    )
```

### UNCOMPUTABLE sentinel

`Operators.UNCOMPUTABLE` (`interpreter/vm.py:133`) is a sentinel that replaces exceptions for operations that fail at the value level (not at the system level). This avoids exception-heavy control flow:

```python
class Operators:
    class _Uncomputable:
        def __repr__(self) -> str:
            return "UNCOMPUTABLE"

    UNCOMPUTABLE = _Uncomputable()

    BINOP_TABLE: dict[str, Any] = {
        "+": lambda a, b: a + b,
        "/": lambda a, b: a / b if b != 0 else Operators.UNCOMPUTABLE,
        ...
    }
```

### Symbolic branching

`_handle_branch_if()` (`interpreter/executor.py:406`):

When the branch condition is symbolic, the VM **deterministically takes the true branch** and records the assumption:

```python
if _is_symbolic(cond_val):
    return ExecutionResult.success(
        StateUpdate(
            next_label=true_label,
            path_condition=f"assuming {sym_desc} is True",
            reasoning=f"branch_if {sym_desc} (symbolic) → {true_label} (assumed true)",
        )
    )
```

Path conditions accumulate in `vm.path_conditions` and are included in LLM prompts, giving the oracle context about what assumptions the VM has made.

### Lazy heap materialisation

When the VM accesses a field on a symbolic object (not yet on the heap), it **materialises** a synthetic heap entry on the fly (`interpreter/executor.py:286`):

```python
def _handle_load_field(inst, vm, **kwargs):
    addr = _heap_addr(obj_val)
    if addr and addr not in vm.heap:
        # Materialise a synthetic heap entry for symbolic objects
        # so repeated field accesses return the same symbolic value
        vm.heap[addr] = HeapObject(type_hint=_symbolic_type_hint(obj_val))
    ...
    # If field not found, create symbolic and cache it
    sym = vm.fresh_symbolic(hint=f"{addr}.{field_name}")
    heap_obj.fields[field_name] = sym   # ← cache for deduplication
```

This ensures that `obj.x` and `obj.x` on the same symbolic object return the *same* symbolic value, which is important for constraint consistency.

### Variable resolution via scope chain

`_handle_load_var()` (`interpreter/executor.py:146`) walks the call stack backwards (innermost to outermost frame), implementing proper lexical scoping:

```python
def _handle_load_var(inst, vm, **kwargs):
    name = inst.operands[0]
    for f in reversed(vm.call_stack):
        if name in f.local_vars:
            return ExecutionResult.success(
                StateUpdate(register_writes={inst.result_reg: val}, ...)
            )
    # Not found anywhere → create symbolic
    sym = vm.fresh_symbolic(hint=name)
    return ExecutionResult.success(...)
```

---

## 9. Closure Capture and Mutation

The VM supports **capture-by-reference** closures with shared mutable environments. This means:

1. Multiple closures from the same scope share the same environment
2. Mutations inside one closure are visible to sibling closures
3. Mutations persist across calls

### ClosureEnvironment

Defined in `interpreter/vm_types.py:43`:

```python
@dataclass
class ClosureEnvironment:
    """Shared mutable environment for closure capture-by-reference."""
    bindings: dict[str, Any] = field(default_factory=dict)
```

### Capture mechanism

When `_handle_const()` (`interpreter/executor.py:100`) encounters a function reference being created inside another function (i.e., `len(vm.call_stack) > 1`), it creates or reuses a `ClosureEnvironment`:

```python
if len(vm.call_stack) > 1 and isinstance(val, str):
    fr = _parse_func_ref(val)
    if fr.matched:
        enclosing = vm.current_frame
        env_id = enclosing.closure_env_id
        if env_id:
            # REUSE existing environment (second closure from same factory)
            env = vm.closures[env_id]
            for k, v in enclosing.local_vars.items():
                if k not in env.bindings:
                    env.bindings[k] = v
        else:
            # CREATE new environment from enclosing frame's local vars
            env_id = f"env_{vm.symbolic_counter}"
            env = ClosureEnvironment(bindings=dict(enclosing.local_vars))
            vm.closures[env_id] = env
            enclosing.closure_env_id = env_id
        # Annotate function reference with closure ID
        val = f"<function:{fr.name}@{fr.label}#{closure_id}>"
```

The `#closure_id` suffix on the function reference string links the closure to its shared environment at call time.

### Mutation persistence

In `apply_update()` (`interpreter/vm.py:59`), variable writes to captured names are synced back to the shared environment:

```python
target_frame = vm.current_frame
for var, val in update.var_writes.items():
    target_frame.local_vars[var] = deserialized
    # Sync to closure environment
    if target_frame.closure_env_id and var in target_frame.captured_var_names:
        env = vm.closures.get(target_frame.closure_env_id)
        if env:
            env.bindings[var] = deserialized
```

### Visual: shared closure environments

```
def make_counter():
    count = 0
    def increment():
        count = count + 1       ← mutates shared env
        return count
    def get():
        return count            ← reads shared env
    return (increment, get)

                     ┌───────────────────┐
                     │ ClosureEnvironment │
                     │ env_0             │
                     │ bindings:         │
                     │   count = 0       │ ← shared mutable state
                     └────────┬──────────┘
                         ┌────┴────┐
                         │         │
                  ┌──────▼─────┐  ┌▼──────────┐
                  │ increment  │  │ get        │
                  │ #closure_1 │  │ #closure_2 │
                  │ env → env_0│  │ env → env_0│
                  └────────────┘  └────────────┘

After increment():  env_0.bindings["count"] = 1
After get():        reads env_0.bindings["count"] → 1
```

---

## 10. Built-in Functions

Built-in functions are defined in `interpreter/builtins.py`. They are dispatched before user functions in the call chain.

### Built-in table

```python
class Builtins:
    TABLE: dict[str, Any] = {
        "len": _builtin_len,
        "range": _builtin_range,
        "print": _builtin_print,
        "int": _builtin_int,
        "float": _builtin_float,
        "str": _builtin_str,
        "bool": _builtin_bool,
        "abs": _builtin_abs,
        "max": _builtin_max,
        "min": _builtin_min,
    }
```

### Handling symbolic arguments

Built-ins gracefully degrade when given symbolic arguments. For example, `_builtin_len()` (`interpreter/builtins.py:12`):

```python
def _builtin_len(args, vm):
    val = args[0]
    addr = _heap_addr(val)
    if addr and addr in vm.heap:
        return len(vm.heap[addr].fields)     # heap object: count fields
    if isinstance(val, (list, tuple, str)):
        return len(val)                       # concrete collection
    return _UNCOMPUTABLE                      # symbolic → can't compute
```

When a builtin returns `UNCOMPUTABLE`, the call handler in `_try_builtin_call()` (`interpreter/executor.py:506`) wraps it in a symbolic value:

```python
result = Builtins.TABLE[func_name](args, vm)
if result is Operators.UNCOMPUTABLE:
    sym = vm.fresh_symbolic(hint=f"{func_name}({args_desc})")
    sym.constraints = [f"{func_name}({args_desc})"]
    return ExecutionResult.success(
        StateUpdate(register_writes={inst.result_reg: sym.to_dict()}, ...)
    )
```

---

## 11. LLM Backend (Oracle Fallback)

The LLM backend (`interpreter/backend.py`) is the fallback for instructions the local executor can't handle. In practice, the local executor handles all 19 opcodes, so the LLM is only called when the local executor explicitly delegates (which currently doesn't happen — all opcodes have handlers).

### Architecture

```python
class LLMBackend(ABC):
    SYSTEM_PROMPT = "..."   # detailed instruction for the LLM

    @abstractmethod
    def interpret_instruction(self, instruction, state) -> StateUpdate: ...

    def _build_prompt(self, instruction, state) -> str: ...
    def _parse_response(self, text) -> StateUpdate: ...
```

Four concrete backends: `ClaudeBackend`, `OpenAIBackend`, `OllamaBackend`, `HuggingFaceBackend`. All delegate to an `LLMClient` abstraction via `get_llm_client()`.

### Prompt construction

`_build_prompt()` (`interpreter/backend.py:87`) builds a compact JSON payload:

```json
{
    "instruction": "%5 = binop * sym_0 4",
    "result_reg": "%5",
    "opcode": "BINOP",
    "operands": ["*", "%3", "%4"],
    "resolved_operand_values": {"%3": {"__symbolic__": true, "name": "sym_0"}, "%4": 4},
    "state": {
        "local_vars": {"x": {"__symbolic__": true, "name": "sym_0"}},
        "heap": {},
        "path_conditions": ["assuming sym_0 > 0 is True"]
    }
}
```

Only relevant state is included (no empty heap, no empty path conditions) to minimize token usage.

### System prompt contract

The system prompt (`interpreter/backend.py:16`) defines the `StateUpdate` JSON schema and gives concrete examples for each opcode category. The LLM must respond with valid JSON matching the schema.

---

## 12. Function and Class Registry

The `FunctionRegistry` (`interpreter/registry.py:62`) is built by scanning IR instructions and the CFG:

```python
@dataclass
class FunctionRegistry:
    func_params: dict[str, list[str]] = ...   # func_label → ["x", "y"]
    class_methods: dict[str, dict[str, str]] = ...  # "Point" → {"__init__": "func___init___4"}
    classes: dict[str, str] = ...             # "Point" → "class_Point_0"
```

### Building the registry

`build_registry()` (`interpreter/registry.py:132`) runs two scans:

**1. Function parameters** — `_scan_func_params()` (line 71):
Walks CFG blocks starting with `func_`. Extracts `SYMBOLIC param:x` instructions to discover parameter names and their order.

```
LABEL func_factorial_0
%0 = SYMBOLIC param:n      ← discovered: func_factorial_0 → ["n"]
```

**2. Classes and methods** — `_scan_classes()` (line 88):
- First pass: find `CONST <class:Point@class_Point_0>` instructions
- Second pass: walk IR linearly, tracking class scope between `class_*` and `end_class_*` labels; collect function references inside class scopes as methods

---

## 13. Dataflow Analysis

`interpreter/dataflow.py` implements classic intraprocedural dataflow analysis on the CFG.

### Analysis pipeline

`analyze()` (`interpreter/dataflow.py:405`) runs four phases:

```
1. Collect all definitions
2. Solve reaching definitions (worklist fixpoint)
3. Extract def-use chains
4. Build dependency graph (with transitive closure)
```

### Core data types

```python
@dataclass(frozen=True)
class Definition:
    variable: str               # "x", "%0"
    block_label: str
    instruction_index: int
    instruction: IRInstruction

@dataclass(frozen=True)
class Use:
    variable: str
    block_label: str
    instruction_index: int
    instruction: IRInstruction

@dataclass(frozen=True)
class DefUseLink:
    definition: Definition
    use: Use
```

### Reaching definitions

`solve_reaching_definitions()` (`interpreter/dataflow.py:219`) uses the standard worklist algorithm:

```
for each block B:
    compute GEN(B) = last definition of each variable in B
    compute KILL(B) = all defs of variables redefined in B (from other blocks)

worklist = all blocks
while worklist not empty:
    B = worklist.pop()
    reach_in(B) = ∪ reach_out(P) for P in predecessors(B)
    reach_out(B) = GEN(B) ∪ (reach_in(B) - KILL(B))
    if reach_out changed:
        add successors to worklist
```

Convergence is capped at `DATAFLOW_MAX_ITERATIONS` (1000) to prevent non-termination on pathological CFGs.

### Def-use chains

`extract_def_use_chains()` (`interpreter/dataflow.py:265`) walks each block forward, tracking local definitions. For each use:
- If a local definition shadows incoming defs, link to the local def
- Otherwise, link to all matching definitions in `reach_in`

### Dependency graph

`build_dependency_graph()` (`interpreter/dataflow.py:313`) traces register chains backward from `STORE_VAR` instructions to find named variable dependencies, then computes the transitive closure:

```
subtotal = price * quantity

Traces: subtotal ← %2 (BINOP) ← %0 (LOAD_VAR price), %1 (LOAD_VAR quantity)
Result: subtotal depends on {price, quantity}

total = subtotal + tax
Result: total depends on {subtotal, tax, price, quantity}  (transitive)
```

---

## 14. Module Map

```
interpreter/
├── ir.py                    IR instruction format, Opcode enum, SourceLocation
├── vm_types.py              VM data types (SymbolicValue, HeapObject, VMState, StateUpdate, ...)
├── vm.py                    apply_update(), helpers (Operators, _parse_const, _resolve_reg, ...)
├── cfg_types.py             BasicBlock, CFG
├── cfg.py                   build_cfg(), cfg_to_mermaid(), extract_function_instructions()
├── run_types.py             VMConfig, ExecutionStats, PipelineStats
├── run.py                   execute_cfg(), run() — orchestration and step loop
├── executor.py              LocalExecutor dispatch table, all 19 opcode handlers
├── builtins.py              Built-in function table (len, range, print, ...)
├── registry.py              FunctionRegistry, function/class scanning
├── backend.py               LLMBackend ABC + 4 concrete backends
├── llm_client.py            LLMClient abstraction for API calls
├── parser.py                tree-sitter parser wrapper
├── frontend.py              Frontend ABC + factory, language routing
├── frontends/               15 language-specific tree-sitter frontends
├── dataflow.py              Reaching definitions, def-use chains, dependency graphs
├── constants.py             All magic strings/numbers as named constants
├── api.py                   Composable public API (lower_source, dump_ir, ...)
└── __init__.py              Package exports
```

### Dependency flow

```
ir.py ← constants.py
  ↑
cfg_types.py ← ir.py, constants.py
  ↑
cfg.py ← cfg_types.py, ir.py, constants.py
  ↑
vm_types.py ← (standalone, pydantic only)
  ↑
vm.py ← vm_types.py
  ↑
registry.py ← ir.py, cfg.py, constants.py
  ↑
builtins.py ← vm.py
  ↑
executor.py ← ir.py, cfg.py, vm.py, registry.py, builtins.py, constants.py
  ↑
backend.py ← ir.py, vm.py, llm_client.py
  ↑
run.py ← (everything above)
```

The new `*_types.py` files are **pure data** with no business-logic imports, ensuring they sit at the bottom of the dependency graph with zero risk of circular imports.

---

## 15. End-to-End Worked Example

### Source

```python
def double(x):
    return x * 2

result = double(5)
```

### Step 1: Lower to IR

```
LABEL func_double_0
  %0 = SYMBOLIC param:x
  %1 = CONST 2
  %2 = BINOP * %0 %1
  RETURN %2
LABEL end_double_1
  %3 = CONST <function:double@func_double_0>
  STORE_VAR double %3
  %4 = CONST 5
  %5 = CALL_FUNCTION double %4
  STORE_VAR result %5
  RETURN %5
```

### Step 2: Build CFG

```
┌─────────────────────────────────┐
│ func_double_0                   │
│ %0=SYMBOLIC param:x             │
│ %1=CONST 2                     │
│ %2=BINOP * %0 %1               │
│ RETURN %2                       │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ end_double_1                    │
│ %3=CONST <function:double@...>  │
│ STORE_VAR double %3             │
│ %4=CONST 5                     │
│ %5=CALL_FUNCTION double %4      │
│ STORE_VAR result %5             │
│ RETURN %5                       │
└─────────────────────────────────┘

Entry = end_double_1 (first block after function skip)
```

### Step 3: Build registry

```
func_params: {"func_double_0": ["x"]}
classes: {}
class_methods: {}
```

### Step 4: Execute

```
VM initialised: call_stack = [StackFrame("<main>")]

Step 0: end_double_1:0  %3 = CONST <function:double@func_double_0>
  → _handle_const: registers[%3] = "<function:double@func_double_0>"

Step 1: end_double_1:1  STORE_VAR double %3
  → _handle_store_var: local_vars["double"] = "<function:double@func_double_0>"

Step 2: end_double_1:2  %4 = CONST 5
  → _handle_const: registers[%4] = 5

Step 3: end_double_1:3  %5 = CALL_FUNCTION double %4
  → _handle_call_function:
    1. "double" not in builtins
    2. Scope lookup: local_vars["double"] = "<function:double@func_double_0>"
    3. Not a class reference
    4. _try_user_function_call matches!
       → call_push: StackFrame("double"), var_writes: {"x": 5}
       → next_label: "func_double_0"
  → _handle_call_dispatch_setup:
       new_frame.return_label = "end_double_1"
       new_frame.return_ip = 4
       new_frame.result_reg = "%5"

Step 4: func_double_0:0  %0 = SYMBOLIC param:x
  → _handle_symbolic: param "x" found in frame.local_vars (pre-bound to 5)
  → registers[%0] = 5

Step 5: func_double_0:1  %1 = CONST 2
  → _handle_const: registers[%1] = 2

Step 6: func_double_0:2  %2 = BINOP * %0 %1
  → _handle_binop: both concrete → 5 * 2 = 10
  → registers[%2] = 10

Step 7: func_double_0:3  RETURN %2
  → _handle_return: return_value = 10, call_pop = True
  → _handle_return_flow:
       Pop "double" frame
       Write 10 to caller's %5
       Resume at end_double_1:4

Step 8: end_double_1:4  STORE_VAR result %5
  → _handle_store_var: local_vars["result"] = 10

Step 9: end_double_1:5  RETURN %5
  → _handle_return: return from <main> → stop

Final state:
  local_vars = {"double": "<function:double@func_double_0>", "result": 10}
  heap = {}
  9 steps, 0 LLM calls
```

---

## Design Principles Summary

| Principle | Manifestation |
|---|---|
| **Deterministic first** | Local executor handles all 19 opcodes; LLM is pure fallback |
| **Functional core, imperative shell** | Pure data types in `*_types.py`, mutation only in `apply_update()` |
| **Result types over exceptions** | `ExecutionResult.not_handled()` instead of raising or returning `None` |
| **Sentinel over exception** | `Operators.UNCOMPUTABLE` instead of try/catch for arithmetic failures |
| **Single mutator** | Only `apply_update()` writes to VMState; everything else produces `StateUpdate` |
| **Serialisable state** | Every type has `to_dict()`; state can be sent to LLM or serialised |
| **Scope chain resolution** | Variables resolved by walking call stack backwards |
| **Lazy materialisation** | Symbolic heap entries created on first access, then cached |
| **Shared environments** | Closures from same scope share one `ClosureEnvironment` |
| **Convention over configuration** | Structured label names (`func_`, `class_`, `end_`) encode semantics |
