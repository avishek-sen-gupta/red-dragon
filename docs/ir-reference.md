# IR Reference

RedDragon uses a flattened high-level three-address code IR. Every program — regardless of source language or frontend — is lowered to a linear sequence of typed instruction dataclasses drawn from 33 opcodes.

## Instruction format

Each opcode has a dedicated frozen dataclass in `interpreter/instructions.py` (33 classes total). All share an `InstructionBase` with `source_location`. All fields use domain types:

- **Register-holding fields**: `Register` objects (e.g., `result_reg`, `left`, `right`)
- **Label-holding fields**: `CodeLabel` objects (e.g., `label`, `true_label`, `false_label`)
- **Variable names**: `VarName` objects (e.g., `name` on `LoadVar`/`StoreVar`/`DeclVar`)
- **Field names**: `FieldName` objects (e.g., `field_name` on `LoadField`/`StoreField`)
- **Function/method names**: `FuncName` objects (e.g., `func_name` on `CallFunction`, `method_name` on `CallMethod`)
- **Operators**: `BinopKind`/`UnopKind` enums (e.g., `operator` on `Binop`/`Unop`)

Each instruction implements `reads()` and `writes()` methods returning `StorageIdentifier` values (either `Register` or `VarName`) for dataflow analysis.

```python
# Example: Binop instruction
@dataclass(frozen=True)
class Binop(InstructionBase):
    result_reg: Register
    operator: BinopKind
    left: Register
    right: Register

    def reads(self) -> list[StorageIdentifier]:
        return [self.left, self.right]

    def writes(self) -> list[StorageIdentifier]:
        return [self.result_reg]
```

The legacy `IRInstruction` name is now a factory function that returns the appropriate typed subclass, maintaining backward compatibility with existing call sites.

Text representation: `%0 = const 42` or `store_var x %0` or `entry:` (for labels).

Registers are named `%0`, `%1`, ... and are assigned once (SSA-like, though not enforced). Labels are strings like `entry`, `func_fib_0`, `if_true_3`.

---

## Value producers

These opcodes write a result into `result_reg`.

### CONST

Load a constant value.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register |
| `value` | `str` | literal value string |

The value string is parsed at execution time: integers, floats, booleans (`True`/`False`), `None`, quoted strings (`"hello"`), function references (`<function:foo@func_foo_0>`), class references (`<class:Foo@class_Foo_0>`).

```
%0 = const 42
%1 = const "hello"
%2 = const True
%3 = const <function:fib@func_fib_0>
```

### LOAD_VAR

Read a named variable.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register |
| `name` | `VarName` | variable name |

Searches the call stack from the current frame backwards. If the variable is not found, the VM creates a fresh symbolic value.

**Alias-aware**: If the variable has been promoted to the heap via `ADDRESS_OF` (i.e., it has an entry in `var_heap_aliases`), the read goes through the heap object instead of `local_vars`. This ensures that writes through pointers (`*ptr = 99`) are visible when the original variable is read.

For block-scoped languages, `var_name` may be a mangled name (e.g. `x$1`) produced by the frontend's scope tracker. See [Block-Scope Tracking](type-system.md#block-scope-tracking-llvm-style).

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
%5 = load_field %obj "name"
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

Resolves `ptr_reg` to a `Pointer`, then reads `heap[base].fields[str(offset)]`. If the resolved value is a `BoundFuncRef`, returns it unchanged (identity). If the resolved value is not a `Pointer` but is on the heap, returns a fresh symbolic value. This is how C and Rust lower `*ptr` in read context.

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

Resolves `ptr_reg` to a `Pointer`, then writes `val_reg` to `heap[base].fields[str(offset)]`. This is how C and Rust lower `*ptr = val`.

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

Arguments may include `SpreadArguments(register)` operands. When the VM encounters a `SpreadArguments` in the operand list, it reads the heap array at that register's pointer and inlines the elements as individual arguments. This supports spread/splat syntax across all 5 supported languages (`*args` in Python/Ruby/Kotlin, `...arr` in JS, `...$arr` in PHP).

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
%15 = call_method %obj "toString"
%16 = call_method %list "append" %val
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

| Field | Value |
|-------|-------|
| `result_reg` | target register (receives the new object) |
| `func_name` | class name (string) |
| `type_hint` | `TypeExpr` — the type of the object being constructed |
| `args` | `(arg1_reg, arg2_reg, ...)` |

Used by Java, C#, Scala, C++, Pascal, and Go frontends for explicit constructor calls (`new Dog(...)`, `Dog{...}`, type conversions). The `type_hint` carries structured type information (e.g., `ParameterizedType("ArrayList", (scalar("Integer"),))`) that flows through to the heap object. Resolution follows the same path as CALL_FUNCTION's constructor dispatch, but with the typed type hint passed directly to the VM.

```
%obj = call_ctor Dog %x %y
```

---

## Value consumers and control flow

These opcodes have `result_reg = null`.

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

Walks the **scope chain** (call stack in reverse) to find an existing binding for `var_name`, then writes to that frame. If no existing binding is found, falls back to creating in the current frame. Used for bare assignments (`x = 10`), augmented assignments, and any write to an already-declared variable.

**Alias-aware**: If the variable has been promoted to the heap via `ADDRESS_OF` (i.e., it has an entry in `var_heap_aliases`), the write goes through the heap object instead of `local_vars`. This ensures that assignments to the original variable are visible through pointers.

**Closure-aware**: If the target frame has a `closure_env_id` and the variable is in `captured_var_names`, the closure environment's bindings are also updated.

For block-scoped languages, `var_name` may be a mangled name (e.g. `x$1`) produced by the frontend's scope tracker. See [Block-Scope Tracking](type-system.md#block-scope-tracking-llvm-style).

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
store_field %obj "name" %val
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
| `value_reg` | `Register \| None` | return value (`None` for implicit void return) |

Pops the call frame and delivers the value to the caller's result register.

```
return %result
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

Pushes a handler onto the exception stack. `catch_labels_csv` is a comma-separated list of catch block labels. The handler remains active until a matching `TRY_POP`.

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

Byte-addressed memory for languages with explicit memory layout (COBOL).

### ALLOC_REGION

Allocate a named byte region.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register (receives region address like `rgn_0`) |
| `size_reg` | `Register` | register holding allocation size in bytes |

Allocates a zeroed `bytearray` of the given size.

```
%r0 = alloc_region 1024
```

### WRITE_REGION

Write bytes into a region.

| Field | Type | Description |
|-------|------|-------------|
| `region_reg` | `Register` | region address |
| `offset_reg` | `Register` | byte offset |
| `length` | `int` | byte count (compile-time constant from PIC clause) |
| `value_reg` | `Register` | value to write |

Writes `value_reg[0:length]` into `region[offset:offset+length]`. No-op if any argument is symbolic.

```
write_region %rgn %off 4 %data
```

### LOAD_REGION

Read bytes from a region.

| Field | Type | Description |
|-------|------|-------------|
| `result_reg` | `Register` | target register (receives `list[int]`) |
| `region_reg` | `Register` | region address |
| `offset_reg` | `Register` | byte offset |
| `length` | `int` | byte count (compile-time constant from PIC clause) |

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

## Common IR patterns

### Function definition

Functions are lowered as a code block bracketed by a branch-over and a label, followed by a CONST+STORE_VAR to register the function reference.

```
branch end_foo_1
func_foo_0:
  %0 = symbolic param:x
  store_var x %0
  ... body ...
  %r = const None
  return %r
end_foo_1:
%f = const <function:foo@func_foo_0>
store_var foo %f
```

### Class definition

Same pattern, with method definitions nested inside the class block.

```
branch end_MyClass_1
class_MyClass_0:
  ... method definitions ...
end_MyClass_1:
%c = const <class:MyClass@class_MyClass_0>
store_var MyClass %c
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
