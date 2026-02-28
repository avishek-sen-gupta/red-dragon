# Base Frontend

> `interpreter/frontends/_base.py` -- 985 lines

## Overview

`BaseFrontend` is the language-agnostic lowering engine that all 15 deterministic tree-sitter frontends inherit from. It provides:

- Two dispatch tables (`_STMT_DISPATCH`, `_EXPR_DISPATCH`) that subclasses populate with language-specific node type mappings
- Overridable class-level constants for tree-sitter field names and literal tokens
- A library of ~30 reusable expression and statement lowering methods
- Code generation primitives: SSA-style register allocation, label generation, instruction emission with automatic source location tracking
- Loop context management (break/continue target stacks)

The base class itself produces no dispatch entries. Subclasses wire up their grammar's node types to the provided handler methods in their `__init__`.

---

## Class Structure

### Inheritance

```
Frontend (ABC)                     # interpreter/frontend.py
  |
  +-- BaseFrontend                 # interpreter/frontends/_base.py
        |
        +-- PythonFrontend         # and 14 other language subclasses
```

`Frontend` defines a single abstract method:

```python
class Frontend(ABC):
    @abstractmethod
    def lower(self, tree, source: bytes) -> list[IRInstruction]: ...
```

`BaseFrontend` implements `lower()` and provides the full lowering infrastructure.

### Constructor (`__init__`)

```python
def __init__(self):
    self._reg_counter: int = 0
    self._label_counter: int = 0
    self._instructions: list[IRInstruction] = []
    self._source: bytes = b""
    self._loop_stack: list[dict[str, str]] = []
    self._break_target_stack: list[str] = []
    self._STMT_DISPATCH: dict[str, Callable] = {}
    self._EXPR_DISPATCH: dict[str, Callable] = {}
```

| Attribute | Type | Purpose |
|---|---|---|
| `_reg_counter` | `int` | Monotonic counter for SSA register names (`%0`, `%1`, ...) |
| `_label_counter` | `int` | Monotonic counter for label names (`L_0`, `if_true_1`, ...) |
| `_instructions` | `list[IRInstruction]` | Accumulator for emitted IR instructions |
| `_source` | `bytes` | Raw source code bytes, used for extracting node text |
| `_loop_stack` | `list[dict[str, str]]` | Stack of `{"continue_label": str, "end_label": str}` for nested loops |
| `_break_target_stack` | `list[str]` | Stack of break target labels (parallels `_loop_stack` but also used for switch statements) |
| `_STMT_DISPATCH` | `dict[str, Callable]` | Maps tree-sitter statement node types to handler methods |
| `_EXPR_DISPATCH` | `dict[str, Callable]` | Maps tree-sitter expression node types to handler methods |

All mutable state is reset at the start of each `lower()` call, making instances reusable across multiple files.

---

## Overridable Constants

These class-level attributes allow subclasses to adapt the shared lowering logic to different tree-sitter grammars without overriding methods. Each constant is shown with its default value and the methods that reference it.

### Function Definition Fields

```python
FUNC_NAME_FIELD: str = "name"           # Used by _lower_function_def
FUNC_PARAMS_FIELD: str = "parameters"   # Used by _lower_function_def
FUNC_BODY_FIELD: str = "body"           # Used by _lower_function_def
```

These map to `node.child_by_field_name(...)` calls when lowering function definitions. Most grammars use these defaults; Kotlin uses `"type_parameters"` for generics extraction, etc.

### If Statement Fields

```python
IF_CONDITION_FIELD: str = "condition"      # Used by _lower_if, _lower_elif
IF_CONSEQUENCE_FIELD: str = "consequence"  # Used by _lower_if, _lower_elif
IF_ALTERNATIVE_FIELD: str = "alternative"  # Used by _lower_if, _lower_elif
```

### While Loop Fields

```python
WHILE_CONDITION_FIELD: str = "condition"   # Used by _lower_while
WHILE_BODY_FIELD: str = "body"             # Used by _lower_while
```

### Call Expression Fields

```python
CALL_FUNCTION_FIELD: str = "function"      # Used by _lower_call
CALL_ARGUMENTS_FIELD: str = "arguments"    # Used by _lower_call
```

### Class Definition Fields

```python
CLASS_NAME_FIELD: str = "name"             # Used by _lower_class_def
CLASS_BODY_FIELD: str = "body"             # Used by _lower_class_def
```

### Attribute Access Fields

```python
ATTR_OBJECT_FIELD: str = "object"          # Used by _lower_attribute, _lower_call_impl, _lower_store_target
ATTR_ATTRIBUTE_FIELD: str = "attribute"    # Used by _lower_attribute, _lower_call_impl, _lower_store_target
```

Languages like JavaScript override `ATTR_ATTRIBUTE_FIELD` to `"property"` to match their tree-sitter grammar.

### Subscript Fields

```python
SUBSCRIPT_VALUE_FIELD: str = "value"       # Used by _lower_subscript, _lower_store_target
SUBSCRIPT_INDEX_FIELD: str = "subscript"   # Used by _lower_subscript, _lower_store_target
```

### Assignment Fields

```python
ASSIGN_LEFT_FIELD: str = "left"            # Used by _lower_assignment, _lower_augmented_assignment
ASSIGN_RIGHT_FIELD: str = "right"          # Used by _lower_assignment, _lower_augmented_assignment
```

### Block Node Types

```python
BLOCK_NODE_TYPES: frozenset[str] = frozenset()
```

Set of node types that should be treated as block containers by `_lower_block`. Subclasses populate this with language-specific block types (e.g., `"block"`, `"compound_statement"`, `"statement_block"`).

### Canonical Literal Constants

```python
NONE_LITERAL: str = "None"                 # Canonical null/nil/undefined
TRUE_LITERAL: str = "True"                 # Canonical boolean true
FALSE_LITERAL: str = "False"               # Canonical boolean false
DEFAULT_RETURN_VALUE: str = "None"         # Implicit return value at end of functions
```

These are Python-form canonical values. All frontends emit these same strings in the IR regardless of the source language's syntax. For example, JavaScript's `null`, `undefined`, Ruby's `nil`, Lua's `nil` all become `CONST "None"` in the IR.

`DEFAULT_RETURN_VALUE` is overridden by C (`"0"`) and Rust/Scala (`"()"`).

### Comment and Noise Types

```python
COMMENT_TYPES: frozenset[str] = frozenset({"comment"})
NOISE_TYPES: frozenset[str] = frozenset({"newline", "\n"})
```

Node types silently skipped by `_lower_stmt`. Subclasses extend these for language-specific comment styles (e.g., PHP adds `"text"` for inline HTML).

### Parenthesized Expression Type

```python
PAREN_EXPR_TYPE: str = "parenthesized_expression"
```

The node type for parenthesized expressions. Used by `_lower_paren` to unwrap.

### Attribute Node Type

```python
ATTRIBUTE_NODE_TYPE: str = "attribute"
```

The node type for attribute/member access. Python uses `"attribute"`, JavaScript uses `"member_expression"`. Referenced by `_lower_call_impl` and `_lower_store_target` to detect method calls and field stores.

---

## Expression Dispatch Table

`_EXPR_DISPATCH` is an empty `dict[str, Callable]` in `BaseFrontend.__init__`. Subclasses populate it with mappings from tree-sitter expression node types to handler methods.

**The base class provides no default entries.** All entries come from subclasses. However, the base class provides the handler methods that subclasses reference. A typical subclass populates the table like:

```python
# Example from a typical subclass __init__:
self._EXPR_DISPATCH = {
    "identifier":                    self._lower_identifier,
    "integer":                       self._lower_const_literal,
    "float":                         self._lower_const_literal,
    "string":                        self._lower_const_literal,
    "true":                          self._lower_canonical_true,
    "false":                         self._lower_canonical_false,
    "null":                          self._lower_canonical_none,
    "parenthesized_expression":      self._lower_paren,
    "binary_expression":             self._lower_binop,
    "unary_expression":              self._lower_unop,
    "call_expression":               self._lower_call,
    "member_expression":             self._lower_attribute,
    "subscript_expression":          self._lower_subscript,
    "assignment_expression":         self._lower_assignment,
    "augmented_assignment_expression": self._lower_augmented_assignment,
    "update_expression":             self._lower_update_expr,
    "array":                         self._lower_list_literal,
    "object":                        self._lower_dict_literal,
    # ... language-specific entries ...
}
```

When `_lower_expr(node)` is called:
1. Look up `node.type` in `_EXPR_DISPATCH`
2. If found, call the handler and return the result register
3. If not found, emit `SYMBOLIC "unsupported:<node.type>"` and return a new register

---

## Statement Dispatch Table

`_STMT_DISPATCH` is an empty `dict[str, Callable]` in `BaseFrontend.__init__`. Like the expression table, it has no default entries. Subclasses populate it with mappings like:

```python
# Example from a typical subclass __init__:
self._STMT_DISPATCH = {
    "expression_statement":          self._lower_expression_statement,
    "return_statement":              self._lower_return,
    "if_statement":                  self._lower_if,
    "while_statement":               self._lower_while,
    "for_statement":                 self._lower_c_style_for,
    "function_declaration":          self._lower_function_def,
    "class_declaration":             self._lower_class_def,
    "break_statement":               self._lower_break,
    "continue_statement":            self._lower_continue,
    "try_statement":                 self._lower_try_catch_wrapper,
    "throw_statement":               self._lower_raise_or_throw,
    "variable_declaration":          self._lower_var_declaration,
    # ... language-specific entries ...
}
```

When `_lower_stmt(node)` is called:
1. Skip if `node.type` is in `COMMENT_TYPES` or `NOISE_TYPES`
2. Look up `node.type` in `_STMT_DISPATCH`
3. If found, call the handler (no return value expected)
4. If not found, fall through to `_lower_expr(node)` (treats the node as an expression statement)

---

## Core Lowering Methods

### Entry Point: `lower(tree, source) -> list[IRInstruction]`

**Line 128.** The public entry point implementing the `Frontend` ABC.

```python
def lower(self, tree, source: bytes) -> list[IRInstruction]:
```

Behaviour:
1. Resets all mutable state (`_reg_counter`, `_label_counter`, `_instructions`, `_source`, `_loop_stack`, `_break_target_stack`)
2. Emits `LABEL "entry"` as the first instruction (using `constants.CFG_ENTRY_LABEL`)
3. Calls `_lower_block(tree.root_node)` to recursively lower the entire AST
4. Returns the accumulated instruction list

### Block Dispatch: `_lower_block(node)`

**Line 142.** Lowers a block of statements (module root, function body, if consequence, etc.).

Two-path logic:
- If `node.type` is in `_STMT_DISPATCH` **and** the handler is **not** `_lower_block` itself, dispatch directly. This handles cases where a single statement (e.g., `return_statement`) is used as the body of an `if` without being wrapped in a block node.
- Otherwise, iterate `node.children`, calling `_lower_stmt(child)` for each named child.

### Statement Dispatch: `_lower_stmt(node)`

**Line 162.** Dispatches a single statement node.

1. If `node.type` is in `COMMENT_TYPES` or `NOISE_TYPES`, return immediately (skip)
2. Look up handler in `_STMT_DISPATCH`; if found, call it
3. Fallback: call `_lower_expr(node)` (treats unknown statements as expression statements)

### Expression Dispatch: `_lower_expr(node) -> str`

**Line 173.** Dispatches a single expression node, returning the register holding its value.

1. Look up handler in `_EXPR_DISPATCH`; if found, call it and return the result register
2. Fallback: allocate a fresh register, emit `SYMBOLIC "unsupported:<node.type>"`, return the register

The SYMBOLIC fallback is a critical design decision: unknown constructs produce a descriptive placeholder rather than crashing, enabling graceful degradation.

### Function Definition: `_lower_function_def(node)`

**Line 702.** Lowers a function definition into IR.

Emits:
```
BRANCH end_<name>_N                        # Skip body in linear flow
LABEL func_<name>_M                        # Function entry point
  <parameter lowering>                     # SYMBOLIC "param:x" + STORE_VAR for each param
  <body lowering>                          # Recursive lowering of function body
  CONST "None" -> %R                       # Implicit return value
  RETURN %R                                # Implicit return at end
LABEL end_<name>_N                         # Resume linear flow
  CONST "<function:name@func_name_M>" -> %S  # Function reference constant
  STORE_VAR name %S                        # Bind function name to reference
```

Uses `constants.FUNC_LABEL_PREFIX` (`"func_"`) and `constants.FUNC_REF_TEMPLATE` (`"<function:{name}@{label}>"`) for label and reference generation.

### Parameter Lowering: `_lower_params(params_node)` / `_lower_param(child)` / `_extract_param_name(child)`

**Lines 739-778.** Lowers function parameters.

- `_lower_params` iterates children of the parameters node, calling `_lower_param` for each
- `_lower_param` skips punctuation (`(`, `)`, `,`, `:`, `->`), extracts the parameter name, then emits:
  ```
  %R = SYMBOLIC "param:<name>"
  STORE_VAR <name> %R
  ```
- `_extract_param_name` extracts the name from various parameter shapes:
  1. If the child is an `identifier`, use its text directly
  2. Try `child_by_field_name("name")` then `child_by_field_name("pattern")`
  3. Try finding the first `identifier` child
  4. Return `None` if no name can be extracted (parameter is skipped)

### Class Definition: `_lower_class_def(node)`

**Line 780.** Lowers a class definition into IR.

Emits:
```
BRANCH end_class_<name>_N                  # Skip class body in linear flow
LABEL class_<name>_M                       # Class entry point
  <body lowering>                          # Methods become nested function definitions
LABEL end_class_<name>_N                   # Resume linear flow
  CONST "<class:name@class_name_M>" -> %R  # Class reference constant
  STORE_VAR name %R                        # Bind class name to reference
```

Uses `constants.CLASS_LABEL_PREFIX` (`"class_"`), `constants.END_CLASS_LABEL_PREFIX` (`"end_class_"`), and `constants.CLASS_REF_TEMPLATE` (`"<class:{name}@{label}>"`) for label and reference generation.

### If/Elif/Else: `_lower_if(node)` / `_lower_alternative(alt_node, end_label)` / `_lower_elif(node, end_label)`

**Lines 515-590.** Lowers conditional branches.

`_lower_if` emits:
```
<condition lowering> -> %cond
BRANCH_IF %cond "if_true_N,if_false_M"    # (or if_true_N,if_end_K if no alternative)
LABEL if_true_N
  <consequence body>
  BRANCH if_end_K
LABEL if_false_M                           # (only if alternative exists)
  <alternative lowering>
  BRANCH if_end_K
LABEL if_end_K
```

`_lower_alternative` dispatches based on the alternative node type:
- `"elif_clause"` -> `_lower_elif` (chains another conditional)
- `"else_clause"` or `"else"` -> lower the body directly
- Anything else -> `_lower_block` (generic fallback)

`_lower_elif` follows the same pattern as `_lower_if` but reuses the parent's `end_label` for branch targets.

### While Loop: `_lower_while(node)`

**Line 638.** Lowers a while loop.

```
LABEL while_cond_N
  <condition lowering> -> %cond
  BRANCH_IF %cond "while_body_M,while_end_K"
LABEL while_body_M
  <body lowering>
  BRANCH while_cond_N
LABEL while_end_K
```

Pushes `{continue_label: while_cond_N, end_label: while_end_K}` onto the loop stack before lowering the body, pops after.

### C-Style For Loop: `_lower_c_style_for(node)`

**Line 663.** Lowers `for(init; cond; update)` loops (C, Java, JavaScript, etc.).

```
<init lowering>                            # Lowered as statement
LABEL for_cond_N
  <condition lowering> -> %cond            # (or unconditional BRANCH if no condition)
  BRANCH_IF %cond "for_body_M,for_end_K"
LABEL for_body_M
  <body lowering>
LABEL for_update_J                         # (only if update expression exists)
  <update lowering>
  BRANCH for_cond_N
LABEL for_end_K
```

The continue target is set to `for_update_J` (if an update expression exists) or `for_cond_N` (if no update), so `continue` correctly executes the update before re-checking the condition.

### Return Statement: `_lower_return(node)`

**Line 497.** Lowers a return statement.

- If the return has a value expression, lower it and emit `RETURN %val`
- If bare `return`, emit `CONST DEFAULT_RETURN_VALUE` then `RETURN`

Children are filtered by skipping the `"return"` keyword node.

### Assignment: `_lower_assignment(node)` / `_lower_augmented_assignment(node)`

**Lines 475-495.**

`_lower_assignment`:
1. Extract left and right via `ASSIGN_LEFT_FIELD` / `ASSIGN_RIGHT_FIELD`
2. Lower the right-hand side expression
3. Call `_lower_store_target(left, val_reg, node)` to emit the appropriate store

`_lower_augmented_assignment` (e.g., `x += 1`):
1. Extract left, right, and operator
2. Strip trailing `=` from the operator text (e.g., `"+="` -> `"+"`)
3. Lower both sides, emit `BINOP`, then store back to the left target

### Break and Continue: `_lower_break(node)` / `_lower_continue(node)`

**Lines 592-624.**

- `_lower_break`: emits `BRANCH` to the top of `_break_target_stack`. If outside any loop/switch, emits `SYMBOLIC "break_outside_loop_or_switch"`.
- `_lower_continue`: emits `BRANCH` to the `continue_label` from the top of `_loop_stack`. If outside any loop, emits `SYMBOLIC "continue_outside_loop"`.

### Raise/Throw: `_lower_raise_or_throw(node, keyword="raise")`

**Line 804.** Lowers raise/throw statements.

- If an expression follows the keyword, lower it and emit `THROW %val`
- If bare `raise`/`throw`, emit `CONST DEFAULT_RETURN_VALUE` then `THROW`

The `keyword` parameter allows subclasses to specify their language's keyword (e.g., `"throw"` for Java/JavaScript).

### Try/Catch/Finally: `_lower_try_catch(node, body_node, catch_clauses, finally_node, else_node)`

**Line 877.** Generic try/catch/finally lowering. Subclasses extract the language-specific clause structure and pass it as a list of catch dicts.

Each catch clause dict: `{"body": node, "variable": str | None, "type": str | None}`

Emits:
```
LABEL try_body_N
  <try body>
  BRANCH try_else_K (or exit_target)
LABEL catch_0_M                            # For each catch clause
  %R = SYMBOLIC "caught_exception:ExceptionType"
  STORE_VAR <variable> %R                  # (if variable is present)
  <catch body>
  BRANCH exit_target
LABEL try_else_J                           # (if else_node is present, Python/Ruby)
  <else body>
  BRANCH exit_target
LABEL try_finally_L                        # (if finally_node is present)
  <finally body>
LABEL try_end_P
```

`exit_target` is `try_finally_L` if a finally block exists, otherwise `try_end_P`.

### Expression Statement: `_lower_expression_statement(node)`

**Line 945.** Unwraps expression statement wrappers.

Iterates children looking for named nodes (skipping `;`). Dispatches the first found child via `_lower_stmt` rather than `_lower_expr`, so that expression-position statements (e.g., Rust's `while_expression`) are handled by their statement handlers.

### Variable Declaration: `_lower_var_declaration(node)`

**Line 960.** Lowers variable declarations with `variable_declarator` children (common in C-family languages).

For each `variable_declarator` child:
- If it has both `name` and `value` fields: lower the value, emit `STORE_VAR`
- If it has only `name` (no initializer): emit `CONST NONE_LITERAL`, then `STORE_VAR`

---

## Canonical Literal Handling

All frontends emit the same canonical Python-form strings for null, boolean, and other literal constants, regardless of the source language's syntax.

### Null/Nil/Undefined -> `CONST "None"`

`_lower_canonical_none(node)` (line 200):
```python
def _lower_canonical_none(self, node) -> str:
    reg = self._fresh_reg()
    self._emit(Opcode.CONST, result_reg=reg, operands=[self.NONE_LITERAL], node=node)
    return reg
```

Always emits `CONST "None"`. Subclasses map their null-like node types to this method:
- Python: `"none"` -> `_lower_canonical_none`
- JavaScript: `"null"`, `"undefined"` -> `_lower_canonical_none`
- Ruby: `"nil"` -> `_lower_canonical_none`
- Lua: `"nil"` -> `_lower_canonical_none`
- Java: `"null_literal"` -> `_lower_canonical_none`
- Go: `"nil"` -> `_lower_canonical_none`

### Boolean True -> `CONST "True"`

`_lower_canonical_true(node)` (line 208):
```python
def _lower_canonical_true(self, node) -> str:
    reg = self._fresh_reg()
    self._emit(Opcode.CONST, result_reg=reg, operands=[self.TRUE_LITERAL], node=node)
    return reg
```

### Boolean False -> `CONST "False"`

`_lower_canonical_false(node)` (line 216):
```python
def _lower_canonical_false(self, node) -> str:
    reg = self._fresh_reg()
    self._emit(Opcode.CONST, result_reg=reg, operands=[self.FALSE_LITERAL], node=node)
    return reg
```

### Combined Boolean: `_lower_canonical_bool(node)`

`_lower_canonical_bool(node)` (line 224):

Reads the node text, strips and lowercases it, then delegates to `_lower_canonical_true` or `_lower_canonical_false`. Used for languages where tree-sitter uses a single `"boolean"` or `"boolean_literal"` node type for both `true` and `false` (e.g., Kotlin, Scala).

### Raw Literals: `_lower_const_literal(node)`

`_lower_const_literal(node)` (line 190):

Emits `CONST` with the literal text of the node as-is. Used for numbers, strings, and other literals that do not need canonicalization.

---

## Operator Handling

### Binary Operators: `_lower_binop(node)`

**Line 250.** Lowers binary operators by extracting three children (filtering out parentheses):
1. Left operand (child 0) -- lowered as expression
2. Operator (child 1) -- extracted as raw text (e.g., `"+"`, `"=="`, `"and"`, `"&&"`)
3. Right operand (child 2) -- lowered as expression

Emits: `%result = BINOP <op> <lhs_reg> <rhs_reg>`

Operators are **not normalized** across languages in the base class. The operator text is passed through as-is. The VM handles language-specific operator semantics.

### Comparison Operators: `_lower_comparison(node)`

**Line 264.** Identical in structure to `_lower_binop`. Both emit `BINOP`. The separate method exists because some tree-sitter grammars distinguish `binary_expression` from `comparison_expression` node types, and subclasses may need to wire them separately.

### Unary Operators: `_lower_unop(node)`

**Line 278.** Extracts operator (child 0) and operand (child 1), filtering out parentheses.

Emits: `%result = UNOP <op> <operand_reg>`

### Update Expressions: `_lower_update_expr(node)`

**Line 856.** Handles `i++`, `i--`, `++i`, `--i` (C-family languages).

1. Extract the operand (first named child)
2. Determine the operator (`"+"` if `"++"` in text, else `"-"`)
3. Lower the operand, emit `CONST "1"`, emit `BINOP`, then store back

Returns the result register (post-increment/decrement value; pre- vs. post- distinction is not modelled).

---

## Call Lowering

### Entry Point: `_lower_call(node)`

**Line 291.** Extracts the function node and arguments node using `CALL_FUNCTION_FIELD` and `CALL_ARGUMENTS_FIELD`, then delegates to `_lower_call_impl`.

### Three-Way Dispatch: `_lower_call_impl(func_node, args_node, node)`

**Line 296.** Distinguishes three call patterns by inspecting `func_node.type`:

**1. Method Call** -- if `func_node.type` is any of:
- `self.ATTRIBUTE_NODE_TYPE` (default: `"attribute"`)
- `"member_expression"`
- `"selector_expression"`
- `"member_access_expression"`
- `"field_access"`
- `"method_index_expression"`

Extracts object and attribute nodes, lowers the object, and emits:
```
%result = CALL_METHOD <obj_reg> <method_name> <arg_regs...>
```

**2. Plain Function Call** -- if `func_node.type == "identifier"`:
```
%result = CALL_FUNCTION <func_name> <arg_regs...>
```

**3. Dynamic/Unknown Call** -- anything else (computed call targets, e.g., `getHandler()(args)`):
```
<target_reg> = lower(func_node)
%result = CALL_UNKNOWN <target_reg> <arg_regs...>
```

If `func_node` is `None`, emits `SYMBOLIC "unknown_call_target"` as the target.

### Argument Extraction

Two methods for extracting call arguments:

**`_extract_call_args(args_node)`** (line 359): Filters children by excluding `(`, `)`, `,`, `"argument"`, and `"value_argument"` types, lowering each named child as an expression.

**`_extract_call_args_unwrap(args_node)`** (line 370): More sophisticated -- unwraps `"argument"` and `"value_argument"` wrapper nodes by finding their first named grandchild. Used by languages (like Kotlin) where arguments are wrapped in additional nodes.

---

## Store Target Lowering

### `_lower_store_target(target, val_reg, parent_node)`

**Line 427.** Determines the correct store instruction based on the target node type:

| Target Type | Instruction | Operands |
|---|---|---|
| `"identifier"` | `STORE_VAR` | `[name, val_reg]` |
| Attribute types (`self.ATTRIBUTE_NODE_TYPE`, `"member_expression"`, `"selector_expression"`, `"member_access_expression"`, `"field_access"`) | `STORE_FIELD` | `[obj_reg, field_name, val_reg]` |
| `"subscript"` | `STORE_INDEX` | `[obj_reg, idx_reg, val_reg]` |
| Anything else (fallback) | `STORE_VAR` | `[node_text, val_reg]` |

For attribute targets, object and attribute nodes are extracted via `ATTR_OBJECT_FIELD` / `ATTR_ATTRIBUTE_FIELD` with fallbacks to first/last children.

---

## Collection Literal Lowering

### List/Array: `_lower_list_literal(node)`

**Line 821.** Lowers `[a, b, c]` style literals.

1. Filter children to exclude `[`, `]`, `,`
2. Emit `CONST <size>` for the array length
3. Emit `NEW_ARRAY "list" <size_reg>`
4. For each element: lower the expression, emit `CONST <index>`, emit `STORE_INDEX`

### Dictionary/Object: `_lower_dict_literal(node)`

**Line 839.** Lowers `{key: value}` style literals.

1. Emit `NEW_OBJECT "dict"`
2. For each child of type `"pair"`: extract key and value fields, lower both, emit `STORE_INDEX`

---

## Utility Methods

### Register and Label Generation

**`_fresh_reg() -> str`** (line 79): Returns `"%N"` and increments the counter. Registers are SSA-style -- each call produces a unique name.

**`_fresh_label(prefix="L") -> str`** (line 84): Returns `"<prefix>_N"` and increments the counter. Labels are globally unique within a single `lower()` call.

### Instruction Emission

**`_emit(opcode, *, result_reg, operands, label, source_location, node) -> IRInstruction`** (line 89):

Creates an `IRInstruction` and appends it to `_instructions`. Source location resolution:
1. If `source_location` is provided and not unknown, use it
2. Else if `node` is provided, derive location via `_source_loc(node)`
3. Else use `NO_SOURCE_LOCATION`

### Node Text and Source Location

**`_node_text(node) -> str`** (line 114): Extracts the source text for a node by slicing `_source[start_byte:end_byte]` and decoding UTF-8.

**`_source_loc(node) -> SourceLocation`** (line 117): Converts tree-sitter's 0-based `(row, column)` tuples to 1-based line numbers:
```python
SourceLocation(
    start_line=node.start_point[0] + 1,
    start_col=node.start_point[1],
    end_line=node.end_point[0] + 1,
    end_col=node.end_point[1],
)
```

### Loop Stack Management

**`_push_loop(continue_label, end_label)`** (line 626): Pushes onto both `_loop_stack` and `_break_target_stack`.

**`_pop_loop()`** (line 633): Pops from both stacks.

The separation of `_loop_stack` and `_break_target_stack` exists because `break` can also target switch statement end labels, which are not loops and should not be continue targets.

---

## Extension Points

Subclasses are expected to:

1. **Call `super().__init__()`** then populate `_STMT_DISPATCH` and `_EXPR_DISPATCH` with language-specific node type mappings.

2. **Override class-level constants** where the tree-sitter grammar uses different field names or literal tokens. Common overrides:
   - `ATTRIBUTE_NODE_TYPE` -- `"member_expression"` (JS), `"navigation_expression"` (Kotlin), `"field_expression"` (Rust), etc.
   - `ATTR_ATTRIBUTE_FIELD` -- `"property"` (JS/TS), `"name"` (Kotlin), `"field"` (Rust), etc.
   - `DEFAULT_RETURN_VALUE` -- `"0"` (C), `"()"` (Rust, Scala)
   - `COMMENT_TYPES` -- add language-specific comment types
   - `BLOCK_NODE_TYPES` -- add `"statement_block"`, `"compound_statement"`, etc.

3. **Map null/boolean node types to canonical methods** in `_EXPR_DISPATCH`:
   - `"none"` / `"null"` / `"nil"` / `"null_literal"` / `"undefined"` -> `self._lower_canonical_none`
   - `"true"` / `"false"` -> `self._lower_canonical_true` / `self._lower_canonical_false`
   - `"boolean"` / `"boolean_literal"` -> `self._lower_canonical_bool`

4. **Add language-specific lowering methods** for constructs that have no equivalent in the base class (e.g., Python list comprehensions, JavaScript destructuring, Go goroutines, Rust match expressions).

5. **Override `_lower_params`** if the language has a different parameter structure (e.g., Java typed parameters, Go grouped parameters, Rust pattern parameters).

6. **Override `_extract_param_name`** if the language embeds parameter names in unusual AST shapes.

7. **Wrap `_lower_try_catch`** with a language-specific method that extracts catch clauses into the expected dict format, since every language structures try/catch differently in tree-sitter.

---

## Design Notes

### Dispatch Table Pattern

The dispatch table pattern was chosen over visitor pattern or if/elif chains because:
- **Extensibility**: adding a new node type is a single dict entry, not a new method on an interface
- **Transparency**: the full mapping is visible in one place in each subclass's `__init__`
- **Reusability**: base class methods can be referenced by any subclass without adapter code

### Graceful Degradation via SYMBOLIC

Unknown node types produce `SYMBOLIC "unsupported:<type>"` rather than raising exceptions. This means:
- Partial lowering always succeeds
- The VM can still execute the known portions of the program
- Unsupported constructs are visible in the IR for debugging

### State Reset in `lower()`

All mutable state is reset at the start of each `lower()` call, making frontend instances safely reusable. This avoids the need to construct a new frontend object for each file.

### Canonical Literals

The decision to canonicalize all null/boolean literals to Python-form (`"None"`, `"True"`, `"False"`) in the IR was made so that downstream analysis (VM, dataflow, CFG) does not need language-specific logic for basic constant values. The canonicalization happens at the frontier -- in the frontend dispatch tables -- so it is zero-cost at analysis time.

### Separation of Expression and Statement Dispatch

Two separate dispatch tables exist because:
- Expression handlers **return a register** (the value they computed)
- Statement handlers **return nothing** (they emit instructions as side effects)
- Some node types are valid as both (e.g., assignment), and having separate tables allows explicit control over which path is taken

### Loop and Break Stacks

Two parallel stacks are maintained because `break` can target non-loop constructs (switch statements in C-family languages push onto `_break_target_stack` but not `_loop_stack`), while `continue` only targets loops.

### Implicit Return

Every function definition ends with an implicit `CONST DEFAULT_RETURN_VALUE` + `RETURN` pair. This ensures the CFG has a single exit path even for functions that fall through without an explicit return. The value used (`"None"`, `"0"`, or `"()"`) is language-appropriate via the `DEFAULT_RETURN_VALUE` constant.
