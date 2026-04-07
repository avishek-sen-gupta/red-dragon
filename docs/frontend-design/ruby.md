# Ruby Frontend

> `interpreter/frontends/ruby/` -- Extends `BaseFrontend`

## Overview

The Ruby frontend lowers tree-sitter Ruby ASTs into the RedDragon flattened TAC IR. It handles Ruby-specific constructs including `unless` (inverted if), `until` (inverted while), modifier-form control flow (`body if cond`, `body unless cond`, `body while cond`, `body until cond`), `begin/rescue/else/ensure` exception handling, blocks and do-blocks as closures, lambdas, `case/when` pattern matching, modules, singleton classes (`class << obj`), singleton methods (`def self.method`), symbols, ranges, word arrays (`%w[]`), symbol arrays (`%i[]`), heredocs, element references (`arr[idx]`), the ternary operator, string interpolation, `super`, `yield`, `retry`, and the `self` keyword.

Ruby's tree-sitter grammar uses `call` as both the attribute access node type and the method invocation node type, which is reflected in the `attribute_node_type = "call"` constant.

## Directory Structure

```
interpreter/frontends/ruby/
  frontend.py          RubyFrontend class (thin orchestrator)
  node_types.py         RubyNodeType constants
  expressions.py        Expression lowerers (pure functions)
  control_flow.py       Control flow lowerers (pure functions)
  declarations.py       Declaration lowerers (pure functions)
  assignments.py        Assignment lowerers (pure functions)
```

## Class Hierarchy

```
Frontend (ABC)
  +-- BaseFrontend
        +-- RubyFrontend
```

`RubyFrontend` extends `BaseFrontend` directly. The class is a thin orchestrator that builds dispatch tables from pure functions defined in the sibling modules (including the extra `assignments.py` module). No other frontend extends `RubyFrontend`.

## Grammar Constants (`_build_constants()`)

| Field | Value | Notes |
|---|---|---|
| `attribute_node_type` | `"call"` | Ruby uses `call` nodes for `obj.method` |
| `attr_object_field` | `"receiver"` | tree-sitter Ruby names the LHS `receiver` |
| `attr_attribute_field` | `"method"` | tree-sitter Ruby names the RHS `method` |
| `comment_types` | `frozenset({"comment"})` | Same as base |
| `noise_types` | `frozenset({"then", "do", "end", "\n"})` | Skips Ruby block delimiters |
| `block_node_types` | `frozenset({"program", "body_statement"})` | Block-like containers |

All other `GrammarConstants` fields retain their defaults (`none_literal = "None"`, `true_literal = "True"`, `false_literal = "False"`, `default_return_value = "None"`, etc.).

## Expression Dispatch Table (`_build_expr_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `"identifier"` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `"instance_variable"` | `ruby_expr.lower_instance_variable` | `LOAD_VAR "self"` + `LOAD_FIELD` |
| `"constant"` | `common_expr.lower_identifier` | `LOAD_VAR` (e.g., `MyClass`) |
| `"integer"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"float"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"string"` | `ruby_expr.lower_ruby_string` | `CONST` or interpolation decomposition |
| `"true"` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `"false"` | `common_expr.lower_canonical_false` | `CONST "False"` |
| `"nil"` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `"binary"` | `common_expr.lower_binop` | `BINOP` |
| `"call"` | `ruby_expr.lower_ruby_call` | `CALL_METHOD` / `CALL_FUNCTION` / `CALL_UNKNOWN` |
| `"parenthesized_expression"` | `common_expr.lower_paren` | (unwraps inner expression) |
| `"parenthesized_statements"` | `common_expr.lower_paren` | (unwraps inner expression) |
| `"array"` | `common_expr.lower_list_literal` | `NEW_ARRAY` + `STORE_INDEX` |
| `"hash"` | `ruby_expr.lower_ruby_hash` | `NEW_OBJECT("hash")` + `STORE_INDEX` |
| `"argument_list"` | `ruby_expr.lower_ruby_argument_list` | (unwraps to first named child) |
| `"simple_symbol"` | `common_expr.lower_const_literal` | `CONST` (e.g., `:name`) |
| `"hash_key_symbol"` | `common_expr.lower_const_literal` | `CONST` (e.g., `name:`) |
| `"range"` | `ruby_expr.lower_ruby_range` | `CALL_FUNCTION("range", start, end)` |
| `"regex"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"lambda"` | `ruby_expr.lower_ruby_lambda` | `BRANCH` + `LABEL` + params + body + `RETURN` + `CONST func:ref` |
| `"string_array"` | `ruby_expr.lower_ruby_word_array` | `NEW_ARRAY` + `CONST` + `STORE_INDEX` per element |
| `"symbol_array"` | `ruby_expr.lower_ruby_word_array` | `NEW_ARRAY` + `CONST` + `STORE_INDEX` per element |
| `"global_variable"` | `common_expr.lower_identifier` | `LOAD_VAR` (e.g., `$stdout`) |
| `"class_variable"` | `common_expr.lower_identifier` | `LOAD_VAR` (e.g., `@@count`) |
| `"heredoc_body"` | `ruby_expr.lower_ruby_heredoc_body` | `CONST` or interpolation decomposition |
| `"element_reference"` | `ruby_expr.lower_element_reference` | `LOAD_INDEX` |
| `"heredoc_beginning"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"right_assignment_list"` | `common_expr.lower_list_literal` | `NEW_ARRAY` + `STORE_INDEX` |
| `"pattern"` | `ruby_expr.lower_ruby_pattern` | (unwraps inner child) |
| `"delimited_symbol"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"in"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"conditional"` | `ruby_expr.lower_ruby_conditional` | `BRANCH_IF` + `STORE_VAR` + `LOAD_VAR` (ternary) |
| `"unary"` | `common_expr.lower_unop` | `UNOP` |
| `"self"` | `ruby_expr.lower_ruby_self` | `LOAD_VAR("self")` |
| `"super"` | `ruby_expr.lower_ruby_super` | `CALL_FUNCTION("super", ...args)` |
| `"yield"` | `ruby_expr.lower_ruby_yield` | `CALL_FUNCTION("yield", ...args)` |

**37 entries total.**

## Statement Dispatch Table (`_build_stmt_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `"expression_statement"` | `common_assign.lower_expression_statement` | (unwraps inner expression) |
| `"assignment"` | `ruby_assign.lower_ruby_assignment` | `STORE_VAR` / `STORE_FIELD` / `STORE_INDEX` |
| `"operator_assignment"` | `ruby_assign.lower_ruby_augmented_assignment` | `BINOP` + store |
| `"return"` | `ruby_assign.lower_ruby_return` | `RETURN` |
| `"return_statement"` | `ruby_assign.lower_ruby_return` | `RETURN` (alternate node type) |
| `"if"` | `ruby_cf.lower_ruby_if` | `BRANCH_IF` + `LABEL` + `BRANCH` |
| `"if_modifier"` | `ruby_cf.lower_ruby_if_modifier` | `BRANCH_IF` + body + `BRANCH` |
| `"unless"` | `ruby_cf.lower_unless` | `UNOP("!")` + `BRANCH_IF` + `LABEL` + `BRANCH` |
| `"unless_modifier"` | `ruby_cf.lower_ruby_unless_modifier` | `UNOP("!")` + `BRANCH_IF` + body + `BRANCH` |
| `"elsif"` | `ruby_cf.lower_ruby_elsif_stmt` | `BRANCH_IF` + `LABEL` + `BRANCH` (standalone fallback) |
| `"while"` | `common_cf.lower_while` | Loop with `BRANCH_IF` |
| `"while_modifier"` | `ruby_cf.lower_ruby_while_modifier` | Modifier-form loop |
| `"until"` | `ruby_cf.lower_until` | Inverted loop with `UNOP("!")` + `BRANCH_IF` |
| `"until_modifier"` | `ruby_cf.lower_ruby_until_modifier` | Inverted modifier-form loop |
| `"for"` | `ruby_cf.lower_ruby_for` | Index-based iteration loop |
| `"method"` | `ruby_decl.lower_ruby_method_stmt` | `BRANCH` + `LABEL` + params + body + `RETURN` + `DECL_VAR` |
| `"singleton_method"` | `ruby_decl.lower_ruby_singleton_method` | Same as method but with `object.method` naming |
| `"class"` | `ruby_decl.lower_ruby_class` | `BRANCH` + `LABEL` + body + `CONST class:ref` + `DECL_VAR` |
| `"singleton_class"` | `ruby_decl.lower_ruby_singleton_class` | `BRANCH` + `LABEL` + body + `LABEL` |
| `"program"` | `lambda ctx, node: ctx.lower_block(node)` | Top-level block lowering |
| `"body_statement"` | `lambda ctx, node: ctx.lower_block(node)` | Ruby body block lowering |
| `"do_block"` | `lambda ctx, node: ruby_expr.lower_ruby_block(ctx, node)` | Closure lowering |
| `"block"` | `lambda ctx, node: ruby_expr.lower_ruby_block(ctx, node)` | Closure lowering |
| `"break"` | `common_cf.lower_break` | `BRANCH` to break target |
| `"next"` | `common_cf.lower_continue` | `BRANCH` to continue label |
| `"begin"` | `ruby_cf.lower_begin` | `begin/rescue/else/ensure` exception handling |
| `"case"` | `ruby_cf.lower_case` | `case/when` as if/else chain |
| `"module"` | `ruby_decl.lower_ruby_module` | Module as class-like structure |
| `"super"` | `lambda ctx, node: ruby_expr.lower_ruby_super(ctx, node)` | `CALL_FUNCTION("super", ...args)` |
| `"yield"` | `lambda ctx, node: ruby_expr.lower_ruby_yield(ctx, node)` | `CALL_FUNCTION("yield", ...args)` |
| `"in"` | `ruby_cf.lower_ruby_in_clause` | `in` pattern matching clause |
| `"retry"` | `ruby_cf.lower_ruby_retry` | `CALL_FUNCTION("retry")` |

**32 entries total.**

## Language-Specific Lowering Methods

### `ruby_expr.lower_element_reference(ctx, node) -> str`
Lowers `arr[idx]` (Ruby `element_reference` node type) as `LOAD_INDEX`. Extracts the first two named children as the object and index respectively.

### `ruby_expr.lower_ruby_argument_list(ctx, node) -> str`
Unwraps an `argument_list` node to its first named child. Used when `argument_list` appears in expression context (e.g., bare `return value` without parentheses). Falls back to `CONST "None"`.

### `ruby_expr.lower_ruby_call(ctx, node) -> str`
Lowers Ruby `call` nodes. Four paths:
1. **Class.new(...) constructor**: `Receiver.new(args)` where receiver starts uppercase -- emits `NEW_OBJECT` + `CALL_METHOD("__init__", ...)`.
2. **Method call with receiver**: `receiver.method(args)` -- emits `CALL_METHOD`. Also detects `block`/`do_block` children and appends the lowered block closure as an extra argument.
3. **Standalone function call**: `method(args)` (no receiver) -- emits `CALL_FUNCTION`. Special-cases `raise` as `THROW`.
4. **Fallback**: unknown call target -- emits `SYMBOLIC("unknown_call_target")` + `CALL_UNKNOWN`.

Block/do_block detection is critical: `arr.each do |x| ... end` passes the block as an additional argument to `CALL_METHOD`.

### `ruby_expr.lower_instance_variable(ctx, node) -> str`
Lowers `@var` as `LOAD_VAR "self"` + `LOAD_FIELD self_reg "var"` (strips the `@` prefix).

### `ruby_expr.lower_ruby_string(ctx, node) -> str`
Lowers Ruby strings. If the string contains interpolation (`#{expr}`), decomposes into `CONST` fragments + `LOAD_VAR` + `BINOP "+"` concatenation. Otherwise delegates to `lower_const_literal`.

### `ruby_expr.lower_ruby_heredoc_body(ctx, node) -> str`
Lowers Ruby heredoc body with interpolation support, similar to `lower_ruby_string`.

### `ruby_assign.lower_ruby_return(ctx, node)`
Lowers `return expr`. Filters out both `"return"` and `"return_statement"` tokens from children. Handles bare `return` by emitting `CONST "None"` + `RETURN`.

### `ruby_cf.lower_unless(ctx, node)`
Lowers `unless cond ... else ... end`. Negates the condition with `UNOP("!")`, then follows the standard if pattern with `BRANCH_IF` on the negated register. Supports an alternative (else) branch.

### `ruby_cf.lower_until(ctx, node)`
Lowers `until cond ... end`. Loop that negates the condition each iteration with `UNOP("!")`. Continues while the condition is false (i.e., the negation is true).

### `ruby_cf.lower_ruby_for(ctx, node)`
Lowers `for var in collection ... end`. Implements as index-based iteration: initializes idx to 0, computes `len(collection)`, branches on `idx < len`, loads element via `LOAD_INDEX`, stores to the loop variable, executes body, increments.

### `ruby_decl.lower_ruby_method(ctx, node, inject_self=False)`
Lowers `def method_name(params) ... end`. Standard function lowering pattern: `BRANCH` past body, `LABEL`, optional `self` param injection, params via `ruby_expr.lower_ruby_params`, body with implicit return handling via `_lower_body_with_implicit_return`, end label, `CONST func:ref`, `DECL_VAR`. Ruby's `initialize` method is renamed to `__init__` when `inject_self=True`.

### `ruby_decl.lower_ruby_method_stmt(ctx, node)`
Statement wrapper: calls `ruby_decl.lower_ruby_method(ctx, node, inject_self=False)`.

### `ruby_expr.lower_ruby_params(ctx, params_node)`
Ruby-specific parameter lowering. Skips `(`, `)`, `,`, and `|` tokens. For each parameter, attempts direct `identifier` extraction, falls back to `_extract_param_name`. Emits `SYMBOLIC("param:name")` + `DECL_VAR`.

### `ruby_decl.lower_ruby_class(ctx, node)`
Lowers `class ClassName ... end`. Emits `BRANCH` past body, `LABEL`, body (with method bodies getting `inject_self=True`), end label, `CONST class:ref`, `DECL_VAR`. Extracts superclass from `superclass` child for class reference.

### `ruby_cf.lower_ruby_if(ctx, node)`
Lowers Ruby `if` statement with `elsif` support. Routes alternatives through `_lower_ruby_alternative` which handles `elsif`, `else`, and `else_clause` node types.

### `ruby_cf.lower_ruby_elsif_stmt(ctx, node)`
Fallback handler for `elsif` appearing as a top-level statement (unusual). Creates its own end label and delegates to `_lower_ruby_elsif`.

### `ruby_expr.lower_ruby_store_target(ctx, target, val_reg, parent_node)`
Ruby-specific store target handling:
- `"instance_variable"` -> `LOAD_VAR "self"` + `STORE_FIELD` (strips `@` prefix)
- `"identifier"`, `"constant"`, `"global_variable"`, `"class_variable"` -> `STORE_VAR`
- `"element_reference"` -> `STORE_INDEX` (extracts object and index from named children)
- Fallback -> delegates to `common_expr.lower_store_target`

### `ruby_assign.lower_ruby_assignment(ctx, node)`
Lowers Ruby `assignment` using `ruby_expr.lower_ruby_store_target` for the LHS.

### `ruby_assign.lower_ruby_augmented_assignment(ctx, node)`
Lowers Ruby `operator_assignment` (`x += 1`). Extracts operator, emits `BINOP`, stores via `ruby_expr.lower_ruby_store_target`.

### `ruby_expr.lower_ruby_hash(ctx, node) -> str`
Lowers Ruby hash literals `{key => value, ...}`. Emits `NEW_OBJECT("hash")`, then for each `pair` child, lowers key and value and emits `STORE_INDEX`.

### `ruby_cf.lower_begin(ctx, node)`
Lowers `begin ... rescue ... else ... ensure ... end`. Handles the structural complexity of Ruby's exception handling:
1. Detects a `body_statement` wrapper (if present) and uses it as the container.
2. Collects body children, `rescue` clauses, `ensure` node (finally), and `else` node.
3. For each `rescue`, extracts the exception type from `exceptions` child and exception variable from `exception_variable` child.
4. Delegates to `_lower_try_catch_ruby`.

### `ruby_expr.lower_ruby_block(ctx, node) -> str`
Lowers a Ruby `block` (`{ |params| body }`) or `do_block` (`do |params| body end`) as an inline closure. Emits `BRANCH` past the body, `LABEL`, optional `block_parameters` via `ruby_expr.lower_ruby_params`, body (from `block_body` or `body_statement` child, or inline named children), implicit `RETURN "None"`, end label, and returns a register holding `"func:block_label"`.

### `ruby_expr.lower_ruby_range(ctx, node) -> str`
Lowers `a..b` or `a...b` as `CALL_FUNCTION("range", start_reg, end_reg)`.

### `ruby_expr.lower_ruby_lambda(ctx, node) -> str`
Lowers `-> (params) { body }`. Generates name `__lambda_N`, emits function body between labels (with optional `lambda_parameters` or `block_parameters`), returns register holding `func:ref`.

### `ruby_expr.lower_ruby_word_array(ctx, node) -> str`
Lowers `%w[a b c]` (string array) and `%i[a b c]` (symbol array). Emits `NEW_ARRAY("list", size)`, then for each element, emits `CONST` with the element text and `STORE_INDEX`.

### `ruby_cf.lower_case(ctx, node)`
Lowers `case expr; when val; ...; else; ...; end` as an if/else chain. For each `when` clause:
1. Extracts the pattern (from `pattern` child or first named child).
2. If a case value exists, compares with `BINOP("==")`.
3. Emits `BRANCH_IF` to body or next case.
4. After all `when` clauses, lowers the `else` clause if present.

### `ruby_decl.lower_ruby_module(ctx, node)`
Lowers `module Name ... end` identically to a class: `BRANCH` past body, `LABEL`, body, end label, `CONST class:ref`, `DECL_VAR`. Uses `CLASS_LABEL_PREFIX` and `CLASS_REF_TEMPLATE` for naming.

### `ruby_cf.lower_ruby_if_modifier(ctx, node)`
Lowers `body if condition` (modifier form). Extracts first two named children as `body_node` and `cond_node`, evaluates condition, emits `BRANCH_IF` to body or end, lowers body on true branch.

### `ruby_cf.lower_ruby_unless_modifier(ctx, node)`
Lowers `body unless condition`. Like `lower_ruby_if_modifier` but negates the condition with `UNOP("!")` first.

### `ruby_cf.lower_ruby_while_modifier(ctx, node)`
Lowers `body while condition` (modifier form). Creates a loop: evaluates condition at top, `BRANCH_IF` to body or end, lowers body, branches back to condition.

### `ruby_cf.lower_ruby_until_modifier(ctx, node)`
Lowers `body until condition`. Like `lower_ruby_while_modifier` but negates the condition with `UNOP("!")`.

### `ruby_expr.lower_ruby_conditional(ctx, node) -> str`
Lowers Ruby's ternary `condition ? true_expr : false_expr`. Uses a temporary variable `__ternary_N` to merge the two branches:
1. Evaluates condition, emits `BRANCH_IF`.
2. True branch: lowers true expression, stores to `__ternary_N`.
3. False branch: lowers false expression, stores to `__ternary_N`.
4. End label: loads `__ternary_N` into result register.

### `ruby_expr.lower_ruby_self(ctx, node) -> str`
Lowers `self` as `LOAD_VAR("self")`.

### `ruby_expr.lower_ruby_super(ctx, node) -> str`
Lowers `super` or `super(args)` as `CALL_FUNCTION("super", ...args)`.

### `ruby_expr.lower_ruby_yield(ctx, node) -> str`
Lowers `yield` or `yield expr` as `CALL_FUNCTION("yield", ...args)`.

### `ruby_expr.lower_ruby_pattern(ctx, node) -> str`
Lowers a `pattern` wrapper node by lowering its inner child.

### `ruby_decl.lower_ruby_singleton_class(ctx, node)`
Lowers `class << obj ... end`. Emits `BRANCH` past body, `LABEL`, evaluates the `value` expression (the object), lowers the body, end label. Does not emit a `STORE_VAR` (the singleton class is anonymous).

### `ruby_decl.lower_ruby_singleton_method(ctx, node)`
Lowers `def obj.method_name(params) ... end`. Like `lower_ruby_method` but constructs the function name as `"object_name.method_name"` (e.g., `"self.class_method"`).

### `ruby_cf.lower_ruby_in_clause(ctx, node)`
Lowers `in pattern then body` clause -- treated as a when-like arm in `case/in` pattern matching.

### `ruby_cf.lower_ruby_retry(ctx, node)`
Lowers `retry` as `CALL_FUNCTION("retry")`.

## Canonical Literal Handling

| Ruby Node Type | Handler | Emitted IR |
|---|---|---|
| `"nil"` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `"true"` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `"false"` | `common_expr.lower_canonical_false` | `CONST "False"` |

Ruby's `nil`, `true`, and `false` are mapped to the Python-canonical forms in the IR.

## Example

**Ruby source:**
```ruby
class Calculator
  def add(a, b)
    a + b
  end
end

calc = Calculator.new
result = calc.add(1, 2)
puts result unless result.nil?
```

**Emitted IR (simplified):**
```
LABEL         ENTRY
BRANCH        end_class_Calculator_0
LABEL         class_Calculator_0
BRANCH        end_add_1
LABEL         func_add_1
SYMBOLIC      %0  "param:a"
STORE_VAR     a  %0
SYMBOLIC      %1  "param:b"
STORE_VAR     b  %1
LOAD_VAR      %2  a
LOAD_VAR      %3  b
BINOP         %4  "+"  %2  %3
CONST         %5  "None"
RETURN        %5
LABEL         end_add_1
CONST         %6  "func:add@func_add_1"
STORE_VAR     add  %6
LABEL         end_class_Calculator_0
CONST         %7  "class:Calculator@class_Calculator_0"
STORE_VAR     Calculator  %7
LOAD_VAR      %8  Calculator
CALL_METHOD   %9  %8  new
STORE_VAR     calc  %9
LOAD_VAR      %10 calc
CALL_METHOD   %11 %10  add  ...
STORE_VAR     result  %11
# unless modifier: negate condition, branch
LOAD_VAR      %12 result
CALL_METHOD   %13 %12  nil?
UNOP          %14 "!"  %13
BRANCH_IF     %14  unlessmod_true_N,unlessmod_end_N
LABEL         unlessmod_true_N
LOAD_VAR      %15 result
CALL_FUNCTION %16 puts  %15
BRANCH        unlessmod_end_N
LABEL         unlessmod_end_N
```

## Design Notes

1. **`call` as both attribute and method node** -- Ruby's tree-sitter grammar uses `call` as the node type for both `obj.method(args)` and `method(args)`. The `attribute_node_type = "call"` constant reflects this. The `ruby_expr.lower_ruby_call` handler disambiguates based on the presence of a `receiver` field.

2. **Modifier-form control flow** -- Ruby's `body if cond`, `body unless cond`, `body while cond`, and `body until cond` forms are handled by separate handlers (`ruby_cf.lower_ruby_if_modifier`, etc.) because the AST node types (`if_modifier`, `unless_modifier`, etc.) differ from their block-form counterparts.

3. **Block/do_block as closures** -- Ruby blocks (`{ |x| ... }` and `do |x| ... end`) are lowered as inline anonymous functions and passed as additional arguments to the enclosing method call. This is handled in `ruby_expr.lower_ruby_call` which detects `block`/`do_block` children.

   **Scoping model**: Ruby does NOT use `BLOCK_SCOPED = True` (no LLVM-style name mangling). Instead, lambdas and blocks get variable isolation through the VM's call-frame mechanism — each is emitted as an inline function (`BRANCH` → `LABEL` → params → body → `RETURN` → `LABEL end`), and the VM creates a new call frame when invoking them via `CALL_FUNCTION` / `CALL_METHOD`. This means block/lambda parameters naturally shadow outer variables without `$` mangling. In contrast, `for..in` is lowered inline (no function boundary, no `RETURN`), so its loop variable intentionally leaks to the enclosing scope — matching Ruby's real semantics where `for` does not create a new scope but blocks do.

4. **`unless` and `until` via negation** -- Rather than special IR opcodes, `unless` is lowered as `UNOP("!") + BRANCH_IF` (i.e., inverted `if`), and `until` as `UNOP("!") + BRANCH_IF` (inverted `while`).

5. **begin/rescue uses custom try/catch lowering** -- `_lower_try_catch_ruby` in `control_flow.py` accepts a list of body children rather than a single body node, because Ruby's `begin` block can have interleaved children. Default exception type is `"StandardError"` (not `"Exception"`).

6. **Ruby-specific store target** -- `ruby_expr.lower_ruby_store_target` handles Ruby-specific variable types (`instance_variable` via `LOAD_VAR "self"` + `STORE_FIELD`, `constant`, `global_variable`, `class_variable`) and `element_reference` for indexed assignment (`arr[idx] = val`). Falls back to the common store target for other types.

7. **`next` mapped to `common_cf.lower_continue`** -- Ruby's `next` keyword (skip to next iteration) is mapped to the common `lower_continue`.

8. **Module as class** -- Ruby modules are lowered with the same pattern as classes, using `CLASS_LABEL_PREFIX` and `CLASS_REF_TEMPLATE`. The IR does not distinguish modules from classes.

9. **Ternary uses synthetic variable** -- The ternary `? :` lowering stores both branch results to a synthetic `__ternary_N` variable and loads it afterward, providing a single result register across the merge point.

10. **Instance variable access** -- `@var` is lowered as `LOAD_VAR "self"` + `LOAD_FIELD "var"` (not `LOAD_VAR "@var"`). Assignment to `@var` is lowered as `LOAD_VAR "self"` + `STORE_FIELD "var"`.

11. **String interpolation** -- `"Hello #{name}"` is decomposed into `CONST` fragments and interpolated expression registers, concatenated with `BINOP "+"`.

12. **Separate assignments module** -- Ruby has an extra `assignments.py` module (beyond the standard `expressions.py`, `control_flow.py`, `declarations.py`) that handles `lower_ruby_return`, `lower_ruby_assignment`, and `lower_ruby_augmented_assignment`.

13. **Constructor lowering** -- `Class.new(args)` is special-cased in `ruby_expr.lower_ruby_call` to emit `NEW_OBJECT(ClassName)` + `CALL_METHOD("__init__", ...)`, and methods named `initialize` within class bodies are renamed to `__init__` via the `inject_self=True` flag.

14. **Implicit return** -- `ruby_decl._lower_body_with_implicit_return` treats the last expression in a method body as an implicit return value, matching Ruby semantics.

15. **`RubyNodeType` constants** -- All tree-sitter node type strings are centralised in `node_types.py` as `RubyNodeType` class attributes, so typos are caught at import time and grep/refactor is trivial.
