# IR Reference

RedDragon uses a flattened high-level three-address code IR. Every program — regardless of source language or frontend — is lowered to a linear sequence of `IRInstruction`s drawn from 27 opcodes.

## Instruction format

```python
class IRInstruction:
    opcode: Opcode
    result_reg: str | None     # destination register (%0, %1, ...), null for side-effect-only ops
    operands: list[Any]        # opcode-specific arguments
    label: str | None          # for LABEL and branch targets
    source_location: SourceLocation  # originating AST span (or NO_SOURCE_LOCATION)
```

Text representation: `%0 = const 42` or `store_var x %0` or `entry:` (for labels).

Registers are named `%0`, `%1`, ... and are assigned once (SSA-like, though not enforced). Labels are strings like `entry`, `func_fib_0`, `if_true_3`.

---

## Value producers

These opcodes write a result into `result_reg`.

### CONST

Load a constant value.

| Field | Value |
|-------|-------|
| `result_reg` | target register |
| `operands` | `[value_string]` |

The value string is parsed at execution time: integers, floats, booleans (`True`/`False`), `None`, quoted strings (`"hello"`), function references (`<function:foo@func_foo_0>`), class references (`<class:Foo@class_Foo_0>`).

```
%0 = const 42
%1 = const "hello"
%2 = const True
%3 = const <function:fib@func_fib_0>
```

### LOAD_VAR

Read a named variable.

| Field | Value |
|-------|-------|
| `result_reg` | target register |
| `operands` | `[var_name]` |

Searches the call stack from the current frame backwards. If the variable is not found, the VM creates a fresh symbolic value.

For block-scoped languages, `var_name` may be a mangled name (e.g. `x$1`) produced by the frontend's scope tracker. See [Block-Scope Tracking](type-system.md#block-scope-tracking-llvm-style).

```
%4 = load_var x
```

### LOAD_FIELD

Read a field from a heap object.

| Field | Value |
|-------|-------|
| `result_reg` | target register |
| `operands` | `[obj_reg, field_name]` |

Resolves `obj_reg` to a heap address, then looks up `field_name` in the object's fields. Returns a fresh symbolic value if the field does not exist.

```
%5 = load_field %obj "name"
```

### LOAD_INDEX

Read an element by index or key.

| Field | Value |
|-------|-------|
| `result_reg` | target register |
| `operands` | `[arr_reg, index_reg]` |

Resolves both registers. For native Python lists/strings, performs direct indexing. For heap arrays, looks up `str(index)` in the object's fields. Returns a fresh symbolic value if the key does not exist.

```
%6 = load_index %arr %i
```

### NEW_OBJECT

Allocate a new heap object.

| Field | Value |
|-------|-------|
| `result_reg` | target register (receives heap address like `obj_0`) |
| `operands` | `[type_name]` |

Creates a new entry in the heap with the given type hint. Fields are initially empty.

```
%7 = new_object Point
```

### NEW_ARRAY

Allocate a new heap array.

| Field | Value |
|-------|-------|
| `result_reg` | target register (receives heap address like `arr_0`) |
| `operands` | `[type_name]` |

Like `NEW_OBJECT` but semantically represents an array/list. Elements are stored as fields keyed by stringified indices (`"0"`, `"1"`, ...).

```
%8 = new_array int[]
```

### BINOP

Binary operation.

| Field | Value |
|-------|-------|
| `result_reg` | target register |
| `operands` | `[operator, lhs_reg, rhs_reg]` |

Resolves both operand registers. If either is symbolic, produces a symbolic result with a constraint. Otherwise evaluates concretely.

Operators: `+`, `-`, `*`, `/`, `//`, `%`, `mod`, `**`, `==`, `!=`, `~=`, `<`, `>`, `<=`, `>=`, `and`, `or`, `in`, `&`, `|`, `^`, `<<`, `>>`, `..`, `.`, `===`, `?:`.

```
%9 = binop + %a %b
%10 = binop <= %x %limit
```

### UNOP

Unary operation.

| Field | Value |
|-------|-------|
| `result_reg` | target register |
| `operands` | `[operator, operand_reg]` |

Operators: `-`, `+`, `not`, `~`, `#` (length), `!`, `!!`.

```
%11 = unop - %x
%12 = unop not %cond
```

### CALL_FUNCTION

Call a named function or constructor.

| Field | Value |
|-------|-------|
| `result_reg` | target register (receives return value) |
| `operands` | `[func_name, arg1_reg, arg2_reg, ...]` |

Resolution order: I/O provider, builtins (print, len, range, ...), local variable lookup. If the value is a class reference, dispatches as a constructor (`NEW_OBJECT` + `__init__` call). If it's a function reference, pushes a call frame and branches to the function label.

```
%13 = call_function fib %n
%14 = call_function Point %x %y
```

### CALL_METHOD

Call a method on an object.

| Field | Value |
|-------|-------|
| `result_reg` | target register |
| `operands` | `[obj_reg, method_name, arg1_reg, ...]` |

Resolves `obj_reg`, looks up the object's type hint in the class registry, finds the method, binds the object as the first parameter (self/this), and dispatches.

```
%15 = call_method %obj "toString"
%16 = call_method %list "append" %val
```

### CALL_UNKNOWN

Call a dynamically-resolved callable.

| Field | Value |
|-------|-------|
| `result_reg` | target register |
| `operands` | `[target_reg, arg1_reg, ...]` |

Used for higher-order functions and dynamic dispatch. Resolves `target_reg` — if it's a function reference, dispatches as a user function. Otherwise delegates to the unresolved call resolver.

```
%17 = call_unknown %callback %x
```

---

## Value consumers and control flow

These opcodes have `result_reg = null`.

### STORE_VAR

Write a value into a named variable.

| Field | Value |
|-------|-------|
| `operands` | `[var_name, value_reg]` |

Stores in the current call frame's local variables. If inside a closure, also updates the captured environment.

For block-scoped languages, `var_name` may be a mangled name (e.g. `x$1`) produced by the frontend's scope tracker. See [Block-Scope Tracking](type-system.md#block-scope-tracking-llvm-style).

```
store_var x %5
```

### STORE_FIELD

Write a value into a heap object field.

| Field | Value |
|-------|-------|
| `operands` | `[obj_reg, field_name, value_reg]` |

```
store_field %obj "name" %val
```

### STORE_INDEX

Write a value into an array/map at an index.

| Field | Value |
|-------|-------|
| `operands` | `[arr_reg, index_reg, value_reg]` |

```
store_index %arr %i %val
```

### BRANCH_IF

Conditional branch.

| Field | Value |
|-------|-------|
| `operands` | `[cond_reg]` |
| `label` | `"true_label,false_label"` |

Resolves `cond_reg`. If concrete, evaluates `bool(value)` and branches accordingly. If symbolic, deterministically takes the true branch and records a path condition.

```
branch_if %cond if_true_0,if_false_0
```

### BRANCH

Unconditional jump.

| Field | Value |
|-------|-------|
| `operands` | `[]` |
| `label` | target label |

```
branch end_if_0
```

### RETURN

Return from the current function.

| Field | Value |
|-------|-------|
| `operands` | `[value_reg]` (or `[]` for implicit None return) |

Pops the call frame and delivers the value to the caller's result register.

```
return %result
```

### THROW

Throw an exception.

| Field | Value |
|-------|-------|
| `operands` | `[value_reg]` (or `[]`) |

Checks the exception stack. If a handler exists, pops it and branches to the catch label. If no handler exists, the throw is uncaught.

```
throw %exc
```

### TRY_PUSH

Push an exception handler.

| Field | Value |
|-------|-------|
| `operands` | `[catch_labels_csv, finally_label, end_label]` |

Pushes a handler onto the exception stack. `catch_labels_csv` is a comma-separated list of catch block labels. The handler remains active until a matching `TRY_POP`.

```
try_push catch_0,catch_1 finally_0 end_try_0
```

### TRY_POP

Pop the current exception handler.

| Field | Value |
|-------|-------|
| `operands` | `[]` |

```
try_pop
```

---

## Special

### SYMBOLIC

Create a symbolic (unknown) value.

| Field | Value |
|-------|-------|
| `result_reg` | target register |
| `operands` | `[hint_string]` |

Primarily used for function parameters with the convention `"param:name"`. When the VM encounters a `param:` hint and the parameter has already been bound by the caller, it uses the bound value instead of creating a fresh symbolic.

```
%0 = symbolic param:x
store_var x %0
```

Also emitted as a fallback for unsupported AST node types (`"unsupported:node_type"`).

### LABEL

Branch target (pseudo-instruction).

| Field | Value |
|-------|-------|
| `label` | label name |
| `operands` | `[]` |

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

| Field | Value |
|-------|-------|
| `result_reg` | target register (receives region address like `rgn_0`) |
| `operands` | `[size]` |

Allocates a zeroed `bytearray` of the given size.

```
%r0 = alloc_region 1024
```

### WRITE_REGION

Write bytes into a region.

| Field | Value |
|-------|-------|
| `operands` | `[region_reg, offset_reg, length, value_reg]` |

Writes `value_reg[0:length]` into `region[offset:offset+length]`. No-op if any argument is symbolic.

```
write_region %rgn %off 4 %data
```

### LOAD_REGION

Read bytes from a region.

| Field | Value |
|-------|-------|
| `result_reg` | target register (receives `list[int]`) |
| `operands` | `[region_reg, offset_reg, length]` |

```
%result = load_region %rgn %off 4
```

---

## Continuation operations

Named return points for paragraph-based control flow (COBOL PERFORM).

### SET_CONTINUATION

Save a return point.

| Field | Value |
|-------|-------|
| `operands` | `[continuation_name, return_label]` |

Stores the mapping `name -> label`. Used before branching to a paragraph so execution knows where to return.

```
set_continuation para_WORK_end perform_return_0
```

### RESUME_CONTINUATION

Jump to a saved return point.

| Field | Value |
|-------|-------|
| `operands` | `[continuation_name]` |

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

Constructors are dispatched via `CALL_FUNCTION` on the class name. The VM allocates a `NEW_OBJECT`, calls `__init__`, and returns the object.

```
%obj = call_function Point %x %y
```

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
