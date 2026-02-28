# Ruby Frontend

> `interpreter/frontends/ruby.py` -- Extends `BaseFrontend` -- 1151 lines

## Overview

The Ruby frontend lowers tree-sitter Ruby ASTs into the RedDragon flattened TAC IR. It handles Ruby-specific constructs including `unless` (inverted if), `until` (inverted while), modifier-form control flow (`body if cond`, `body unless cond`, `body while cond`, `body until cond`), `begin/rescue/else/ensure` exception handling, blocks and do-blocks as closures, lambdas, `case/when` pattern matching, modules, singleton classes (`class << obj`), singleton methods (`def self.method`), symbols, ranges, word arrays (`%w[]`), symbol arrays (`%i[]`), heredocs, element references (`arr[idx]`), the ternary operator, and the `self` keyword.

Ruby's tree-sitter grammar uses `call` as both the attribute access node type and the method invocation node type, which is reflected in the `ATTRIBUTE_NODE_TYPE = "call"` override.

## Class Hierarchy

```
Frontend (ABC)
  +-- BaseFrontend
        +-- RubyFrontend
```

`RubyFrontend` extends `BaseFrontend` directly. No other frontend extends `RubyFrontend`.

## Overridden Constants

| Constant | BaseFrontend Default | RubyFrontend Value | Notes |
|---|---|---|---|
| `ATTRIBUTE_NODE_TYPE` | `"attribute"` | `"call"` | Ruby uses `call` nodes for `obj.method` |
| `ATTR_OBJECT_FIELD` | `"object"` | `"receiver"` | tree-sitter Ruby names the LHS `receiver` |
| `ATTR_ATTRIBUTE_FIELD` | `"attribute"` | `"method"` | tree-sitter Ruby names the RHS `method` |
| `COMMENT_TYPES` | `frozenset({"comment"})` | `frozenset({"comment"})` | Same as base |
| `NOISE_TYPES` | `frozenset({"newline", "\n"})` | `frozenset({"then", "do", "end", "\n"})` | Skips Ruby block delimiters |

All other constants retain their `BaseFrontend` defaults (`NONE_LITERAL = "None"`, `TRUE_LITERAL = "True"`, `FALSE_LITERAL = "False"`, `DEFAULT_RETURN_VALUE = "None"`, etc.).

## Expression Dispatch Table

| AST Node Type | Handler Method | Emitted IR |
|---|---|---|
| `"identifier"` | `_lower_identifier` | `LOAD_VAR` |
| `"instance_variable"` | `_lower_identifier` | `LOAD_VAR` (e.g., `@name`) |
| `"constant"` | `_lower_identifier` | `LOAD_VAR` (e.g., `MyClass`) |
| `"integer"` | `_lower_const_literal` | `CONST` (raw text) |
| `"float"` | `_lower_const_literal` | `CONST` (raw text) |
| `"string"` | `_lower_const_literal` | `CONST` (raw text) |
| `"true"` | `_lower_canonical_true` | `CONST "True"` |
| `"false"` | `_lower_canonical_false` | `CONST "False"` |
| `"nil"` | `_lower_canonical_none` | `CONST "None"` |
| `"binary"` | `_lower_binop` | `BINOP` |
| `"unary"` | `_lower_unop` | `UNOP` |
| `"call"` | `_lower_ruby_call` | `CALL_METHOD` / `CALL_FUNCTION` / `CALL_UNKNOWN` |
| `"parenthesized_expression"` | `_lower_paren` | (unwraps inner expression) |
| `"array"` | `_lower_list_literal` | `NEW_ARRAY` + `STORE_INDEX` |
| `"hash"` | `_lower_ruby_hash` | `NEW_OBJECT("hash")` + `STORE_INDEX` |
| `"argument_list"` | `_lower_ruby_argument_list` | (unwraps to first named child) |
| `"simple_symbol"` | `_lower_const_literal` | `CONST` (e.g., `:name`) |
| `"range"` | `_lower_ruby_range` | `CALL_FUNCTION("range", start, end)` |
| `"regex"` | `_lower_const_literal` | `CONST` (raw text) |
| `"lambda"` | `_lower_ruby_lambda` | `BRANCH` + `LABEL` + params + body + `RETURN` + `CONST func:ref` |
| `"string_array"` | `_lower_ruby_word_array` | `NEW_ARRAY` + `CONST` + `STORE_INDEX` per element |
| `"symbol_array"` | `_lower_ruby_word_array` | `NEW_ARRAY` + `CONST` + `STORE_INDEX` per element |
| `"global_variable"` | `_lower_identifier` | `LOAD_VAR` (e.g., `$stdout`) |
| `"class_variable"` | `_lower_identifier` | `LOAD_VAR` (e.g., `@@count`) |
| `"heredoc_body"` | `_lower_const_literal` | `CONST` (raw text) |
| `"element_reference"` | `_lower_element_reference` | `LOAD_INDEX` |
| `"conditional"` | `_lower_ruby_conditional` | `BRANCH_IF` + `STORE_VAR` + `LOAD_VAR` (ternary) |
| `"self"` | `_lower_ruby_self` | `LOAD_VAR("self")` |

**28 entries total.** (Note: `"conditional"`, `"unary"`, and `"self"` are added via direct dictionary assignment after the initial dict literal.)

## Statement Dispatch Table

| AST Node Type | Handler Method | Emitted IR |
|---|---|---|
| `"expression_statement"` | `_lower_expression_statement` | (unwraps inner expression) |
| `"assignment"` | `_lower_assignment` | `STORE_VAR` / `STORE_FIELD` / `STORE_INDEX` |
| `"operator_assignment"` | `_lower_augmented_assignment` | `BINOP` + store |
| `"return"` | `_lower_ruby_return` | `RETURN` |
| `"return_statement"` | `_lower_ruby_return` | `RETURN` (alternate node type) |
| `"if"` | `_lower_if` | `BRANCH_IF` + `LABEL` + `BRANCH` |
| `"if_modifier"` | `_lower_ruby_if_modifier` | `BRANCH_IF` + body + `BRANCH` |
| `"unless"` | `_lower_unless` | `UNOP("!")` + `BRANCH_IF` + `LABEL` + `BRANCH` |
| `"unless_modifier"` | `_lower_ruby_unless_modifier` | `UNOP("!")` + `BRANCH_IF` + body + `BRANCH` |
| `"elsif"` | `_lower_ruby_elsif_stmt` | `BRANCH_IF` + `LABEL` + `BRANCH` (standalone fallback) |
| `"while"` | `_lower_while` | Loop with `BRANCH_IF` |
| `"while_modifier"` | `_lower_ruby_while_modifier` | Modifier-form loop |
| `"until"` | `_lower_until` | Inverted loop with `UNOP("!")` + `BRANCH_IF` |
| `"until_modifier"` | `_lower_ruby_until_modifier` | Inverted modifier-form loop |
| `"for"` | `_lower_ruby_for` | Index-based iteration loop |
| `"method"` | `_lower_ruby_method` | `BRANCH` + `LABEL` + params + body + `RETURN` + `STORE_VAR` |
| `"singleton_method"` | `_lower_ruby_singleton_method` | Same as method but with `object.method` naming |
| `"class"` | `_lower_ruby_class` | `BRANCH` + `LABEL` + body + `CONST class:ref` + `STORE_VAR` |
| `"singleton_class"` | `_lower_ruby_singleton_class` | `BRANCH` + `LABEL` + body + `LABEL` |
| `"program"` | `_lower_block` | Top-level block lowering |
| `"body_statement"` | `_lower_block` | Ruby body block lowering |
| `"do_block"` | `_lower_symbolic_block` | Closure lowering (delegates to `_lower_ruby_block`) |
| `"block"` | `_lower_symbolic_block` | Closure lowering (delegates to `_lower_ruby_block`) |
| `"break"` | `_lower_break` | `BRANCH` to break target |
| `"next"` | `_lower_continue` | `BRANCH` to continue label |
| `"begin"` | `_lower_begin` | `begin/rescue/else/ensure` exception handling |
| `"case"` | `_lower_case` | `case/when` as if/else chain |
| `"module"` | `_lower_ruby_module` | Module as class-like structure |

**27 entries total.**

## Language-Specific Lowering Methods

### `_lower_element_reference(node) -> str`
Lowers `arr[idx]` (Ruby `element_reference` node type) as `LOAD_INDEX`. Extracts the first two named children as the object and index respectively.

### `_lower_ruby_argument_list(node) -> str`
Unwraps an `argument_list` node to its first named child. Used when `argument_list` appears in expression context (e.g., bare `return value` without parentheses). Falls back to `CONST "None"`.

### `_lower_ruby_call(node) -> str`
Lowers Ruby `call` nodes. Three paths:
1. **Method call with receiver**: `receiver.method(args)` -- emits `CALL_METHOD`. Also detects `block`/`do_block` children and appends the lowered block closure as an extra argument.
2. **Standalone function call**: `method(args)` (no receiver) -- emits `CALL_FUNCTION`.
3. **Fallback**: unknown call target -- emits `SYMBOLIC("unknown_call_target")` + `CALL_UNKNOWN`.

Block/do_block detection is critical: `arr.each do |x| ... end` passes the block as an additional argument to `CALL_METHOD`.

### `_lower_ruby_return(node)`
Lowers `return expr`. Filters out both `"return"` and `"return_statement"` tokens from children. Handles bare `return` by emitting `CONST "None"` + `RETURN`.

### `_lower_unless(node)`
Lowers `unless cond ... else ... end`. Negates the condition with `UNOP("!")`, then follows the standard if pattern with `BRANCH_IF` on the negated register. Supports an alternative (else) branch.

### `_lower_until(node)`
Lowers `until cond ... end`. Loop that negates the condition each iteration with `UNOP("!")`. Continues while the condition is false (i.e., the negation is true).

### `_lower_ruby_for(node)`
Lowers `for var in collection ... end`. Implements as index-based iteration: initializes idx to 0, computes `len(collection)`, branches on `idx < len`, loads element via `LOAD_INDEX`, stores to the loop variable, executes body, increments.

### `_lower_ruby_method(node)`
Lowers `def method_name(params) ... end`. Standard function lowering pattern: `BRANCH` past body, `LABEL`, params via `_lower_ruby_params`, body, implicit `RETURN "None"`, end label, `CONST func:ref`, `STORE_VAR`.

### `_lower_ruby_params(params_node)`
Ruby-specific parameter lowering. Skips `(`, `)`, `,`, and `|` tokens. For each parameter, attempts direct `identifier` extraction, falls back to `_extract_param_name`. Emits `SYMBOLIC("param:name")` + `STORE_VAR`.

### `_lower_ruby_class(node)`
Lowers `class ClassName ... end`. Emits `BRANCH` past body, `LABEL`, body, end label, `CONST class:ref`, `STORE_VAR`.

### `_lower_alternative(alt_node, end_label)`
**Overrides `BaseFrontend._lower_alternative`.** Routes `"elsif"` nodes to `_lower_ruby_elsif`, `"else"`/`"else_clause"` to inline statement lowering, and everything else to `_lower_block`.

### `_lower_ruby_elsif(node, end_label)`
Lowers Ruby's `elsif` clause. Evaluates the condition, emits `BRANCH_IF`, lowers the body on the true branch, and recursively handles further alternatives.

### `_lower_ruby_elsif_stmt(node)`
Fallback handler for `elsif` appearing as a top-level statement (unusual). Creates its own end label and delegates to `_lower_ruby_elsif`.

### `_lower_ruby_alternative(alt_node, end_label)`
Thin wrapper that delegates to `_lower_alternative`.

### `_lower_store_target(target, val_reg, parent_node)`
**Overrides `BaseFrontend._lower_store_target`.** Handles Ruby-specific store targets:
- `"identifier"`, `"instance_variable"`, `"constant"`, `"global_variable"`, `"class_variable"` -> `STORE_VAR`
- `"element_reference"` -> `STORE_INDEX` (extracts object and index from named children)
- Anything else -> delegates to `super()._lower_store_target`

### `_lower_ruby_hash(node) -> str`
Lowers Ruby hash literals `{key => value, ...}`. Emits `NEW_OBJECT("hash")`, then for each `pair` child, lowers key and value and emits `STORE_INDEX`.

### `_lower_begin(node)`
Lowers `begin ... rescue ... else ... ensure ... end`. Handles the structural complexity of Ruby's exception handling:
1. Detects a `body_statement` wrapper (if present) and uses it as the container.
2. Collects body children, `rescue` clauses, `ensure` node (finally), and `else` node.
3. For each `rescue`, extracts the exception type from `exceptions` child and exception variable from `exception_variable` child.
4. Delegates to `_lower_try_catch_ruby`.

### `_lower_try_catch_ruby(node, body_children, catch_clauses, finally_node, else_node)`
Ruby-specific try/catch lowering. Unlike the base class `_lower_try_catch` which takes a single body node, this method takes a **list of body children** and lowers them inline. For each rescue clause, uses `"StandardError"` as the default exception type (vs. base class `"Exception"`).

### `_lower_ruby_block(node) -> str`
Lowers a Ruby `block` (`{ |params| body }`) or `do_block` (`do |params| body end`) as an inline closure. Emits `BRANCH` past the body, `LABEL`, optional `block_parameters` via `_lower_ruby_params`, body (from `block_body` or `body_statement` child, or inline named children), implicit `RETURN "None"`, end label, and returns a register holding `"func:block_label"`.

### `_lower_symbolic_block(node)`
Statement-level handler for `block`/`do_block`. Delegates to `_lower_ruby_block` (discards the returned register).

### `_lower_ruby_range(node) -> str`
Lowers `a..b` or `a...b` as `CALL_FUNCTION("range", start_reg, end_reg)`.

### `_lower_ruby_lambda(node) -> str`
Lowers `-> (params) { body }`. Generates name `__lambda_N`, emits function body between labels (with optional `lambda_parameters` or `block_parameters`), returns register holding `func:ref`.

### `_lower_ruby_word_array(node) -> str`
Lowers `%w[a b c]` (string array) and `%i[a b c]` (symbol array). Emits `NEW_ARRAY("list", size)`, then for each element, emits `CONST` with the element text and `STORE_INDEX`.

### `_lower_case(node)`
Lowers `case expr; when val; ...; else; ...; end` as an if/else chain. For each `when` clause:
1. Extracts the pattern (from `pattern` child or first named child).
2. If a case value exists, compares with `BINOP("==")`.
3. Emits `BRANCH_IF` to body or next case.
4. After all `when` clauses, lowers the `else` clause if present.

### `_lower_ruby_module(node)`
Lowers `module Name ... end` identically to a class: `BRANCH` past body, `LABEL`, body, end label, `CONST class:ref`, `STORE_VAR`. Uses `CLASS_LABEL_PREFIX` and `CLASS_REF_TEMPLATE` for naming.

### `_lower_ruby_if_modifier(node)`
Lowers `body if condition` (modifier form). Extracts first two named children as `body_node` and `cond_node`, evaluates condition, emits `BRANCH_IF` to body or end, lowers body on true branch.

### `_lower_ruby_unless_modifier(node)`
Lowers `body unless condition`. Like `_lower_ruby_if_modifier` but negates the condition with `UNOP("!")` first.

### `_lower_ruby_while_modifier(node)`
Lowers `body while condition` (modifier form). Creates a loop: evaluates condition at top, `BRANCH_IF` to body or end, lowers body, branches back to condition.

### `_lower_ruby_until_modifier(node)`
Lowers `body until condition`. Like `_lower_ruby_while_modifier` but negates the condition with `UNOP("!")`.

### `_lower_ruby_conditional(node) -> str`
Lowers Ruby's ternary `condition ? true_expr : false_expr`. Uses a temporary variable `__ternary_N` to merge the two branches:
1. Evaluates condition, emits `BRANCH_IF`.
2. True branch: lowers true expression, stores to `__ternary_N`.
3. False branch: lowers false expression, stores to `__ternary_N`.
4. End label: loads `__ternary_N` into result register.

### `_lower_ruby_self(node) -> str`
Lowers `self` as `LOAD_VAR("self")`.

### `_lower_ruby_singleton_class(node)`
Lowers `class << obj ... end`. Emits `BRANCH` past body, `LABEL`, evaluates the `value` expression (the object), lowers the body, end label. Does not emit a `STORE_VAR` (the singleton class is anonymous).

### `_lower_ruby_singleton_method(node)`
Lowers `def obj.method_name(params) ... end`. Like `_lower_ruby_method` but constructs the function name as `"object_name.method_name"` (e.g., `"self.class_method"`).

## Canonical Literal Handling

| Ruby Node Type | Canonical Method | Emitted IR |
|---|---|---|
| `"nil"` | `_lower_canonical_none` | `CONST "None"` |
| `"true"` | `_lower_canonical_true` | `CONST "True"` |
| `"false"` | `_lower_canonical_false` | `CONST "False"` |

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

1. **`call` as both attribute and method node** -- Ruby's tree-sitter grammar uses `call` as the node type for both `obj.method(args)` and `method(args)`. The `ATTRIBUTE_NODE_TYPE = "call"` override reflects this. The `_lower_ruby_call` handler disambiguates based on the presence of a `receiver` field.

2. **Modifier-form control flow** -- Ruby's `body if cond`, `body unless cond`, `body while cond`, and `body until cond` forms are handled by separate handlers (`_lower_ruby_if_modifier`, etc.) because the AST node types (`if_modifier`, `unless_modifier`, etc.) differ from their block-form counterparts.

3. **Block/do_block as closures** -- Ruby blocks (`{ |x| ... }` and `do |x| ... end`) are lowered as inline anonymous functions and passed as additional arguments to the enclosing method call. This is handled in `_lower_ruby_call` which detects `block`/`do_block` children.

4. **`unless` and `until` via negation** -- Rather than special IR opcodes, `unless` is lowered as `UNOP("!") + BRANCH_IF` (i.e., inverted `if`), and `until` as `UNOP("!") + BRANCH_IF` (inverted `while`).

5. **begin/rescue uses custom try/catch lowering** -- `_lower_try_catch_ruby` accepts a list of body children rather than a single body node, because Ruby's `begin` block can have interleaved children. Default exception type is `"StandardError"` (not `"Exception"`).

6. **Overridden `_lower_store_target`** -- Handles Ruby-specific variable types (`instance_variable`, `constant`, `global_variable`, `class_variable`) and `element_reference` for indexed assignment (`arr[idx] = val`). Falls back to the base class for other target types.

7. **`next` mapped to `_lower_continue`** -- Ruby's `next` keyword (skip to next iteration) is mapped to the base class `_lower_continue`.

8. **Module as class** -- Ruby modules are lowered with the same pattern as classes, using `CLASS_LABEL_PREFIX` and `CLASS_REF_TEMPLATE`. The IR does not distinguish modules from classes.

9. **Ternary uses synthetic variable** -- The ternary `? :` lowering stores both branch results to a synthetic `__ternary_N` variable and loads it afterward, providing a single result register across the merge point.
