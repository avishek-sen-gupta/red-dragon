# IR Reference

RedDragon uses a flattened high-level three-address code IR. Every frontend lowers its program to a linear sequence of typed instruction dataclasses drawn from 37 opcodes (the `Opcode` enum in `interpreter/ir.py`).

## Instruction format

Each opcode has a frozen dataclass in `interpreter/instructions.py` (37 classes). All inherit from `InstructionBase`, which carries:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `source_location` | `SourceLocation` | `NO_SOURCE_LOCATION` | source span |
| `result_reg` | `Register` | `NO_REGISTER` | target register |
| `label` | `CodeLabel` | `NO_LABEL` | label (`LABEL`, `BRANCH`) |
| `branch_targets` | `tuple[CodeLabel, ...]` | `()` | targets (`BRANCH_IF`) |
| `id` | `InstructionId` | `NO_INSTRUCTION_ID` | stable sidecar coordinate |

`InstructionId` is a `NewType` over `int`; `NO_INSTRUCTION_ID` is `-1`. The field is `compare=False`, so two instructions differing only in `id` are equal. Ids key data kept beside the IR rather than in it. The COBOL frontend mints them from one `InstructionIdSource` shared across every program it lowers, and keys its `MemoryEffect` records by them.

Fields use domain types:

- **Registers**: `Register` (e.g. `result_reg`, `left`, `right`)
- **Labels**: `CodeLabel` (e.g. `label`, `target_label`, `catch_labels`)
- **Variable names**: `VarName` (`name` on `LoadVar`/`StoreVar`/`DeclVar`, `var_name` on `AddressOf`)
- **Field names**: `FieldName` (`field_name` on `LoadField`/`StoreField`)
- **Function/method names**: `FuncName` (`func_name` on `CallFunction`/`CallCtorFunction`/`CallWithMemory`, `method_name` on `CallMethod`)
- **Operators**: `BinopKind`/`UnopKind` enums (`operator` on `Binop`/`Unop`)

Each instruction implements `reads() -> list[StorageIdentifier]` and `writes() -> StorageIdentifier | None` for dataflow analysis. `StorageIdentifier` is a protocol that `Register` and `VarName` satisfy. The base `writes()` returns `result_reg` when present, else `None`; `DeclVar` and `StoreVar` return `name`.

```python
@dataclass(frozen=True)
class Binop(InstructionBase):
    result_reg: Register = NO_REGISTER
    operator: BinopKind = BinopKind.ADD
    left: Register = NO_REGISTER
    right: Register = NO_REGISTER

    def reads(self) -> list[StorageIdentifier]:
        return [r for r in (self.left, self.right) if isinstance(r, Register) and r.is_present()]

    # writes() is inherited: result_reg, or None when absent
```

`IRInstruction(opcode, result_reg, operands, label, branch_targets, source_location, literal_type)` in `ir.py` is a factory that builds the typed instruction from flat operands. It is kept for older call sites and test helpers.

Text representation: `%0 = const 42`, `store_var x %0`, `entry:` (labels). A known source location is appended as `  # line:col-line:col`.

Registers are named `%0`, `%1`, ... (the COBOL frontend uses `%r0`, `%r1`, ...). Each is assigned once by convention; this is not enforced. Labels are `CodeLabel` values such as `entry`, `func_fib_0`, `if_true_3`.

---

## Value producers

These opcodes write `result_reg`, except `STORE_INDIRECT`.

### CONST

Load a constant value.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register |
| `value` | Python value | typed payload (`int`, `float`, `CobolNumber`, `str`, `bool`, `None`, or a label string) |
| `has_value` | `bool` | `False` renders no operand; default `True` |
| `type_expr` | `TypeExpr` | keyword-only, required; the constant's type |

Build constants with the typed factories, not the constructor:

| Factory | `value` | `type_expr` |
|---------|---------|-------------|
| `Const.int_(reg, v)` | `int` | `scalar(INT)` |
| `Const.float_(reg, v)` | `float` | `scalar(FLOAT)` |
| `Const.decimal_(reg, v)` | `CobolNumber` | `scalar(DECIMAL)` (COBOL only) |
| `Const.string(reg, v)` | `str`, no quotes | `scalar(STRING)` |
| `Const.bool_(reg, v)` | `bool` | `scalar(BOOL)` |
| `Const.null_(reg)` | `None` | `NULL` |
| `Const.func_ref(reg, label, params, return_type)` | function label | `fn_type(params, return_type)` |
| `Const.class_ref(reg, label, class_type)` | class label | `metatype(class_type)` |

The handler writes `value` with `type_expr` as its type. A function-typed label found in the function symbol table becomes a `BoundFuncRef`, capturing a closure when not at top level. A metatype label found in the class symbol table becomes a `ClassRef`.

The flat `IRInstruction` path takes a `literal_type` (`"Int"`, `"Float"`, `"Decimal"`, `"String"`, `"Bool"`, `"Null"`, `"FuncRef"`, `"ClassRef"`). Without one, it infers the type from the operand text: `None`, `True`/`False`, `func_`/`<function:` and `class_`/`<class:` prefixes, integer, float, quoted string, else bare string. Only legacy IR and hand-written fixtures reach that path.

```
%0 = const 42
%1 = const hello
%2 = const True
%3 = const None
%4 = const func_fib_0
```

### LOAD_VAR

Read a named variable.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register |
| `name` | `VarName` | variable name |

Searches the call stack from the current frame backwards. If no frame binds it, tries the field fallback (implicit `this.name`), then returns a fresh symbolic value.

**Alias-aware**: a variable promoted to the heap by `ADDRESS_OF` (an entry in `var_heap_aliases`) is read from the heap object, so writes through pointers are visible.

For block-scoped languages, `name` may be a mangled name (e.g. `x$1`) produced by the frontend's scope tracker. See [Block-Scope Tracking](type-system.md#block-scope-tracking-llvm-style).

```
%4 = load_var x
```

### LOAD_FIELD

Read a field from a heap object.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register |
| `obj_reg` | `Register` | object pointer |
| `field_name` | `FieldName` | field to read |

Resolves `obj_reg` to a `Pointer`, extracts the base heap address via `_heap_addr()`, then looks up `field_name` in the object's fields. Returns a fresh symbolic value if the field does not exist.

```
%5 = load_field %obj name
```

### LOAD_INDEX

Read an element by index or key.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register |
| `arr_reg` | `Register` | array/map pointer |
| `index_reg` | `Register` | index or key |

Resolves both registers. For native Python lists/strings, performs direct indexing. For heap arrays, looks up `str(index)` in the object's fields. Returns a fresh symbolic value if the key does not exist.

```
%6 = load_index %arr %i
```

### NEW_OBJECT

Allocate a new heap object.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register (receives `Pointer(base=heap_addr, offset=0)` typed e.g. `pointer(scalar("Point"))`) |
| `type_hint` | `TypeExpr` | type of the new object |

Creates a new entry in the heap with the given type hint. Fields are initially empty. The result is a `Pointer` dataclass, not a bare string address.

```
%7 = new_object Point
```

### NEW_ARRAY

Allocate a new heap array.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register (receives `Pointer(base=heap_addr, offset=0)` typed e.g. `pointer(scalar("int[]"))`) |
| `type_hint` | `TypeExpr` | element type hint |
| `size_reg` | `Register` | optional initial size (may be `NO_REGISTER`) |

Like `NEW_OBJECT` but semantically represents an array/list. Elements are stored as fields keyed by stringified indices (`"0"`, `"1"`, ...). The result is a `Pointer` dataclass, not a bare string address.

```
%8 = new_array int[]
```

### BINOP

Binary operation.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register |
| `operator` | `BinopKind` | operator enum |
| `left` | `Register` | left operand |
| `right` | `Register` | right operand |

Resolves both operand registers. If either is symbolic, produces a symbolic result with a constraint. Otherwise evaluates concretely.

Operators: `+`, `-`, `*`, `/`, `//`, `%`, `mod`, `**`, `==`, `!=`, `~=`, `<`, `>`, `<=`, `>=`, `and`, `or`, `in`, `&`, `|`, `^`, `<<`, `>>`, `..`, `.`, `===`, `?:`.

**Pointer arithmetic**: When one operand is a `Pointer`, `+` and `-` with an integer produce a new `Pointer` with adjusted offset. `Pointer - Pointer` (same base) returns the integer offset difference. Relational operators (`<`, `>`, `<=`, `>=`, `==`, `!=`) between same-base Pointers compare offsets.

```
%9 = binop + %a %b
%10 = binop <= %x %limit
%11 = binop + %ptr %1          // pointer arithmetic: ptr + 1
%12 = binop - %p2 %p1          // pointer difference: p2 - p1 → int
%13 = binop < %p1 %p2          // pointer comparison: p1 < p2 → bool
```

### UNOP

Unary operation.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register |
| `operator` | `UnopKind` | operator enum |
| `operand` | `Register` | operand |

Operators: `-`, `+`, `not`, `~`, `#` (length), `!`, `!!`.

```
%11 = unop - %x
%12 = unop not %cond
```

### ADDRESS_OF

Take the address of a named variable (pointer creation).

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register (receives a `Pointer`) |
| `var_name` | `VarName` | variable whose address is taken |

Implements the `&x` operator for C and Rust. The operand is a **variable name** (not a register), because the VM needs the variable's identity to set up aliasing.

**Behaviour by variable type:**
- **Primitive** (int, float, bool, string): promotes the value from `local_vars` to a `HeapObject` on the heap, records the variable in `var_heap_aliases`, and returns a `Pointer(base=heap_addr, offset=0)`. Subsequent reads/writes to the variable go through the heap.
- **Struct/array** (already on heap): wraps the existing heap address in a `Pointer` without aliasing (the variable already points to the heap).
- **Function reference**: returns the function reference unchanged (identity — `&func` is the function itself).

Taking `&x` twice on the same variable returns the same `Pointer` (idempotent).

```
%0 = address_of x              // &x → Pointer to x's heap-backed storage
```

### LOAD_INDIRECT

Read through a pointer (pointer dereference).

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register |
| `ptr_reg` | `Register` | pointer to dereference |

Resolves `ptr_reg` to a `Pointer`, then reads `heap[base].fields[str(offset)]` (INDEX first, then PROPERTY). If the pointed slot is missing and `base` is an object/array heap address (`obj_*` or `arr_*`), dereference is treated as pointer identity (returns the same pointer) — this preserves byref object semantics. Function-pointer dereference (`BoundFuncRef`) is also identity. Otherwise, missing/invalid dereference yields a fresh symbolic value. This is how C and Rust lower `*ptr` in read context.

```
%1 = load_indirect %ptr        // *ptr → reads through the pointer
```

### LOAD_FIELD_INDIRECT

Load a field from a heap object where the field name is in a register (dynamic field access).

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register |
| `obj_reg` | `Register` | object pointer |
| `name_reg` | `Register` | register holding the field name string |

Resolves `obj_reg` to a `Pointer` and extracts the base heap address via `_heap_addr()`, then resolves `name_reg` to a field name string. If the object is on the heap and the field exists, returns the field value. If the field is missing, checks for a `__method_missing__` method on the object and dispatches to it with `(self, field_name)`. If no `__method_missing__` exists or the object is not on the heap, returns a fresh symbolic value. Used by `__method_missing__` implementations to forward field access by dynamic name.

```
%1 = load_field_indirect %obj %name   // obj[name] where name is a register
```

### STORE_INDIRECT

Write through a pointer (pointer dereference write).

| Field | Type | Description |
|-------|------|-------------|
| `ptr_reg` | `Register` | pointer to write through |
| `value_reg` | `Register` | value to write |

Resolves `ptr_reg` to a `Pointer` and writes `value_reg` to `heap[base].fields[str(offset)]`. A non-pointer target is a no-op. C and Rust lower `*ptr = val` to this.

```
store_indirect %ptr %val       // *ptr = val → writes through the pointer
```

### CALL_FUNCTION

Call a named function.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register (receives return value) |
| `func_name` | `FuncName` | function to call |
| `args` | `tuple[Register \| SpreadArguments, ...]` | arguments |

Arguments may include `SpreadArguments(register)`. The VM reads the heap array the register points to and passes its elements as individual arguments. Python, Ruby and Kotlin (`*args`), JavaScript (`...arr`) and PHP (`...$arr`) lower spread syntax to it.

Resolution order: I/O provider, builtins (print, len, range, ...), local variable lookup. If the value is a class reference, dispatches as a constructor (`NEW_OBJECT` + `__init__` call). If it's a function reference, pushes a call frame and branches to the function label. For explicit constructor calls in statically-typed languages, prefer `CALL_CTOR` which carries a `TypeExpr` type hint.

```
%13 = call_function fib %n
%14 = call_function Point %x %y
%15 = call_function add *%arr          # SpreadArguments — unpacks heap array
```

### CALL_METHOD

Call a method on an object.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register |
| `obj_reg` | `Register` | receiver object |
| `method_name` | `FuncName` | method to call |
| `args` | `tuple[Register \| SpreadArguments, ...]` | arguments |

Arguments (after `method_name`) may include `SpreadArguments` operands, expanded the same way as in CALL_FUNCTION.

Resolution order: method builtins, class registry lookup, **heap field callable lookup** (for table-based OOP — if the method exists as a `BoundFuncRef` field on the heap object, it is invoked directly with `obj` injected as `self`), parent chain walk, `__method_missing__` delegation, symbolic fallback.

```
%15 = call_method %obj toString
%16 = call_method %list append %val
```

### CALL_UNKNOWN

Call a dynamically-resolved callable.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register |
| `target_reg` | `Register` | register holding the callable |
| `args` | `tuple[Register \| SpreadArguments, ...]` | arguments |

Used for higher-order functions and dynamic dispatch. Resolves `target_reg` — if it's a function reference, dispatches as a user function. Otherwise delegates to the unresolved call resolver.

```
%17 = call_unknown %callback %x
```

### CALL_CTOR

Call a class constructor with a typed type hint.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register (receives the new object) |
| `func_name` | `FuncName` | class name |
| `type_hint` | `TypeExpr` | type of the object being constructed |
| `args` | `tuple[Register \| SpreadArguments, ...]` | arguments |

Emitted by the Java, C#, Scala, C++, Pascal and Go frontends for explicit constructor calls (`new Dog(...)`, `Dog{...}`, type conversions). `type_hint` carries structured type information (e.g. `ArrayList<Integer>`) through to the heap object. Resolution follows `CALL_FUNCTION`'s constructor dispatch, with the type hint passed to the VM.

```
%obj = call_ctor Dog %x %y
```

### CALL_WITH_MEMORY

Call a COBOL subprogram, passing each argument by address.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | receives the callee's RETURN-CODE; also feeds `GIVING` |
| `func_name` | `FuncName` | callee program name (static `CALL 'NAME'`) |
| `params_reg` | `Register` | argument array |
| `target_reg` | `Register` | callee name as a runtime string (`CALL identifier`); `NO_REGISTER` when static |

Lowers `CALL ... USING` (ADR-150). The caller builds the argument array in plain IR: a `NEW_ARRAY` with a `count` field, and per argument a `NEW_OBJECT` with `region`, `offset` and `omitted`. BY REFERENCE passes the argument's own region and offset. BY CONTENT, BY VALUE and literals pass a fresh copy. OMITTED passes a marker.

Dispatch goes through the callee's program singleton:

1. Take the program id from `target_reg` (stripped, upper-cased) when present, else from `func_name` (upper-cased).
2. Find `__prog_<PROGRAM-ID>` in the scope chain; it points to the singleton heap object.
3. Load its `__init_params__` field, a `BoundFuncRef`.
4. Push a frame for it with `__call_arguments` bound to the argument array, and branch to its label.

The callee binds each LINKAGE 01 from `__call_arguments` in plain IR. If the singleton, `__init_params__` or its label is missing, a static call goes to the configured unresolved-call resolver; a runtime-resolved call raises `UnresolvedProgramError`.

```
%r9 = call_with_memory SUBPROG %r8
%r9 = call_with_memory SUBPROG %r8 %r7     # target_reg present: name taken from %r7
```

---

## Value consumers and control flow

These opcodes leave `result_reg` as `NO_REGISTER`.

### DECL_VAR

Declare a new variable in the current scope.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `VarName` | variable name |
| `value_reg` | `Register` | initial value |

Always creates (or overwrites) the variable in the **current** call frame's `local_vars`. Used for all declaration-site bindings: `let`/`var`/`const`/`val` declarations, function/class definitions, parameter bindings, catch variables, and for-loop variable initializations.

```
decl_var x %5
```

### STORE_VAR

Assign a value to an existing variable.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `VarName` | variable name |
| `value_reg` | `Register` | value to assign |

Walks the **scope chain** (call stack in reverse) to find an existing binding for `name`, then writes to that frame. If no existing binding is found, falls back to creating in the current frame. Used for bare assignments (`x = 10`), augmented assignments, and any write to an already-declared variable.

**Alias-aware**: If the variable has been promoted to the heap via `ADDRESS_OF` (i.e., it has an entry in `var_heap_aliases`), the write goes through the heap object instead of `local_vars`. This ensures that assignments to the original variable are visible through pointers.

**Closure-aware**: If the target frame has a `closure_env_id` and the variable is in `captured_var_names`, the closure environment's bindings are also updated.

For block-scoped languages, `name` may be a mangled name (e.g. `x$1`) produced by the frontend's scope tracker. See [Block-Scope Tracking](type-system.md#block-scope-tracking-llvm-style).

```
store_var x %5
```

### STORE_FIELD

Write a value into a heap object field.

| Field | Type | Description |
|-------|------|-------------|
| `obj_reg` | `Register` | object pointer |
| `field_name` | `FieldName` | field to write |
| `value_reg` | `Register` | value to store |

Resolves `obj_reg` to a `Pointer`, extracts the base heap address via `_heap_addr()`, then writes `value_reg` into the object's field. All heap references are `Pointer` objects — there is no separate bare-string code path.

```
store_field %obj name %val
```

### STORE_INDEX

Write a value into an array/map at an index.

| Field | Type | Description |
|-------|------|-------------|
| `arr_reg` | `Register` | array/map pointer |
| `index_reg` | `Register` | index or key |
| `value_reg` | `Register \| SpreadArguments` | value to store |

```
store_index %arr %i %val
```

### BRANCH_IF

Conditional branch.

| Field | Type | Description |
|-------|------|-------------|
| `cond_reg` | `Register` | condition register |
| `branch_targets` | `tuple[CodeLabel, ...]` | `(true_label, false_label)` |

Resolves `cond_reg`. If concrete, evaluates `bool(value)` and branches accordingly. If symbolic, deterministically takes the true branch and records a path condition.

```
branch_if %cond if_true_0,if_false_0
```

### BRANCH

Unconditional jump.

| Field | Type | Description |
|-------|------|-------------|
| `label` | `CodeLabel` | target label |

```
branch end_if_0
```

### RETURN

Return from the current function.

| Field | Type | Description |
|-------|------|-------------|
| `value_reg` | `Register \| None` | return value; `None` when there is none |
| `implicit` | `bool` | `True` for a synthetic fall-off-the-end return; default `False` |

Pops the call frame and delivers the value to the caller's result register. Return-type inference skips implicit returns, since they are lowering artifacts.

```
return %result
```

### HALT

Terminate the whole run unit from any call depth. COBOL only: `lower_stop_run` emits it for `STOP RUN`. `RETURN` (`GOBACK`, `EXIT PROGRAM`) resumes the caller one frame at a time instead.

_(no fields beyond the `InstructionBase` defaults: `source_location`, `result_reg`, `label`, `branch_targets`, `id`)_

Both step loops (`_run_loop` and `execute_cfg_traced`) `break` on `HALT` after applying its update, skipping `_handle_return_flow()`. It is a separate type rather than a flag on `RETURN` so that return-type inference, which dispatches on exact type, ignores it.

```
halt
```

### THROW

Throw an exception.

| Field | Type | Description |
|-------|------|-------------|
| `value_reg` | `Register \| None` | exception value |

Checks the exception stack. If a handler exists, pops it and branches to the catch label. If no handler exists, the throw is uncaught.

```
throw %exc
```

### TRY_PUSH

Push an exception handler.

| Field | Type | Description |
|-------|------|-------------|
| `catch_labels` | `tuple[CodeLabel, ...]` | catch block labels |
| `finally_label` | `CodeLabel` | finally block label |
| `end_label` | `CodeLabel` | end of try/catch |

Pushes a handler onto the exception stack. `catch_labels` is a typed `tuple[CodeLabel, ...]`; `finally_label` and `end_label` are `CodeLabel` values. The handler remains active until a matching `TRY_POP`.

```
try_push catch_0,catch_1 finally_0 end_try_0
```

### TRY_POP

Pop the current exception handler.

_(no fields)_

```
try_pop
```

---

## Special

### SYMBOLIC

Create a symbolic (unknown) value.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register |
| `hint` | `str` | descriptive hint (e.g. `"param:x"`, `"unsupported:node_type"`) |

Primarily used for function parameters with the convention `"param:name"`. When the VM encounters a `param:` hint and the parameter has already been bound by the caller, it uses the bound value instead of creating a fresh symbolic.

```
%0 = symbolic param:x
store_var x %0
```

Also emitted as a fallback for unsupported AST node types (`"unsupported:node_type"`).

### LABEL

Branch target (pseudo-instruction).

| Field | Type | Description |
|-------|------|-------------|
| `label` | `CodeLabel` | label name |

Not executed — marks a position that `BRANCH`, `BRANCH_IF`, and call dispatch can jump to.

```
entry:
func_fib_0:
if_true_3:
```

---

## Region operations

Byte-addressed memory for languages with explicit memory layout (COBOL). Regions are segments of one flat address space owned by `VMState` (ADR-151, ADR-152). A region handle is its segment's base address, an integer.

### ALLOC_REGION

Allocate a zeroed byte region.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | receives the region's base address |
| `size_reg` | `Register` | allocation size in bytes |

Places the region at the next free address. A symbolic size yields a symbolic address.

```
%r0 = alloc_region %r1
```

### WRITE_REGION

Write bytes into a region.

| Field | Type | Description |
|-------|------|-------------|
| `region_reg` | `Register` | region base address |
| `offset_reg` | `Register` | byte offset |
| `length` | `int` | byte count (compile-time constant) |
| `value_reg` | `Register` | bytes to write (`list[int]`) |

Writes `value[0:length]` at address `region + offset`. A write past the segment's end continues into the following segments. No-op if any argument is symbolic.

```
write_region %rgn %off 4 %data
```

### LOAD_REGION

Read bytes from a region.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | receives `list[int]` |
| `region_reg` | `Register` | region base address |
| `offset_reg` | `Register` | byte offset |
| `length` | `int` | byte count (compile-time constant) |

Reads `length` bytes from `region + offset`, across segments if needed. Bytes past the last allocated byte read as zero. A symbolic address or offset yields a symbolic result.

```
%result = load_region %rgn %off 4
```

---

## Continuation operations

Named return points for paragraph-based control flow (COBOL PERFORM).

### SET_CONTINUATION

Save a return point.

| Field | Type | Value |
|-------|------|-------|
| `name` | `ContinuationName` | name key for the continuation |
| `target_label` | `CodeLabel` | label to jump to on resume |

Stores the mapping `name → target_label`. Used before branching to a paragraph so execution knows where to return.

```
set_continuation para_WORK_end perform_return_0
```

### RESUME_CONTINUATION

Jump to a saved return point.

| Field | Type | Value |
|-------|------|-------|
| `name` | `ContinuationName` | name key to look up |

Looks up the continuation and branches to its label. If no continuation is set, falls through. Clears the continuation after use.

```
resume_continuation para_WORK_end
```

---

## Cooperative suspension

A frontend-agnostic suspend/resume primitive. Continuation operations are return points inside one execution; `SUSPEND` instead stops the executor and hands a serializable state back to its caller. See [VM design notes](notes-on-vm-design.md#cooperative-suspendresume).

### SUSPEND

Suspend execution, yielding a value to the driver.

| Field | Type | Value |
|-------|------|-------|
| `operand_reg` | `Register` | value yielded to the driver |
| `result_reg` | `Register` | receives the driver's value on resume |

Under `run_resumable()` / `resume()`, the step loop stops at `SUSPEND` and returns `Suspended(state, value)`: `value` is `operand_reg`'s contents, `state` is an `ExecutionState` (the `VMState` plus the cursor). `resume(cfg, registry, state, value)` writes `value` into `result_reg` and continues at the next instruction. Under `execute_cfg()` a `SUSPEND` raises `RuntimeError`.

```
%p = const 42
%v = suspend %p        # yield 42 to the driver; on resume, %v = the driver's value
```

---

## Module imports

### IMPORT_MODULE

Import a module. The linker expands it into other opcodes.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | register bound to the module |
| `module_path` | `str` | module path as written in source (e.g. `os.path`, `./m`) |
| `resolved_path` | `PathName \| NoPathName` | local file the import resolves to; `NO_PATH_NAME` when external or unresolved |

Emitted by the Python, JavaScript and TypeScript frontends, followed by `DECL_VAR` (whole-module import) or `LOAD_FIELD` + `DECL_VAR` per imported name.

The linker rewrites a resolved import. Each `LOAD_FIELD` + `DECL_VAR` naming an exported function or class becomes `CONST` (`func_ref` or `class_ref` to the namespaced label) + `DECL_VAR`. A pair naming an exported variable is dropped, since the dependency's top-level code already bound it. A name not found in the exports keeps its pair. With no such pairs, the `IMPORT_MODULE` is dropped. An unresolved `IMPORT_MODULE` is kept. The VM has no local handler for it, so executing one falls through to the LLM backend.

```
%0 = import_module utils /project/utils.py
%1 = load_field %0 helper
decl_var helper %1
```

---

## Common IR patterns

### Function definition

A function body is bracketed by a branch-over and its entry label. Parameters are bound with `SYMBOLIC` + `DECL_VAR`. After the end label, a `CONST` function reference is bound to the function's name.

```
branch end_foo_1
func_foo_0:
  %0 = symbolic param:x
  decl_var x %0
  ... body ...
  %2 = const None
  return %2
end_foo_1:
%3 = const func_foo_0
decl_var foo %3
```

### Class definition

Same pattern, with method definitions inside the class block.

```
branch end_class_MyClass_1
class_MyClass_0:
  ... method definitions ...
end_class_MyClass_1:
%4 = const class_MyClass_0
decl_var MyClass %4
```

### Constructor call

Statically-typed frontends (Java, C#, Scala, C++, Pascal, Go) emit `CALL_CTOR` for constructor calls. The instruction carries a `TypeExpr` type hint that flows to the heap object, preserving parameterized type information (e.g., `ArrayList<Integer>`).

```
%obj = call_ctor Point %x %y
```

Dynamic frontends (Python, Ruby) and the LLM frontend use `CALL_FUNCTION` on the class name, which the VM resolves to a constructor via scope lookup. JavaScript and PHP use `NEW_OBJECT` + `CALL_METHOD("constructor"/"__construct")`.

### If/else

```
... condition -> %cond ...
branch_if %cond if_true_0,if_false_0
if_true_0:
  ... true body ...
  branch end_if_0
if_false_0:
  ... false body ...
  branch end_if_0
end_if_0:
```

### While loop

```
loop_0:
  ... condition -> %cond ...
  branch_if %cond body_0,end_0
body_0:
  ... body ...
  branch loop_0
end_0:
```

### Try/catch/finally

```
try_push catch_0 finally_0 end_try_0
  ... try body ...
try_pop
branch finally_0
catch_0:
  ... catch body ...
  branch finally_0
finally_0:
  ... finally body ...
end_try_0:
```

### Pointer aliasing (C/Rust)

The `ADDRESS_OF` + `LOAD_INDIRECT`/`STORE_INDIRECT` pattern implements pointer semantics:

```
// C source: int x = 42; int *ptr = &x; *ptr = 99; int answer = x;
%0 = const 42
store_var x %0
%1 = address_of x              // promotes x to heap, returns Pointer
store_var ptr %1
%2 = load_var ptr
%3 = const 99
store_indirect %2 %3           // *ptr = 99 (writes through to x's heap storage)
%4 = load_var x                 // reads 99 from heap (alias-aware)
store_var answer %4
```

Pointer arithmetic on arrays:

```
// C source: int arr[3] = {10, 20, 30}; int *p = arr; int val = *(p + 1);
... arr setup ...
%p = load_var arr               // Pointer from NEW_ARRAY
%1 = const 1
%p1 = binop + %p %1            // Pointer(base=arr_0, offset=1)
%val = load_indirect %p1       // reads heap[arr_0].fields["1"] → 20
```
