# Pascal Frontend

> `interpreter/frontends/pascal.py` · Extends `BaseFrontend` · ~915 lines

## Overview

The Pascal frontend lowers tree-sitter Pascal ASTs into the RedDragon TAC IR. Pascal's grammar uses `k`-prefixed keyword nodes (e.g., `kBegin`, `kEnd`, `kAssign`) rather than punctuation tokens, requiring a custom noise-filtering approach via `_KEYWORD_NOISE`. The frontend handles Pascal-specific constructs including `procedure`/`function` definitions with `:=` return-by-assignment, `for..to`/`for..downto` loops, `repeat..until` loops, `case` statements, typed variable declarations with array sizing, constant declarations, and set literals (`[1, 2, 3]`).

## Class Hierarchy

```
Frontend (abstract)
  └── BaseFrontend (_base.py)
        └── PascalFrontend (pascal.py)
```

`PascalFrontend` inherits register allocation, label generation, `_emit`, `_lower_const_literal`, `_lower_identifier`, `_lower_paren`, and canonical literal helpers from `BaseFrontend`. However, it does **not** use the inherited `_lower_block`, `_lower_if`, `_lower_while`, `_lower_assignment`, or `_lower_function_def` -- instead it provides Pascal-specific versions for all of these.

## Overridden Constants

| Constant | BaseFrontend Default | PascalFrontend Value |
|---|---|---|
| `COMMENT_TYPES` | `frozenset({"comment"})` | `frozenset({"comment"})` (same) |
| `NOISE_TYPES` | `frozenset({"newline", "\n"})` | `_KEYWORD_NOISE` (see below) |
| `BLOCK_NODE_TYPES` | `frozenset()` | `frozenset({"block"})` |

### `_KEYWORD_NOISE` (module-level constant)

A `frozenset` of 30 keyword/punctuation node types that the Pascal frontend treats as noise:

```python
frozenset({
    "kProgram", "kBegin", "kEnd", "kEndDot", "kVar", "kDo", "kThen",
    "kElse", "kOf", "kTo", "kDownto", "kAssign", "kSemicolon", "kColon",
    "kComma", "kDot", "kLParen", "kRParen", "kIf", "kWhile", "kFor",
    "kRepeat", "kUntil", "kFunction", "kProcedure", "kCase", "kNot",
    "kSub", "kAdd", "kEq", "kConst",
    ";", ":", ",", ".", "(", ")", "\n"
})
```

### `_K_OPERATOR_MAP` (module-level constant)

Maps keyword node types to IR operator symbols:

| Keyword | IR Operator |
|---|---|
| `kAdd` | `+` |
| `kSub` | `-` |
| `kMul` | `*` |
| `kDiv` | `/` |
| `kGt` | `>` |
| `kLt` | `<` |
| `kEq` | `==` |
| `kNeq` | `!=` |
| `kGte` | `>=` |
| `kLte` | `<=` |
| `kAnd` | `and` |
| `kOr` | `or` |
| `kMod` | `mod` |

### `_K_UNARY_MAP` (class-level constant)

Maps unary keyword node types to IR operator symbols:

| Keyword | IR Operator |
|---|---|
| `kNot` | `not` |
| `kSub` | `-` |
| `kAdd` | `+` |

Note: `NONE_LITERAL`, `TRUE_LITERAL`, `FALSE_LITERAL`, `DEFAULT_RETURN_VALUE` retain their BaseFrontend defaults.

## Expression Dispatch Table

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `identifier` | `_lower_identifier` | `LOAD_VAR` |
| `literalNumber` | `_lower_const_literal` | `CONST` (raw text) |
| `literalString` | `_lower_const_literal` | `CONST` (raw text) |
| `exprBinary` | `_lower_pascal_binop` | `BINOP` (with `_K_OPERATOR_MAP` translation) |
| `exprCall` | `_lower_pascal_call` | `CALL_FUNCTION` or `CALL_UNKNOWN` |
| `exprParens` | `_lower_paren` | (unwraps inner expr) |
| `exprDot` | `_lower_pascal_dot` | `LOAD_FIELD` |
| `exprSubscript` | `_lower_pascal_subscript` | `LOAD_INDEX` |
| `exprUnary` | `_lower_pascal_unary` | `UNOP` (with `_K_UNARY_MAP` translation) |
| `exprBrackets` | `_lower_pascal_brackets` | `NEW_ARRAY("set", size)` + `STORE_INDEX` |
| `kTrue` | `_lower_canonical_true` | `CONST "True"` |
| `kFalse` | `_lower_canonical_false` | `CONST "False"` |
| `kNil` | `_lower_canonical_none` | `CONST "None"` |

## Statement Dispatch Table

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `root` | `_lower_pascal_root` | (iterates named children) |
| `program` | `_lower_pascal_program` | (iterates non-noise, non-moduleName children) |
| `block` | `_lower_pascal_block` | (iterates non-noise named children) |
| `statement` | `_lower_pascal_statement` | (unwraps to inner statement) |
| `assignment` | `_lower_pascal_assignment` | `STORE_VAR`/`STORE_INDEX`/`RETURN` |
| `declVars` | `_lower_pascal_decl_vars` | (iterates `declVar` children) |
| `declVar` | `_lower_pascal_decl_var` | `STORE_VAR` (scalar) or `NEW_ARRAY` (array) |
| `ifElse` | `_lower_pascal_if` | `BRANCH_IF` + labels |
| `if` | `_lower_pascal_if` | `BRANCH_IF` + labels |
| `while` | `_lower_pascal_while` | `BRANCH_IF` loop |
| `for` | `_lower_pascal_for` | `STORE_VAR`/`BINOP`/`BRANCH_IF` loop |
| `defProc` | `_lower_pascal_proc` | `BRANCH`/`LABEL`/`RETURN`/`STORE_VAR` |
| `declProc` | `_lower_pascal_proc` | `BRANCH`/`LABEL`/`RETURN`/`STORE_VAR` |
| `statements` | `_lower_pascal_block` | (alias for block lowering) |
| `case` | `_lower_pascal_case` | `BINOP ==` + `BRANCH_IF` chain |
| `repeat` | `_lower_pascal_repeat` | Body-first loop + `BRANCH_IF` |
| `declConsts` | `_lower_pascal_decl_consts` | (iterates `declConst` children) |
| `declConst` | `_lower_pascal_decl_const` | `STORE_VAR` |
| `declType` | `_lower_pascal_noop` | No-op |
| `declTypes` | `_lower_pascal_noop` | No-op |

## Language-Specific Lowering Methods

### `_lower_pascal_root(node)`
Entry point for the `root` node. Iterates all named children and dispatches each to `_lower_stmt`.

### `_lower_pascal_program(node)`
Handles the `program` node. Iterates children, skipping noise keywords and `moduleName` nodes. Dispatches remaining named children to `_lower_stmt`.

### `_lower_pascal_block(node)`
Handles `block` and `statements` nodes. Iterates children, filtering out `_KEYWORD_NOISE`. Also used for `statements` via dispatch table aliasing.

### `_lower_pascal_statement(node)`
Unwraps a `statement` node. Finds the first non-noise named child and dispatches to `_lower_stmt`. Falls back to lowering each named child as an expression.

### `_lower_pascal_decl_vars(node)` / `_lower_pascal_decl_var(node)`
`declVars` iterates `declVar` children. Each `declVar` extracts an `identifier` and optional `type` node:
- If the type contains a `declArray` with a `range` (two `literalNumber` children), computes array size as `hi - lo + 1` and emits `NEW_ARRAY("array", size_reg)` + `STORE_VAR`
- Otherwise emits `CONST "None"` + `STORE_VAR` for scalar variables

### `_pascal_array_size(type_node) -> int`
Helper that extracts array size from a Pascal type node. Looks for `declArray -> range -> literalNumber, literalNumber` and returns `hi - lo + 1`. Returns `0` if not an array type.

### `_lower_pascal_assignment(node)`
Handles Pascal assignment (`target := value`). Extracts non-noise named children as `[target, value]`. Three cases:
1. **Array subscript target** (`exprSubscript`): Lowers object and index from `exprArgs`, emits `STORE_INDEX`
2. **Function return** (target name matches `_current_function_name`): Emits `RETURN` (Pascal convention for function return values)
3. **Simple variable**: Emits `STORE_VAR`

### `_lower_pascal_binop(node) -> str`
Handles `exprBinary`. Finds the operator by matching children against `_K_OPERATOR_MAP`. Falls back to the text of the middle named child if no k-prefixed operator found. Emits `BINOP`.

### `_lower_pascal_call(node) -> str`
Handles `exprCall`. Extracts `identifier` and `exprArgs` children. If identifier found, emits `CALL_FUNCTION`. Otherwise emits `SYMBOLIC("unknown_call_target")` + `CALL_UNKNOWN`.

### `_extract_pascal_args(args_node) -> list[str]`
Extracts argument registers from `exprArgs` nodes. Filters out noise keywords, lowers each remaining named child as an expression.

### `_lower_pascal_if(node)`
Handles both `if` and `ifElse` nodes. Extracts non-noise named children as `[condition, consequence, optional_alternative]`. Emits `BRANCH_IF` with true/false/end labels. Uses `_lower_stmt` (not `_lower_block`) for consequence and alternative since Pascal's if body can be a single statement.

### `_lower_pascal_while(node)`
Handles `while` nodes. Extracts `[condition, body]` from non-noise named children. Emits standard condition-first loop: `LABEL`, `BINOP`/`BRANCH_IF`, body, `BRANCH` back.

### `_lower_pascal_for(node)`
Handles `for` loops. Detects two AST shapes:
1. **Named children starting with `assignment`**: Extracts var/start from the assignment, end value, and body from `[assignment, end_value, body]`
2. **Four named children**: `[var, start, end, body]`

Determines direction from `kDownto` presence. Uses `<=` (or `>=` for downto) comparison. Step is always `+1` or `-1`.

### `_lower_pascal_proc(node)`
Handles both `defProc` and `declProc`. For `defProc`, looks for a nested `declProc` child to find the identifier and `declArgs`. Extracts identifier, `declArgs`, and `block` body. Sets `_current_function_name` during body lowering (for return-by-assignment detection). Emits function definition pattern with implicit `RETURN`. Restores previous `_current_function_name` after lowering.

### `_lower_pascal_params(args_node)`
Handles `declArgs`. Iterates children, dispatching `declArg` to `_lower_pascal_single_param` and bare `identifier` children to direct `SYMBOLIC`/`STORE_VAR` emission.

### `_lower_pascal_single_param(child)`
Handles a single `declArg`. Pascal allows multiple identifiers sharing a type (`a, b: integer`). Iterates direct `identifier` children only (type identifiers are nested inside `type > typeref`). Emits `SYMBOLIC("param:{name}")` + `STORE_VAR` for each.

### `_lower_pascal_dot(node) -> str`
Handles `exprDot` (record field access, e.g., `obj.field`). Takes first and last non-noise named children as object and field. Emits `LOAD_FIELD`.

### `_lower_pascal_subscript(node) -> str`
Handles `exprSubscript` (array access, e.g., `arr[idx]`). Extracts object from first named child and index from `exprArgs` child. Emits `LOAD_INDEX`.

### `_lower_pascal_unary(node) -> str`
Handles `exprUnary`. Matches operator keyword against `_K_UNARY_MAP` (`kNot` -> `"not"`, `kSub` -> `"-"`, `kAdd` -> `"+"`). Emits `UNOP`.

### `_lower_pascal_case(node)`
Handles `case` statement. Lowers the first named child as the selector expression. Iterates `caseCase` children via `_lower_pascal_case_branch`. Handles optional `kElse` branch by lowering named children after the `kElse` keyword.

### `_lower_pascal_case_branch(case_node, selector_reg, end_label)`
Handles a single `caseCase`. Extracts `caseLabel` children for match values. Builds an OR chain for multi-valued labels: first label uses `BINOP ==`, additional labels add `BINOP ==` + `BINOP or`. Emits `BRANCH_IF` to true/next labels. Body children (non-label, non-noise) are lowered as statements.

### `_lower_pascal_repeat(node)`
Handles `repeat..until`. Body-first loop: last non-noise named child is the condition, everything before is body. Emits body label, lowers body statements, evaluates condition, then `BRANCH_IF` with swapped targets (loop continues while condition is FALSE: `BRANCH_IF cond -> end_label, body_label`).

### `_lower_pascal_brackets(node) -> str`
Handles `exprBrackets` (set literals like `[1, 2, 3]`). Creates `NEW_ARRAY("set", size_reg)` and populates with `STORE_INDEX` per element.

### `_lower_pascal_decl_consts(node)` / `_lower_pascal_decl_const(node)`
`declConsts` iterates `declConst` children. Each `declConst` extracts `identifier` and `defaultValue` nodes. The `defaultValue` wrapper is unwrapped to its inner non-noise named child. Emits `STORE_VAR`.

### `_lower_pascal_noop(node)`
No-op handler for `declType` and `declTypes`. Type declarations produce no IR. Logs a debug message.

## Canonical Literal Handling

| Pascal Node Type | Handler | Canonical IR Value |
|---|---|---|
| `kTrue` | `_lower_canonical_true` | `CONST "True"` |
| `kFalse` | `_lower_canonical_false` | `CONST "False"` |
| `kNil` | `_lower_canonical_none` | `CONST "None"` |

Pascal's boolean literals are keyword nodes (`kTrue`, `kFalse`) rather than typed literal nodes, so they map to the specific `_lower_canonical_true` and `_lower_canonical_false` handlers directly rather than using `_lower_canonical_bool`.

## Example

**Pascal source:**
```pascal
program Factorial;
var
  n, result: integer;

function Fact(x: integer): integer;
begin
  if x <= 1 then
    Fact := 1
  else
    Fact := x * Fact(x - 1);
end;

begin
  n := 5;
  result := Fact(n);
end.
```

**Emitted IR (approximate):**
```
LABEL     __entry__
CONST     %0  "None"
STORE_VAR n   %0
CONST     %1  "None"
STORE_VAR result  %1
BRANCH    end_Fact_1
LABEL     func:Fact_0
SYMBOLIC  %2  "param:x"
STORE_VAR x   %2
LOAD_VAR  %3  "x"
CONST     %4  "1"
BINOP     %5  "<="  %3  %4
BRANCH_IF %5  if_true_2,if_false_3
LABEL     if_true_2
CONST     %6  "1"
RETURN    %6
BRANCH    if_end_4
LABEL     if_false_3
LOAD_VAR  %7  "x"
LOAD_VAR  %8  "x"
CONST     %9  "1"
BINOP     %10  "-"  %8  %9
CALL_FUNCTION %11  "Fact"  %10
BINOP     %12  "*"  %7  %11
RETURN    %12
BRANCH    if_end_4
LABEL     if_end_4
CONST     %13  "None"
RETURN    %13
LABEL     end_Fact_1
CONST     %14  "func:Fact@func:Fact_0"
STORE_VAR Fact  %14
CONST     %15  "5"
STORE_VAR n    %15
LOAD_VAR  %16  "n"
CALL_FUNCTION %17  "Fact"  %16
STORE_VAR result  %17
```

Note: Assignment to the function name (`Fact := 1`) is lowered as `RETURN` because `_current_function_name` is set to `"Fact"` during body lowering.

## Design Notes

1. **Return-by-assignment**: Pascal functions return values by assigning to the function name (`Fact := value`). The frontend tracks `_current_function_name` and converts matching assignments to `RETURN` instructions. This is managed via a save/restore pattern in `_lower_pascal_proc`.

2. **Keyword-based AST**: The Pascal tree-sitter grammar uses `k`-prefixed keyword nodes (e.g., `kBegin`, `kEnd`, `kAssign`) rather than punctuation-based unnamed nodes. The extensive `_KEYWORD_NOISE` set filters these throughout all lowering methods.

3. **Operator keyword mapping**: Binary operators appear as keyword nodes (`kAdd`, `kLt`, etc.) that must be translated to IR operator strings via `_K_OPERATOR_MAP`. This differs from C-family languages where operators are direct text tokens.

4. **Nested `defProc`/`declProc` structure**: The tree-sitter Pascal grammar nests the function signature (`declProc`) inside the definition (`defProc`). The frontend handles both standalone `declProc` and nested `defProc -> declProc` patterns.

5. **Multi-parameter `declArg`**: Pascal allows `a, b: integer` syntax. `_lower_pascal_single_param` correctly emits separate parameter entries for each identifier, filtering out the type identifier (which is nested inside `type > typeref`).

6. **Array declarations compute size**: `declVar` with an array type computes the array size from the range (`array[1..10]` -> size 10). The array is pre-allocated with `NEW_ARRAY`.

7. **`repeat..until` inverts branch condition**: Unlike `while` loops, `repeat..until` continues when the condition is false. The `BRANCH_IF` targets are swapped: `true -> end, false -> body`.

8. **Case with multi-valued labels**: A single `caseCase` can have multiple `caseLabel` children. These are OR-chained: each additional label adds a `BINOP ==` + `BINOP or` to build a compound condition.

9. **No class/OOP support**: Pascal (standard Pascal, not Object Pascal/Delphi) has no class constructs. Type declarations (`declType`, `declTypes`) are no-ops.

10. **`statements` aliased to block**: The `statements` node type is handled by `_lower_pascal_block`, the same handler as `block`.
