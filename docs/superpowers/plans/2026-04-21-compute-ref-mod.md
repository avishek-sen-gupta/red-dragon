# COMPUTE Source Reference Modification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable `COMPUTE WS-RESULT = WS-FIELD(1:3) + 10` by walking ProLeap's arithmetic AST in Java and emitting a structured JSON expression tree that Python deserializes into the existing `ExprNode` union (extended with `RefModNode`).

**Architecture:** Java bridge fixes `serializeBasis` to attach ref_mod fields and swaps `serializeCompute`'s raw-text extraction for the already-existing `serializeArithmeticExpr` tree walker. Python adds `RefModNode`, `expr_from_dict`, and one new branch in `lower_expr_node` that decodes the full field and emits a `STRING_SLICE` call. `lower_compute` becomes a one-line change: drop `parse_expression()`, pass `stmt.expression` (already an `ExprNode`) directly.

**Tech Stack:** ProLeap AST (Java), Gson JSON (Java), Python dataclasses, `STRING_SLICE` builtin, existing `BinopCoercionStrategy` (no extra conversion needed).

---

## File Map

| File | Change |
|------|--------|
| `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java` | Fix `serializeBasis` (add ref_mod); fix `serializeCompute` (structured tree) |
| `interpreter/cobol/cobol_expression.py` | Add `RefModNode`; add `expr_from_dict` |
| `interpreter/cobol/cobol_statements.py` | `expression: str → ExprNode`; call `expr_from_dict` |
| `interpreter/cobol/condition_lowering.py` | Add `RefModNode` branch in `lower_expr_node` |
| `interpreter/cobol/lower_arithmetic.py` | Drop `parse_expression()` in `lower_compute` |
| `tests/integration/test_cobol_programs.py` | New `TestComputeRefMod` class |

---

## Background: What Already Exists

`serializeArithmeticExpr` (line 1592) already walks ProLeap's tree and emits nodes with `"kind"` discriminant:
- `{"kind":"lit","value":"5"}` — literal
- `{"kind":"ref","name":"WS-FIELD"}` — field reference (no ref_mod; **this is the bug**)
- `{"kind":"binop","op":"+","left":{...},"right":{...}}` — binary operation
- `{"kind":"neg","expr":{...}}` — unary negation

`serializeBasis` (line 1636) emits `{"kind":"ref","name":"..."}` but never calls `getRefMod(call)` — ref_mod is silently dropped.

`serializeRefMod` (line 1415) already serializes `ref_mod_start` and `ref_mod_length` as **expression subtrees** (via `serializeArithExprCtx`), not plain strings.

`extractCallName` (line 1339) preserves subscript notation: for `TABLE_CALL` it returns `"WS-TABLE(WS-IDX)"` — no change needed for subscripts.

---

## Task 1: Fix `serializeBasis` — attach ref_mod to `"ref"` nodes

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java:1636-1654`

- [ ] **Step 1: Write the failing integration test (Java level — verify JSON shape)**

  Run the bridge on a minimal COBOL snippet in any existing Java bridge test, OR skip to Step 5 (Python integration test is the real gate). The Java change is verified by the Python tests in Task 6.

- [ ] **Step 2: Replace `serializeBasis` body**

  Current body (lines 1636–1654):
  ```java
  private static JsonElement serializeBasis(Basis b) {
      if (b == null) return litNode("");
      ValueStmt vs = b.getBasisValueStmt();
      if (vs instanceof CallValueStmt) {
          Call call = ((CallValueStmt) vs).getCall();
          JsonObject ref = new JsonObject();
          ref.addProperty("kind", "ref");
          ref.addProperty("name", call != null ? extractCallName(call) : b.getCtx().getText());
          return ref;
      }
      if (vs instanceof ArithmeticValueStmt) {
          return serializeArithmeticExpr((ArithmeticValueStmt) vs);
      }
      String text = vs != null && vs.getCtx() != null ? vs.getCtx().getText()
                  : (b.getCtx() != null ? b.getCtx().getText() : "");
      return litNode(text);
  }
  ```

  Replace with:
  ```java
  private static JsonElement serializeBasis(Basis b) {
      if (b == null) return litNode("");
      ValueStmt vs = b.getBasisValueStmt();
      if (vs instanceof CallValueStmt) {
          Call call = ((CallValueStmt) vs).getCall();
          JsonObject ref = new JsonObject();
          ref.addProperty("kind", "ref");
          ref.addProperty("name", call != null ? extractCallName(call) : b.getCtx().getText());
          CobolParser.ReferenceModifierContext refMod = call != null ? getRefMod(call) : null;
          if (refMod != null) {
              JsonObject rm = serializeRefMod(refMod);
              ref.add("ref_mod_start", rm.get("ref_mod_start"));
              if (rm.has("ref_mod_length")) {
                  ref.add("ref_mod_length", rm.get("ref_mod_length"));
              }
          }
          return ref;
      }
      if (vs instanceof ArithmeticValueStmt) {
          return serializeArithmeticExpr((ArithmeticValueStmt) vs);
      }
      String text = vs != null && vs.getCtx() != null ? vs.getCtx().getText()
                  : (b.getCtx() != null ? b.getCtx().getText() : "");
      return litNode(text);
  }
  ```

  The five new lines mirror `serializeMoveOperand` exactly (line 1435–1442).

- [ ] **Step 3: Rebuild the bridge JAR**

  ```bash
  cd /Users/asgupta/code/red-dragon/proleap-bridge && mvn package -q
  ```

  Expected: `BUILD SUCCESS` with no errors.

---

## Task 2: Fix `serializeCompute` — emit structured tree instead of raw text

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java:469-511`

- [ ] **Step 1: Replace raw-text extraction block**

  Current block (lines 473–487):
  ```java
  try {
      if (stmt.getArithmeticExpression() != null && stmt.getArithmeticExpression().getCtx() != null) {
          var ctx = stmt.getArithmeticExpression().getCtx();
          Token start = ctx.getStart();
          Token stop = ctx.getStop();
          if (start != null && stop != null) {
              CharStream input = start.getInputStream();
              String exprText = input.getText(
                      Interval.of(start.getStartIndex(), stop.getStopIndex()));
              obj.addProperty("expression", exprText.trim());
          }
      }
  } catch (Exception e) {
      LOG.fine("Could not extract COMPUTE expression: " + e.getMessage());
  }
  ```

  Replace with:
  ```java
  if (stmt.getArithmeticExpression() != null) {
      obj.add("expression", serializeArithmeticExpr(stmt.getArithmeticExpression()));
  }
  ```

  Note: `obj.add` (not `obj.addProperty`) because `serializeArithmeticExpr` returns `JsonElement`.

- [ ] **Step 2: Remove now-unused imports (if any)**

  Check if `Interval`, `CharStream`, `Token` are used elsewhere in the file. If not, remove those imports. (If the file uses them elsewhere, leave them.)

- [ ] **Step 3: Rebuild the bridge JAR**

  ```bash
  cd /Users/asgupta/code/red-dragon/proleap-bridge && mvn package -q
  ```

  Expected: `BUILD SUCCESS`.

---

## Task 3: Add `RefModNode` and `expr_from_dict` to `cobol_expression.py`

**Files:**
- Modify: `interpreter/cobol/cobol_expression.py`

- [ ] **Step 1: Write the failing unit test**

  Add to `tests/unit/cobol/test_cobol_expression.py` (or create it if it doesn't exist):

  ```python
  from interpreter.cobol.cobol_expression import (
      BinOpNode,
      FieldRefNode,
      LiteralNode,
      RefModNode,
      expr_from_dict,
  )


  class TestExprFromDict:
      def test_literal(self):
          assert expr_from_dict({"kind": "lit", "value": "5"}) == LiteralNode("5")

      def test_plain_ref(self):
          assert expr_from_dict({"kind": "ref", "name": "WS-FIELD"}) == FieldRefNode("WS-FIELD")

      def test_ref_mod(self):
          d = {
              "kind": "ref",
              "name": "WS-FIELD",
              "ref_mod_start": {"kind": "lit", "value": "1"},
              "ref_mod_length": {"kind": "lit", "value": "3"},
          }
          node = expr_from_dict(d)
          assert isinstance(node, RefModNode)
          assert node.name == "WS-FIELD"
          assert node.ref_mod_start == LiteralNode("1")
          assert node.ref_mod_length == LiteralNode("3")

      def test_ref_mod_no_length(self):
          d = {
              "kind": "ref",
              "name": "WS-FIELD",
              "ref_mod_start": {"kind": "lit", "value": "2"},
          }
          node = expr_from_dict(d)
          assert isinstance(node, RefModNode)
          assert node.ref_mod_length is None

      def test_binop(self):
          d = {
              "kind": "binop",
              "op": "+",
              "left": {"kind": "lit", "value": "1"},
              "right": {"kind": "ref", "name": "WS-A"},
          }
          assert expr_from_dict(d) == BinOpNode("+", LiteralNode("1"), FieldRefNode("WS-A"))

      def test_neg(self):
          d = {"kind": "neg", "expr": {"kind": "ref", "name": "WS-X"}}
          node = expr_from_dict(d)
          assert node == BinOpNode("*", LiteralNode("-1"), FieldRefNode("WS-X"))

      def test_unknown_kind_raises(self):
          import pytest
          with pytest.raises(ValueError, match="Unknown"):
              expr_from_dict({"kind": "unknown"})
  ```

- [ ] **Step 2: Run test to verify it fails**

  ```bash
  cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/cobol/test_cobol_expression.py::TestExprFromDict -x -q
  ```

  Expected: `ImportError` or `AttributeError` — `RefModNode` and `expr_from_dict` don't exist yet.

- [ ] **Step 3: Add `RefModNode` and update `ExprNode`**

  In `interpreter/cobol/cobol_expression.py`, after the `BinOpNode` dataclass (line ~56) and before `ExprNode = ...`:

  ```python
  @dataclass(frozen=True)
  class RefModNode:
      """COBOL reference modification: FIELD(start:length) substring access."""

      name: str
      ref_mod_start: "ExprNode"
      ref_mod_length: "ExprNode | None"  # None = to end of string (rare in practice)
  ```

  Update the `ExprNode` alias:
  ```python
  ExprNode = LiteralNode | FieldRefNode | RefModNode | BinOpNode
  ```

- [ ] **Step 4: Add `expr_from_dict`**

  Add after the `ExprNode` alias:

  ```python
  def expr_from_dict(d: dict) -> ExprNode:
      """Deserialize a JSON expression-tree dict (emitted by the Java bridge) into an ExprNode.

      The bridge uses ``"kind"`` as the discriminant with values:
      ``"lit"``, ``"ref"``, ``"binop"``, ``"neg"``.
      A ``"ref"`` node carries ``ref_mod_start``/``ref_mod_length`` sub-trees when
      reference modification is present.
      """
      kind = d["kind"]
      if kind == "lit":
          return LiteralNode(value=d["value"])
      if kind == "ref":
          if "ref_mod_start" in d:
              return RefModNode(
                  name=d["name"],
                  ref_mod_start=expr_from_dict(d["ref_mod_start"]),
                  ref_mod_length=expr_from_dict(d["ref_mod_length"]) if "ref_mod_length" in d else None,
              )
          return FieldRefNode(name=d["name"])
      if kind == "binop":
          return BinOpNode(
              op=d["op"],
              left=expr_from_dict(d["left"]),
              right=expr_from_dict(d["right"]),
          )
      if kind == "neg":
          return BinOpNode(op="*", left=LiteralNode(value="-1"), right=expr_from_dict(d["expr"]))
      raise ValueError(f"Unknown expression node kind: {kind!r}")
  ```

- [ ] **Step 5: Run test to verify it passes**

  ```bash
  cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/cobol/test_cobol_expression.py::TestExprFromDict -x -q
  ```

  Expected: 7 tests pass.

- [ ] **Step 6: Commit**

  ```bash
  git add interpreter/cobol/cobol_expression.py tests/unit/cobol/test_cobol_expression.py
  git commit -m "feat(cobol): add RefModNode and expr_from_dict to cobol_expression"
  ```

---

## Task 4: Update `ComputeStatement` — `expression: str → ExprNode`

**Files:**
- Modify: `interpreter/cobol/cobol_statements.py:247-271`

- [ ] **Step 1: Write the failing unit test**

  Add to `tests/unit/cobol/test_cobol_statements.py` (locate the existing test for `ComputeStatement`, or add a new class):

  ```python
  from interpreter.cobol.cobol_expression import BinOpNode, FieldRefNode, LiteralNode, RefModNode
  from interpreter.cobol.cobol_statements import ComputeStatement


  class TestComputeStatementFromDict:
      def test_plain_expression_deserializes_to_expr_node(self):
          d = {
              "statement": "COMPUTE",
              "expression": {
                  "kind": "binop",
                  "op": "+",
                  "left": {"kind": "ref", "name": "WS-A"},
                  "right": {"kind": "lit", "value": "5"},
              },
              "targets": ["WS-RESULT"],
          }
          stmt = ComputeStatement.from_dict(d)
          assert stmt.expression == BinOpNode("+", FieldRefNode("WS-A"), LiteralNode("5"))
          assert stmt.targets == ["WS-RESULT"]

      def test_ref_mod_expression_deserializes(self):
          d = {
              "statement": "COMPUTE",
              "expression": {
                  "kind": "ref",
                  "name": "WS-FIELD",
                  "ref_mod_start": {"kind": "lit", "value": "1"},
                  "ref_mod_length": {"kind": "lit", "value": "3"},
              },
              "targets": ["WS-RESULT"],
          }
          stmt = ComputeStatement.from_dict(d)
          assert isinstance(stmt.expression, RefModNode)
          assert stmt.expression.name == "WS-FIELD"
  ```

- [ ] **Step 2: Run test to verify it fails**

  ```bash
  cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/cobol/test_cobol_statements.py::TestComputeStatementFromDict -x -q
  ```

  Expected: `TypeError` or `AssertionError` — `expression` is still a `str`.

- [ ] **Step 3: Update `ComputeStatement` in `cobol_statements.py`**

  Add import at the top of `cobol_statements.py` (with other `cobol_expression` imports):
  ```python
  from interpreter.cobol.cobol_expression import ExprNode, expr_from_dict
  ```

  Change the `expression` field type and `from_dict`:
  ```python
  @dataclass(frozen=True)
  class ComputeStatement:
      expression: ExprNode          # was: str
      targets: list[str] = field(default_factory=list)
      on_size_error: list[CobolStatementType] = field(default_factory=list)
      not_on_size_error: list[CobolStatementType] = field(default_factory=list)

      @classmethod
      def from_dict(cls, data: dict) -> ComputeStatement:
          return cls(
              expression=expr_from_dict(data["expression"]),   # was: data.get("expression", "")
              targets=data.get("targets", []),
              on_size_error=[
                  cobol_statement_from_dict(s)
                  for s in data.get("on_size_error", [])
              ],
              not_on_size_error=[
                  cobol_statement_from_dict(s)
                  for s in data.get("not_on_size_error", [])
              ],
          )
  ```

- [ ] **Step 4: Run test to verify it passes**

  ```bash
  cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/cobol/test_cobol_statements.py::TestComputeStatementFromDict -x -q
  ```

  Expected: 2 tests pass.

- [ ] **Step 5: Run full unit suite to catch any regressions**

  ```bash
  cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/ -x -q
  ```

  Expected: all pass.

- [ ] **Step 6: Commit**

  ```bash
  git add interpreter/cobol/cobol_statements.py tests/unit/cobol/test_cobol_statements.py
  git commit -m "feat(cobol): change ComputeStatement.expression from str to ExprNode"
  ```

---

## Task 5: Add `RefModNode` branch to `lower_expr_node`

**Files:**
- Modify: `interpreter/cobol/condition_lowering.py:377-405`

- [ ] **Step 1: Write the failing unit test**

  Add to `tests/unit/cobol/test_condition_lowering.py` (or the appropriate unit test file for `lower_expr_node`). This is a unit test that drives `lower_expr_node` directly with a mock `EmitContext`:

  ```python
  from unittest.mock import MagicMock, call
  from interpreter.cobol.cobol_expression import LiteralNode, RefModNode
  from interpreter.cobol.condition_lowering import lower_expr_node


  class TestLowerExprNodeRefMod:
      def _make_ctx(self):
          ctx = MagicMock()
          ctx.fresh_reg.side_effect = ["r1", "r2", "r3", "r4"]
          ctx.const_to_reg.side_effect = lambda v: f"c{v}"
          ctx.resolve_field_ref.return_value = MagicMock(fl=MagicMock(), offset_reg="off0")
          ctx.emit_decode_field.return_value = "decoded0"
          return ctx

      def test_ref_mod_node_emits_string_slice(self):
          ctx = self._make_ctx()
          layout = MagicMock()
          ctx.has_field.return_value = True

          node = RefModNode(
              name="WS-FIELD",
              ref_mod_start=LiteralNode("1"),
              ref_mod_length=LiteralNode("3"),
          )
          result = lower_expr_node(ctx, node, layout, "region0")

          # Should have emitted a STRING_SLICE call
          call_args = [str(c) for c in ctx.emit_inst.call_args_list]
          assert any("STRING_SLICE" in c or "string_slice" in c for c in call_args)
          assert result is not None
  ```

  Note: This test verifies observable side effects (STRING_SLICE emission). The exact mock wiring depends on how `EmitContext` works in unit tests. If a more comprehensive integration test is cleaner, use Task 6's integration tests as the gate instead and keep this as a smoke test.

- [ ] **Step 2: Run test to verify it fails**

  ```bash
  cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/cobol/test_condition_lowering.py::TestLowerExprNodeRefMod -x -q
  ```

  Expected: `AttributeError` — `lower_expr_node` falls through to the `logger.warning` path.

- [ ] **Step 3: Update imports in `condition_lowering.py`**

  Add to the existing import from `cobol_expression`:
  ```python
  from interpreter.cobol.cobol_expression import (
      BinOpNode,
      ExprNode,
      FieldRefNode,
      LiteralNode,
      RefModNode,
  )
  ```

  Add new imports:
  ```python
  from interpreter.cobol.cobol_constants import BuiltinName
  from interpreter.instructions import Binop, CallFunction, Const
  from interpreter.ir import FuncName
  ```

  Check that `CallFunction` and `FuncName` are available in those modules — look at how `lower_arithmetic.py` does it (lines 9–18) and mirror the exact import paths.

- [ ] **Step 4: Add `RefModNode` branch to `lower_expr_node`**

  Insert before the final `logger.warning` line (after the `BinOpNode` branch, line ~403):

  ```python
  if isinstance(node, RefModNode):
      ref = ctx.resolve_field_ref(node.name, layout, region_reg)
      full_str_reg = ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg)
      # ref_mod_start is 1-based; STRING_SLICE expects 0-based offset
      start_1based_reg = lower_expr_node(ctx, node.ref_mod_start, layout, region_reg)
      one_reg = ctx.const_to_reg(1)
      start_0based_reg = ctx.fresh_reg()
      ctx.emit_inst(
          Binop(
              result_reg=start_0based_reg,
              operator=resolve_binop("-"),
              left=Register(str(start_1based_reg)),
              right=Register(str(one_reg)),
          )
      )
      if node.ref_mod_length is not None:
          length_reg = lower_expr_node(ctx, node.ref_mod_length, layout, region_reg)
      else:
          length_reg = ctx.const_to_reg('"999999"')
      result_reg = ctx.fresh_reg()
      ctx.emit_inst(
          CallFunction(
              result_reg=result_reg,
              func_name=FuncName(BuiltinName.STRING_SLICE),
              args=(
                  Register(str(full_str_reg)),
                  Register(str(start_0based_reg)),
                  Register(str(length_reg)),
              ),
          )
      )
      return result_reg
  ```

  The `no-length` fallback (`"999999"`) mirrors the pattern already used in `lower_arithmetic.py:266`.

- [ ] **Step 5: Run test to verify it passes**

  ```bash
  cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/cobol/test_condition_lowering.py::TestLowerExprNodeRefMod -x -q
  ```

  Expected: pass.

- [ ] **Step 6: Commit**

  ```bash
  git add interpreter/cobol/condition_lowering.py tests/unit/cobol/test_condition_lowering.py
  git commit -m "feat(cobol): add RefModNode branch to lower_expr_node"
  ```

---

## Task 6: Drop `parse_expression` in `lower_compute`

**Files:**
- Modify: `interpreter/cobol/lower_arithmetic.py:687-695`

- [ ] **Step 1: Change `lower_compute`**

  Current lines 694–695:
  ```python
  expr_tree = parse_expression(stmt.expression)
  result_reg = lower_expr_node(ctx, expr_tree, layout, region_reg)
  ```

  Replace with:
  ```python
  result_reg = lower_expr_node(ctx, stmt.expression, layout, region_reg)
  ```

- [ ] **Step 2: Remove the `parse_expression` import if no longer used**

  Check line 10 of `lower_arithmetic.py`:
  ```python
  from interpreter.cobol.cobol_expression import parse_expression
  ```

  Search for any other call to `parse_expression` in the file:
  ```bash
  grep -n "parse_expression" interpreter/cobol/lower_arithmetic.py
  ```

  If only one hit (the now-deleted line), remove the import.

- [ ] **Step 3: Run the unit suite**

  ```bash
  cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/ -x -q
  ```

  Expected: all pass.

- [ ] **Step 4: Commit**

  ```bash
  git add interpreter/cobol/lower_arithmetic.py
  git commit -m "feat(cobol): lower_compute passes ExprNode directly, drops parse_expression"
  ```

---

## Task 7: Integration tests — `TestComputeRefMod`

**Files:**
- Modify: `tests/integration/test_cobol_programs.py`

- [ ] **Step 1: Write the failing integration tests**

  Find the `TestComputeRefMod` location (add near other `TestCompute*` classes). Add:

  ```python
  class TestComputeRefMod:
      """COMPUTE WS-RESULT = WS-FIELD(start:length) reference modification."""

      @covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)
      def test_compute_ref_mod_simple(self):
          """WS-FIELD(1:3) extracts first 3 characters → numeric 123."""
          src = textwrap.dedent("""\
              IDENTIFICATION DIVISION.
              PROGRAM-ID. TEST.
              DATA DIVISION.
              WORKING-STORAGE SECTION.
              01 WS-FIELD PIC X(6) VALUE '123ABC'.
              01 WS-RESULT PIC 9(5).
              PROCEDURE DIVISION.
              COMPUTE WS-RESULT = WS-FIELD(1:3)
              STOP RUN.
          """)
          result = run(src)
          assert field_bytes(result, "WS-RESULT") == encode_display(123, 5)

      @covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)
      def test_compute_ref_mod_offset(self):
          """WS-FIELD(4:3) extracts characters 4-6 → numeric 456."""
          src = textwrap.dedent("""\
              IDENTIFICATION DIVISION.
              PROGRAM-ID. TEST.
              DATA DIVISION.
              WORKING-STORAGE SECTION.
              01 WS-FIELD PIC X(6) VALUE 'XXX456'.
              01 WS-RESULT PIC 9(5).
              PROCEDURE DIVISION.
              COMPUTE WS-RESULT = WS-FIELD(4:3)
              STOP RUN.
          """)
          result = run(src)
          assert field_bytes(result, "WS-RESULT") == encode_display(456, 5)

      @covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)
      def test_compute_ref_mod_in_expression(self):
          """WS-FIELD(1:3) + 5 — ref_mod result participates in arithmetic."""
          src = textwrap.dedent("""\
              IDENTIFICATION DIVISION.
              PROGRAM-ID. TEST.
              DATA DIVISION.
              WORKING-STORAGE SECTION.
              01 WS-FIELD PIC X(5) VALUE '010XY'.
              01 WS-RESULT PIC 9(5).
              PROCEDURE DIVISION.
              COMPUTE WS-RESULT = WS-FIELD(1:3) + 5
              STOP RUN.
          """)
          result = run(src)
          assert field_bytes(result, "WS-RESULT") == encode_display(15, 5)

      @covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)
      def test_compute_ref_mod_multiply(self):
          """WS-FIELD(1:3) * 4 — ref_mod operand in multiplication."""
          src = textwrap.dedent("""\
              IDENTIFICATION DIVISION.
              PROGRAM-ID. TEST.
              DATA DIVISION.
              WORKING-STORAGE SECTION.
              01 WS-FIELD PIC X(5) VALUE '003XY'.
              01 WS-RESULT PIC 9(5).
              PROCEDURE DIVISION.
              COMPUTE WS-RESULT = WS-FIELD(1:3) * 4
              STOP RUN.
          """)
          result = run(src)
          assert field_bytes(result, "WS-RESULT") == encode_display(12, 5)

      @covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)
      def test_compute_no_ref_mod_regression(self):
          """Plain COMPUTE WS-A + WS-B still works after the bridge change."""
          src = textwrap.dedent("""\
              IDENTIFICATION DIVISION.
              PROGRAM-ID. TEST.
              DATA DIVISION.
              WORKING-STORAGE SECTION.
              01 WS-A PIC 9(3) VALUE 10.
              01 WS-B PIC 9(3) VALUE 3.
              01 WS-RESULT PIC 9(5).
              PROCEDURE DIVISION.
              COMPUTE WS-RESULT = WS-A + WS-B
              STOP RUN.
          """)
          result = run(src)
          assert field_bytes(result, "WS-RESULT") == encode_display(13, 5)
  ```

  Use the same helpers (`run`, `field_bytes`, `encode_display`) as the surrounding tests. Check the existing `TestCompute*` classes for the exact helper import pattern.

- [ ] **Step 2: Run tests to verify they fail**

  ```bash
  cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/integration/test_cobol_programs.py::TestComputeRefMod -x -q
  ```

  Expected: failures (bridge JAR not yet rebuilt with Tasks 1–2 changes in the same run, OR the Python changes in Tasks 3–6 not yet in place if running tests incrementally). If all prior tasks are complete, the tests may already pass — in that case, proceed directly to Step 4.

- [ ] **Step 3: Rebuild JAR (if not done since Task 2)**

  ```bash
  cd /Users/asgupta/code/red-dragon/proleap-bridge && mvn package -q
  ```

- [ ] **Step 4: Run integration tests — verify all 5 pass**

  ```bash
  cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/integration/test_cobol_programs.py::TestComputeRefMod -x -q
  ```

  Expected: 5 tests pass.

- [ ] **Step 5: Run full regression suite**

  ```bash
  cd /Users/asgupta/code/red-dragon && poetry run python -m pytest -x -q
  ```

  Expected: all tests pass (13,000+ suite, no regressions).

- [ ] **Step 6: Format**

  ```bash
  cd /Users/asgupta/code/red-dragon && poetry run python -m black .
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add tests/integration/test_cobol_programs.py
  git commit -m "feat(cobol): add TestComputeRefMod integration tests — closes red-dragon-59y3"
  ```

---

## Verification Checklist

```bash
# Bridge builds clean
cd proleap-bridge && mvn package -q

# Unit tests pass
poetry run python -m pytest tests/unit/ -x -q

# Integration tests pass
poetry run python -m pytest tests/integration/test_cobol_programs.py::TestComputeRefMod -x -q

# Full regression clean
poetry run python -m pytest -x -q

# Feature coverage still 0 uncovered
poetry run python scripts/feature_coverage_audit.py

# Formatted
poetry run python -m black .
```
