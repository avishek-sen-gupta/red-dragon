# Pascal Frontend

> `interpreter/frontends/pascal/` -- Extends `BaseFrontend` -- per-language directory architecture

## Overview

The Pascal frontend lowers tree-sitter Pascal ASTs into the RedDragon TAC IR. Pascal's grammar uses `k`-prefixed keyword nodes (e.g., `kBegin`, `kEnd`, `kAssign`) rather than punctuation tokens, requiring a custom noise-filtering approach via `KEYWORD_NOISE`. The frontend handles Pascal-specific constructs including `procedure`/`function` definitions with `:=` return-by-assignment, `for..to`/`for..downto` loops, `repeat..until` loops, `case` statements, typed variable declarations with array sizing, constant declarations, set literals (`[1, 2, 3]`), record types (`declType`/`declClass`), `try`/`except`/`finally` exception handling, `raise` statements, `with` blocks, `inherited` calls, and `uses` declarations.

## Directory Structure

```
interpreter/frontends/pascal/
  frontend.py            -- PascalFrontend class (thin orchestrator)
  node_types.py          -- PascalNodeType constants class
  expressions.py         -- Pascal-specific expression lowerers (pure functions)
  control_flow.py        -- Pascal-specific control flow lowerers (pure functions)
  declarations.py        -- Pascal-specific declaration lowerers (pure functions)
  pascal_constants.py    -- KEYWORD_NOISE, K_OPERATOR_MAP, K_UNARY_MAP
  type_helpers.py        -- extract_pascal_return_type helper
```

## Class Hierarchy

```
Frontend (abstract)
  +-- BaseFrontend (_base.py)
        +-- PascalFrontend (pascal/frontend.py)
```

`PascalFrontend` is a thin orchestrator that builds dispatch tables from pure functions. All lowering logic lives in the `expressions`, `control_flow`, and `declarations` modules as pure functions taking `(ctx: TreeSitterEmitContext, node)`. It inherits register allocation, label generation, `emit`, `lower_const_literal`, `lower_identifier`, and canonical literal helpers from `BaseFrontend`. However, it does **not** use the inherited `lower_block`, `lower_if`, `lower_while`, `lower_assignment`, or `lower_function_def` -- instead it provides Pascal-specific versions for all of these.

The `_build_context` method is overridden to attach Pascal-specific mutable state to the context: `_pascal_current_function_name` (for return-by-assignment detection) and `_pascal_record_types` (set of declared record type names).

## Grammar Constants (`_build_constants()`)

| Field | Value |
|---|---|
| `comment_types` | `frozenset({PascalNodeType.COMMENT})` |
| `noise_types` | `KEYWORD_NOISE` (from `pascal_constants.py`, see below) |
| `block_node_types` | `frozenset({PascalNodeType.BLOCK, PascalNodeType.ROOT, PascalNodeType.PROGRAM, PascalNodeType.STATEMENTS})` |

### `KEYWORD_NOISE` (in `pascal_constants.py`)

A `frozenset` of keyword/punctuation node types that the Pascal frontend treats as noise:

```python
frozenset({
    "kProgram", "kBegin", "kEnd", "kEndDot", "kVar", "kDo", "kThen",
    "kElse", "kOf", "kTo", "kDownto", "kAssign", "kSemicolon", "kColon",
    "kComma", "kDot", "kLParen", "kRParen", "kIf", "kWhile", "kFor",
    "kRepeat", "kUntil", "kFunction", "kProcedure", "kCase", "kNot",
    "kSub", "kAdd", "kEq", "kConst", "kTry", "kExcept", "kFinally",
    "kOn", "kRaise", "kWith",
    ";", ":", ",", ".", "(", ")", "\n"
})
```

### `K_OPERATOR_MAP` (in `pascal_constants.py`)

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

### `K_UNARY_MAP` (in `pascal_constants.py`)

Maps unary keyword node types to IR operator symbols:

| Keyword | IR Operator |
|---|---|
| `kNot` | `not` |
| `kSub` | `-` |
| `kAdd` | `+` |

Note: `none_literal`, `true_literal`, `false_literal`, `default_return_value` retain their `GrammarConstants` defaults.

## Expression Dispatch Table (`_build_expr_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `literalNumber` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `literalString` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `exprBinary` | `pascal_expr.lower_pascal_binop` | `BINOP` (with `K_OPERATOR_MAP` translation) |
| `exprCall` | `pascal_expr.lower_pascal_call` | `CALL_FUNCTION` or `CALL_UNKNOWN` |
| `exprParens` | `pascal_expr.lower_pascal_paren` | (unwraps inner expr) |
| `exprDot` | `pascal_expr.lower_pascal_dot` | `LOAD_FIELD` |
| `exprSubscript` | `pascal_expr.lower_pascal_subscript` | `LOAD_INDEX` |
| `exprUnary` | `pascal_expr.lower_pascal_unary` | `UNOP` (with `K_UNARY_MAP` translation) |
| `exprBrackets` | `pascal_expr.lower_pascal_brackets` | `NEW_ARRAY("set", size)` + `STORE_INDEX` |
| `kTrue` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `kFalse` | `common_expr.lower_canonical_false` | `CONST "False"` |
| `kNil` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `range` | `pascal_expr.lower_pascal_range` | `CALL_FUNCTION("range", lo, hi)` |
| `inherited` | `pascal_expr.lower_pascal_inherited_expr` | `CALL_FUNCTION("inherited", method)` |
| `typeref` | `common_expr.lower_const_literal` | `CONST` (raw text) |

## Statement Dispatch Table (`_build_stmt_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `root` | `pascal_cf.lower_pascal_root` | (iterates named children) |
| `program` | `pascal_cf.lower_pascal_program` | (iterates non-noise, non-moduleName children) |
| `block` | `pascal_cf.lower_pascal_block` | (iterates non-noise named children) |
| `statement` | `pascal_cf.lower_pascal_statement` | (unwraps to inner statement) |
| `assignment` | `pascal_decl.lower_pascal_assignment` | `STORE_VAR`/`STORE_INDEX`/`STORE_FIELD`/`RETURN` |
| `declVars` | `pascal_decl.lower_pascal_decl_vars` | (iterates `declVar` children) |
| `declVar` | `pascal_decl.lower_pascal_decl_var` | `STORE_VAR` (scalar) or `NEW_ARRAY` (array) or `CALL_FUNCTION` (record) |
| `ifElse` | `pascal_cf.lower_pascal_if` | `BRANCH_IF` + labels |
| `if` | `pascal_cf.lower_pascal_if` | `BRANCH_IF` + labels |
| `while` | `pascal_cf.lower_pascal_while` | `BRANCH_IF` loop |
| `for` | `pascal_cf.lower_pascal_for` | `STORE_VAR`/`BINOP`/`BRANCH_IF` loop |
| `defProc` | `pascal_decl.lower_pascal_proc` | `BRANCH`/`LABEL`/`RETURN`/`STORE_VAR` |
| `declProc` | `pascal_decl.lower_pascal_proc` | `BRANCH`/`LABEL`/`RETURN`/`STORE_VAR` |
| `statements` | `pascal_cf.lower_pascal_block` | (alias for block lowering) |
| `case` | `pascal_cf.lower_pascal_case` | `BINOP ==` + `BRANCH_IF` chain |
| `repeat` | `pascal_cf.lower_pascal_repeat` | Body-first loop + `BRANCH_IF` |
| `declConsts` | `pascal_decl.lower_pascal_decl_consts` | (iterates `declConst` children) |
| `declConst` | `pascal_decl.lower_pascal_decl_const` | `STORE_VAR` |
| `declType` | `pascal_decl.lower_pascal_decl_type` | `CLASS_REF` for record types, skip others |
| `declTypes` | `pascal_decl.lower_pascal_decl_types` | (iterates `declType` children) |
| `declUses` | `pascal_cf.lower_pascal_noop` | No-op |
| `try` | `pascal_cf.lower_pascal_try` | `LABEL`/`SYMBOLIC`/`BRANCH` (try/except/finally) |
| `exceptionHandler` | `pascal_cf.lower_pascal_exception_handler` | `SYMBOLIC`/`STORE_VAR` + body |
| `raise` | `pascal_cf.lower_pascal_raise` | `THROW` |
| `with` | `pascal_cf.lower_pascal_with` | Lowers object then body |
| `inherited` | `pascal_cf.lower_pascal_inherited_stmt` | `CALL_FUNCTION("inherited", method)` |

## Language-Specific Lowering Methods

### `pascal_cf.lower_pascal_root(ctx, node)`
Entry point for the `root` node. Iterates all named children and dispatches each to `ctx.lower_stmt`.

### `pascal_cf.lower_pascal_program(ctx, node)`
Handles the `program` node. Iterates children, skipping noise keywords and `moduleName` nodes. Dispatches remaining named children to `ctx.lower_stmt`.

### `pascal_cf.lower_pascal_block(ctx, node)`
Handles `block` and `statements` nodes. Iterates children, filtering out `KEYWORD_NOISE`. Also used for `statements` via dispatch table aliasing.

### `pascal_cf.lower_pascal_statement(ctx, node)`
Unwraps a `statement` node. Finds the first non-noise named child and dispatches to `ctx.lower_stmt`. Falls back to lowering each named child as an expression.

### `pascal_decl.lower_pascal_decl_vars(ctx, node)` / `pascal_decl.lower_pascal_decl_var(ctx, node)`
`declVars` iterates `declVar` children. Each `declVar` extracts an `identifier` and optional `type` node:
- If the type contains a `declArray` with a `range` (two `literalNumber` children), computes array size as `hi - lo + 1` and emits `NEW_ARRAY("array", size_reg)` + `STORE_VAR`
- If the type names a record type (tracked via `ctx._pascal_record_types`), emits `CALL_FUNCTION(type_name)` + `STORE_VAR`
- Otherwise emits `CONST "None"` + `STORE_VAR` for scalar variables
- Seeds variable type hints via `ctx.seed_var_type`

### `pascal_decl.lower_pascal_assignment(ctx, node)`
Handles Pascal assignment (`target := value`). Extracts non-noise named children as `[target, value]`. Four cases:
1. **Array subscript target** (`exprSubscript`): Lowers object and index from `exprArgs`, emits `STORE_INDEX`
2. **Dot target** (`exprDot`): Lowers object, emits `STORE_FIELD`
3. **Function return** (target name matches `_pascal_current_function_name`): Emits `RETURN` (Pascal convention for function return values)
4. **Simple variable**: Emits `STORE_VAR`

### `pascal_expr.lower_pascal_binop(ctx, node) -> str`
Handles `exprBinary`. Finds the operator by matching children against `K_OPERATOR_MAP`. Falls back to the text of the middle named child if no k-prefixed operator found. Emits `BINOP`.

### `pascal_expr.lower_pascal_call(ctx, node) -> str`
Handles `exprCall`. Extracts `identifier` and `exprArgs` children. If identifier found, emits `CALL_FUNCTION`. Otherwise emits `SYMBOLIC("unknown_call_target")` + `CALL_UNKNOWN`.

### `pascal_expr.lower_pascal_paren(ctx, node) -> str`
Handles `exprParens`. Unwraps inner expression by finding the first child that is not `(` or `)`.

### `pascal_expr.lower_pascal_dot(ctx, node) -> str`
Handles `exprDot` (record field access, e.g., `obj.field`). Takes first and last non-noise named children as object and field. Emits `LOAD_FIELD`.

### `pascal_expr.lower_pascal_subscript(ctx, node) -> str`
Handles `exprSubscript` (array access, e.g., `arr[idx]`). Extracts object from first named child and index from `exprArgs` child. Emits `LOAD_INDEX`.

### `pascal_expr.lower_pascal_unary(ctx, node) -> str`
Handles `exprUnary`. Matches operator keyword against `K_UNARY_MAP` (`kNot` -> `"not"`, `kSub` -> `"-"`, `kAdd` -> `"+"`). Emits `UNOP`.

### `pascal_expr.lower_pascal_brackets(ctx, node) -> str`
Handles `exprBrackets` (set literals like `[1, 2, 3]`). Creates `NEW_ARRAY("set", size_reg)` and populates with `STORE_INDEX` per element.

### `pascal_expr.lower_pascal_range(ctx, node) -> str`
Handles `4..10` range expressions. Emits `CALL_FUNCTION("range", lo_reg, hi_reg)`.

### `pascal_expr.lower_pascal_inherited_expr(ctx, node) -> str`
Handles `inherited Create` as expression. Emits `CALL_FUNCTION("inherited", method_name)`.

### `pascal_cf.lower_pascal_if(ctx, node)`
Handles both `if` and `ifElse` nodes. Extracts non-noise named children as `[condition, consequence, optional_alternative]`. Emits `BRANCH_IF` with true/false/end labels. Uses `ctx.lower_stmt` (not `lower_block`) for consequence and alternative since Pascal's if body can be a single statement.

### `pascal_cf.lower_pascal_while(ctx, node)`
Handles `while` nodes. Extracts `[condition, body]` from non-noise named children. Emits standard condition-first loop: `LABEL`, `BINOP`/`BRANCH_IF`, body, `BRANCH` back.

### `pascal_cf.lower_pascal_for(ctx, node)`
Handles `for` loops. Detects two AST shapes:
1. **Named children starting with `assignment`**: Extracts var/start from the assignment, end value, and body from `[assignment, end_value, body]`
2. **Four named children**: `[var, start, end, body]`

Determines direction from `kDownto` presence. Uses `<=` (or `>=` for downto) comparison. Step is always `+1` or `-1`.

### `pascal_decl.lower_pascal_proc(ctx, node)`
Handles both `defProc` and `declProc`. For `defProc`, looks for a nested `declProc` child to find the identifier and `declArgs`. Extracts identifier, `declArgs`, and `block` body. Sets `ctx._pascal_current_function_name` during body lowering (for return-by-assignment detection). Lowers nested `defProc` children (nested procedures). Emits function definition pattern with implicit `RETURN`. Restores previous `_pascal_current_function_name` after lowering. Extracts return type via `type_helpers.extract_pascal_return_type`.

### `type_helpers.extract_pascal_return_type(ctx, search_node) -> str`
Helper in `type_helpers.py`. Determines if the node is a `kFunction` (vs `kProcedure`). If so, extracts the `typeref` child and normalizes the type hint. Returns `""` for procedures.

### `pascal_cf.lower_pascal_case(ctx, node)`
Handles `case` statement. Lowers the first named child as the selector expression. Iterates `caseCase` children via the private `_lower_pascal_case_branch` helper. Handles optional `kElse` branch by lowering named children after the `kElse` keyword.

### `_lower_pascal_case_branch(ctx, case_node, selector_reg, end_label)` (private)
Handles a single `caseCase`. Extracts `caseLabel` children for match values. Builds an OR chain for multi-valued labels: first label uses `BINOP ==`, additional labels add `BINOP ==` + `BINOP or`. Emits `BRANCH_IF` to true/next labels. Body children (non-label, non-noise) are lowered as statements.

### `pascal_cf.lower_pascal_repeat(ctx, node)`
Handles `repeat..until`. Body-first loop: last non-noise named child is the condition, everything before is body. Emits body label, lowers body statements, evaluates condition, then `BRANCH_IF` with swapped targets (loop continues while condition is FALSE: `BRANCH_IF cond -> end_label, body_label`).

### `pascal_cf.lower_pascal_try(ctx, node)`
Handles `try`/`except`/`finally`. Extracts body, catch clauses (from `exceptionHandler` children and bare `statements` blocks in except region), and finally node. Delegates to the common `lower_try_catch` helper.

### `pascal_cf.lower_pascal_exception_handler(ctx, node)`
Handles `on E: Exception do statement`. Extracts the variable identifier and emits `SYMBOLIC("param:{name}")` + `STORE_VAR`. Then lowers body statements.

### `pascal_cf.lower_pascal_raise(ctx, node)`
Handles `raise Exception.Create('oops')`. Lowers the expression child and emits `THROW`.

### `pascal_cf.lower_pascal_with(ctx, node)`
Handles `with P do statement`. Lowers the object expression, then lowers the body statement.

### `pascal_cf.lower_pascal_inherited_stmt(ctx, node)`
Handles `inherited Create` as statement. Delegates to `pascal_expr.lower_pascal_inherited_expr`.

### `pascal_decl.lower_pascal_decl_consts(ctx, node)` / `pascal_decl.lower_pascal_decl_const(ctx, node)`
`declConsts` iterates `declConst` children. Each `declConst` extracts `identifier` and `defaultValue` nodes. The `defaultValue` wrapper is unwrapped to its inner non-noise named child. Emits `STORE_VAR`.

### `pascal_decl.lower_pascal_decl_types(ctx, node)` / `pascal_decl.lower_pascal_decl_type(ctx, node)`
`declTypes` iterates `declType` children. Each `declType` checks for a `declClass` child with a `kRecord` keyword. Record types get `BRANCH`/`LABEL`/`CLASS_REF`/`STORE_VAR` and are tracked in `ctx._pascal_record_types`. Non-record type declarations are skipped.

### `pascal_cf.lower_pascal_noop(ctx, node)`
No-op handler for `declUses`. Logs a debug message.

## Canonical Literal Handling

| Pascal Node Type | Handler | Canonical IR Value |
|---|---|---|
| `kTrue` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `kFalse` | `common_expr.lower_canonical_false` | `CONST "False"` |
| `kNil` | `common_expr.lower_canonical_none` | `CONST "None"` |

Pascal's boolean literals are keyword nodes (`kTrue`, `kFalse`) rather than typed literal nodes, so they map to the specific `lower_canonical_true` and `lower_canonical_false` handlers directly rather than using `lower_canonical_bool`.

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

Note: Assignment to the function name (`Fact := 1`) is lowered as `RETURN` because `_pascal_current_function_name` is set to `"Fact"` during body lowering.

## Design Notes

1. **Return-by-assignment**: Pascal functions return values by assigning to the function name (`Fact := value`). The frontend tracks `ctx._pascal_current_function_name` and converts matching assignments to `RETURN` instructions. This is managed via a save/restore pattern in `pascal_decl.lower_pascal_proc`.

2. **Keyword-based AST**: The Pascal tree-sitter grammar uses `k`-prefixed keyword nodes (e.g., `kBegin`, `kEnd`, `kAssign`) rather than punctuation-based unnamed nodes. The extensive `KEYWORD_NOISE` set in `pascal_constants.py` filters these throughout all lowering functions.

3. **Operator keyword mapping**: Binary operators appear as keyword nodes (`kAdd`, `kLt`, etc.) that must be translated to IR operator strings via `K_OPERATOR_MAP` in `pascal_constants.py`. This differs from C-family languages where operators are direct text tokens.

4. **Nested `defProc`/`declProc` structure**: The tree-sitter Pascal grammar nests the function signature (`declProc`) inside the definition (`defProc`). The frontend handles both standalone `declProc` and nested `defProc -> declProc` patterns. Nested procedures (procedures within procedures) are also supported.

5. **Multi-parameter `declArg`**: Pascal allows `a, b: integer` syntax. The private `_lower_pascal_single_param` helper correctly emits separate parameter entries for each identifier, filtering out the type identifier (which is nested inside `type > typeref`). Type hints are seeded for each parameter.

6. **Array declarations compute size**: `declVar` with an array type computes the array size from the range (`array[1..10]` -> size 10). The array is pre-allocated with `NEW_ARRAY`.

7. **`repeat..until` inverts branch condition**: Unlike `while` loops, `repeat..until` continues when the condition is false. The `BRANCH_IF` targets are swapped: `true -> end, false -> body`.

8. **Case with multi-valued labels**: A single `caseCase` can have multiple `caseLabel` children. These are OR-chained: each additional label adds a `BINOP ==` + `BINOP or` to build a compound condition.

9. **Record types generate CLASS_REF**: `declType` with a `kRecord` child emits `BRANCH`/`LABEL`/`CLASS_REF`/`STORE_VAR` and registers the type name in `ctx._pascal_record_types` so that variable declarations of that type emit `CALL_FUNCTION(type_name)` instead of `CONST "None"`.

10. **`statements` aliased to block**: The `statements` node type is handled by `pascal_cf.lower_pascal_block`, the same handler as `block`.

11. **Pascal-specific paren handling**: Pascal uses `pascal_expr.lower_pascal_paren` instead of the common `lower_paren` because Pascal's `exprParens` children include raw `(` and `)` tokens that need filtering.

12. **Type extraction in `type_helpers.py`**: Return type extraction for functions is isolated in `type_helpers.extract_pascal_return_type`, which distinguishes `kFunction` (has return type) from `kProcedure` (no return type).

13. **Exception handling**: `try`/`except`/`finally` is lowered via the common `lower_try_catch` infrastructure. Pascal's `on E: Exception do` handlers and bare `except` blocks are both supported. The `raise` statement emits `THROW`.
