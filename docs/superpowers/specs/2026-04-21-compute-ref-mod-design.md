# COMPUTE Source Reference Modification Design

**Issue:** red-dragon-59y3  
**Date:** 2026-04-21

---

## Problem

COBOL allows reference modification in COMPUTE arithmetic expressions:

```cobol
COMPUTE WS-RESULT = WS-FIELD(1:3) + 10
COMPUTE WS-RESULT = WS-A(2:4) * WS-B(1:2)
```

Currently `serializeCompute` extracts the expression as raw source text via
`input.getText(Interval.of(start, stop))` and passes it to Python as a flat
string. The Python expression parser (`cobol_expression.py`) has no awareness
of `NAME(start:length)` notation — the colon is silently dropped by the
tokenizer — so reference modification in COMPUTE expressions is ignored.

---

## Approach: Structured Expression Tree from Java (Approach C)

The Java bridge walks ProLeap's arithmetic AST and emits a normalized JSON
expression tree. Python deserializes the tree directly into the existing
`ExprNode` union (extended with `RefModNode`) and lowers it via the existing
`lower_expr_node` pipeline.

---

## ProLeap Arithmetic Tree Structure

ProLeap's `ArithmeticValueStmt` has the following hierarchy:

```
ArithmeticValueStmt
  getMultDivs()    → MultDivs          (base multiplicative term)
  getPlusMinus()   → List<PlusMinus>   (additional additive terms)

MultDivs
  getPowers()      → Powers            (base factor)
  getMultDivs()    → List<MultDiv>     (additional * or / factors)

Powers
  getBasis()       → Basis             (the atom)
  getPowersType()  → PLUS | MINUS      (unary sign; PLUS = no-op)

Basis
  getBasisValueStmt() → ValueStmt      (leaf: literal, CallValueStmt, or sub-expression)
```

Each list is left-folded into nested `BinOpNode`s by the Java serializer, so
the JSON output is a clean binary tree regardless of expression complexity.

---

## JSON Schema (emitted by bridge)

All nodes carry a `"type"` discriminant:

```json
// literal
{"type": "literal", "value": "5"}

// plain field reference
{"type": "field_ref", "name": "WS-FIELD"}

// reference modification  ← new
{"type": "ref_mod", "name": "WS-FIELD", "ref_mod_start": "1", "ref_mod_length": "3"}

// subscript table access
{"type": "subscript", "name": "WS-TABLE", "subscript": "WS-IDX"}

// binary operation
{"type": "binop", "op": "+", "left": {...}, "right": {...}}
```

Unary negation (MINUS unary sign in `Powers`) is represented as
`{"type": "binop", "op": "*", "left": {"type": "literal", "value": "-1"}, "right": {...}}`
to avoid introducing a new node type.

---

## Components

### 1. Java Bridge — `StatementSerializer.java`

Add four private helpers:

- **`serializeArithExpr(ArithmeticValueStmt)`** — left-folds `getPlusMinus()`
  list over the base `MultDivs` into `BinOpNode`s with `+`/`-` operators.
- **`serializeArithMultDivs(MultDivs)`** — left-folds `getMultDivs()` list
  over the base `Powers` into `BinOpNode`s with `*`/`/` operators.
- **`serializeArithPowers(Powers)`** — handles unary sign; delegates to
  `serializeArithBasis`.
- **`serializeArithBasis(Basis)`** — dispatches on `getBasisValueStmt()` type:
  - `CallValueStmt` → reuse `serializeMoveOperand(call)` (already handles
    ref_mod vs subscript vs plain field)
  - `ArithmeticValueStmt` → recurse via `serializeArithExpr` (parenthesized
    sub-expression)
  - anything else → extract literal text via `vs.getCtx().getText()`

Update `serializeCompute` to replace the raw-text extraction with:
```java
obj.add("expression", serializeArithExpr(stmt.getArithmeticExpression()));
```

Targets remain extracted as plain string names (no change).

### 2. Python AST — `cobol_expression.py`

Add:
```python
@dataclass(frozen=True)
class RefModNode:
    name: str
    ref_mod_start: str   # 1-based, as string from JSON
    ref_mod_length: str  # length, as string from JSON

ExprNode = LiteralNode | FieldRefNode | RefModNode | BinOpNode

def expr_from_dict(d: dict) -> ExprNode:
    """Deserialize a JSON expression tree dict into an ExprNode."""
    t = d["type"]
    if t == "literal":   return LiteralNode(value=d["value"])
    if t == "field_ref": return FieldRefNode(name=d["name"])
    if t == "ref_mod":   return RefModNode(name=d["name"],
                                           ref_mod_start=d["ref_mod_start"],
                                           ref_mod_length=d["ref_mod_length"])
    if t == "subscript": return FieldRefNode(name=f'{d["name"]}({d["subscript"]})')
    if t == "binop":     return BinOpNode(op=d["op"],
                                          left=expr_from_dict(d["left"]),
                                          right=expr_from_dict(d["right"]))
    raise ValueError(f"Unknown expression node type: {t!r}")
```

Note: `subscript` is mapped to the existing `FieldRefNode(name="TABLE(IDX)")` 
format that `lower_expr_node` already resolves correctly via `resolve_field_ref`.

### 3. Python AST — `cobol_statements.py`

`ComputeStatement`:
- `expression: str` → `expression: ExprNode`
- `from_dict`: replace `d["expression"]` string capture with
  `expr_from_dict(d["expression"])`

### 4. Python Lowering — `condition_lowering.py`

Add `RefModNode` branch to `lower_expr_node`:
```python
if isinstance(node, RefModNode):
    ref = ctx.resolve_field_ref(node.name, layout, region_reg)
    full_str = ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg)
    start_reg = ctx.const_to_reg(int(node.ref_mod_start) - 1)  # 1-based → 0-based
    len_reg   = ctx.const_to_reg(int(node.ref_mod_length))
    return ctx.call_builtin("STRING_SLICE", [full_str, start_reg, len_reg])
```

The result register holds a string substring. At the `BinOpNode` level,
`BinopCoercionStrategy` already coerces operands to numeric at runtime —
no additional conversion is needed.

### 5. Python Lowering — `lower_arithmetic.py`

`lower_compute`: remove the `parse_expression(stmt.expression)` call.
`stmt.expression` is already an `ExprNode`; pass it directly to
`lower_expr_node`.

---

## What Is NOT Changed

- `cobol_expression.py`'s `parse_expression` / `tokenize_expression` functions
  are retained — their unit tests remain valid as standalone parser tests.
- COMPUTE targets remain plain string names (ref_mod on COMPUTE targets is
  a separate, untracked feature).
- `on_size_error` / `not_on_size_error` serialization in `serializeCompute` is
  unaffected.

---

## Integration Tests

New class `TestComputeRefMod` in `tests/integration/test_cobol_programs.py`:

| Test | Setup | Expression | Expected |
|------|-------|------------|----------|
| `test_compute_ref_mod_simple` | WS-FIELD='123ABC', WS-RESULT PIC 9(5) | `WS-FIELD(1:3)` | WS-RESULT = 123 |
| `test_compute_ref_mod_offset` | WS-FIELD='XXX456', WS-RESULT PIC 9(5) | `WS-FIELD(4:3)` | WS-RESULT = 456 |
| `test_compute_ref_mod_in_expression` | WS-FIELD='010XY', WS-RESULT PIC 9(5) | `WS-FIELD(1:3) + 5` | WS-RESULT = 15 |
| `test_compute_ref_mod_multiply` | WS-FIELD='003XY', WS-RESULT PIC 9(5) | `WS-FIELD(1:3) * 4` | WS-RESULT = 12 |
| `test_compute_no_ref_mod_regression` | WS-A=10, WS-B=3, WS-RESULT PIC 9(5) | `WS-A + WS-B` | WS-RESULT = 13 |

All tests decorated with `@covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)`.

---

## Verification

```bash
cd proleap-bridge && mvn package -q
poetry run python -m pytest tests/integration/test_cobol_programs.py::TestComputeRefMod -x -q
poetry run python -m pytest -x -q   # full regression
poetry run python -m black .
```
