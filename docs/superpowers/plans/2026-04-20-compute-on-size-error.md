# COMPUTE ON SIZE ERROR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ON SIZE ERROR / NOT ON SIZE ERROR overflow detection to the COMPUTE statement (red-dragon-zdac), matching the behaviour already implemented for ADD/SUBTRACT/MULTIPLY/DIVIDE.

**Architecture:** Four layers in sequence: (1) Java bridge serializes the clauses from ProLeap ASG, (2) `ComputeStatement` dataclass gains two new fields, (3) `lower_compute` gains a fast path (no clause → unchanged) and an overflow path (OR flags across all targets, single BranchIf, all-or-nothing write), (4) integration tests verify each discrete scenario. All overflow helpers (`_compute_overflow_flag`) already exist in `lower_arithmetic.py` and are reused directly.

**Tech Stack:** Java 11 (ProLeap bridge JAR via Maven), Python 3.13, pytest, EBCDIC zoned-decimal byte assertions.

---

## File Map

| File | Change |
|------|--------|
| `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java` | Add `on_size_error` / `not_on_size_error` to `serializeCompute` |
| `interpreter/cobol/cobol_statements.py` | Extend `ComputeStatement` with two new fields |
| `interpreter/cobol/lower_arithmetic.py` | Restructure `lower_compute` with fast path + overflow path |
| `tests/integration/test_cobol_programs.py` | Add `TestComputeOnSizeError` class (4 tests) |

---

### Task 1: Java Bridge — serialize ON SIZE ERROR phrases in COMPUTE

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java:484-488`

- [ ] **Step 1: Add clause serialization before the closing `return obj;` of `serializeCompute`**

  The method currently ends at line 487 with `return obj;`. Insert these lines immediately before it (after the `if (targets.size() > 0)` block):

  ```java
  if (stmt.getOnSizeErrorPhrase() != null) {
      obj.add("on_size_error", serializeStatements(
          stmt.getOnSizeErrorPhrase().getStatements()));
  }
  if (stmt.getNotOnSizeErrorPhrase() != null) {
      obj.add("not_on_size_error", serializeStatements(
          stmt.getNotOnSizeErrorPhrase().getStatements()));
  }
  ```

  The full method after the change:

  ```java
  private static JsonObject serializeCompute(ComputeStatement stmt) {
      JsonObject obj = newStatement("COMPUTE");

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

      JsonArray targets = new JsonArray();
      for (Store store : stmt.getStores()) {
          Call storeCall = store.getStoreCall();
          if (storeCall != null) {
              targets.add(extractCallName(storeCall));
          }
      }

      if (targets.size() > 0) {
          obj.add("targets", targets);
      }

      if (stmt.getOnSizeErrorPhrase() != null) {
          obj.add("on_size_error", serializeStatements(
              stmt.getOnSizeErrorPhrase().getStatements()));
      }
      if (stmt.getNotOnSizeErrorPhrase() != null) {
          obj.add("not_on_size_error", serializeStatements(
              stmt.getNotOnSizeErrorPhrase().getStatements()));
      }
      return obj;
  }
  ```

- [ ] **Step 2: Rebuild the bridge JAR**

  ```bash
  cd proleap-bridge && mvn package -q && cd ..
  ```

  Expected: no output, exit code 0. The JAR at `proleap-bridge/target/` is updated.

- [ ] **Step 3: Commit**

  ```bash
  git add proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java
  git add proleap-bridge/target/
  git commit -m "feat(cobol-bridge): serialize ON SIZE ERROR phrases for COMPUTE statement"
  ```

---

### Task 2: AST — extend `ComputeStatement` with clause fields

**Files:**
- Modify: `interpreter/cobol/cobol_statements.py:167-185`

- [ ] **Step 1: Replace the `ComputeStatement` dataclass**

  Current (lines 167–185):

  ```python
  @dataclass(frozen=True)
  class ComputeStatement:
      """COMPUTE target = arithmetic-expression."""

      expression: str  # e.g. "WS-A + WS-B * 2"
      targets: list[str] = field(default_factory=list)  # target variable names

      @classmethod
      def from_dict(cls, data: dict) -> ComputeStatement:
          return cls(
              expression=data.get("expression", ""),
              targets=data.get("targets", []),
          )

      def to_dict(self) -> dict:
          result: dict = {"type": "COMPUTE", "expression": self.expression}
          if self.targets:
              result["targets"] = list(self.targets)
          return result
  ```

  Replace with:

  ```python
  @dataclass(frozen=True)
  class ComputeStatement:
      """COMPUTE target = arithmetic-expression."""

      expression: str  # e.g. "WS-A + WS-B * 2"
      targets: list[str] = field(default_factory=list)  # target variable names
      on_size_error: list[CobolStatement] = field(default_factory=list)
      not_on_size_error: list[CobolStatement] = field(default_factory=list)

      @classmethod
      def from_dict(cls, data: dict) -> ComputeStatement:
          return cls(
              expression=data.get("expression", ""),
              targets=data.get("targets", []),
              on_size_error=[parse_statement(c) for c in data.get("on_size_error", [])],
              not_on_size_error=[parse_statement(c) for c in data.get("not_on_size_error", [])],
          )

      def to_dict(self) -> dict:
          result: dict = {"type": "COMPUTE", "expression": self.expression}
          if self.targets:
              result["targets"] = list(self.targets)
          return result
  ```

  `CobolStatement` and `parse_statement` are already in scope in this file (used by `ArithmeticStatement` and `IfStatement` above).

- [ ] **Step 2: Run existing COMPUTE tests to confirm no regression**

  ```bash
  poetry run python -m pytest tests/ -k "compute or COMPUTE" -x -q
  ```

  Expected: all pass.

- [ ] **Step 3: Commit**

  ```bash
  git add interpreter/cobol/cobol_statements.py
  git commit -m "feat(cobol): extend ComputeStatement AST with on_size_error / not_on_size_error fields"
  ```

---

### Task 3: Lowering — restructure `lower_compute` with overflow path

**Files:**
- Modify: `interpreter/cobol/lower_arithmetic.py:387-405`

- [ ] **Step 1: Replace `lower_compute` with fast path + overflow path**

  Current (lines 387–405):

  ```python
  def lower_compute(
      ctx: EmitContext,
      stmt: ComputeStatement,
      layout: DataLayout,
      region_reg: str,
  ) -> None:
      """COMPUTE target(s) = arithmetic-expression."""
      expr_tree = parse_expression(stmt.expression)
      result_reg = lower_expr_node(ctx, expr_tree, layout, region_reg)

      result_str_reg = ctx.emit_to_string(result_reg)
      for target_name in stmt.targets:
          if not ctx.has_field(target_name, layout):
              logger.warning("COMPUTE target %s not found in layout", target_name)
              continue
          target_ref = ctx.resolve_field_ref(target_name, layout, region_reg)
          ctx.emit_encode_and_write(
              region_reg, target_ref.fl, result_str_reg, target_ref.offset_reg
          )
  ```

  Replace with:

  ```python
  def lower_compute(
      ctx: EmitContext,
      stmt: ComputeStatement,
      layout: DataLayout,
      region_reg: str,
  ) -> None:
      """COMPUTE target(s) = arithmetic-expression."""
      expr_tree = parse_expression(stmt.expression)
      result_reg = lower_expr_node(ctx, expr_tree, layout, region_reg)

      has_clause = bool(stmt.on_size_error or stmt.not_on_size_error)

      if not has_clause:
          result_str_reg = ctx.emit_to_string(result_reg)
          for target_name in stmt.targets:
              if not ctx.has_field(target_name, layout):
                  logger.warning("COMPUTE target %s not found in layout", target_name)
                  continue
              target_ref = ctx.resolve_field_ref(target_name, layout, region_reg)
              ctx.emit_encode_and_write(
                  region_reg, target_ref.fl, result_str_reg, target_ref.offset_reg
              )
          return

      on_size_err_label = ctx.fresh_label("on_size_err")
      not_on_size_err_label = ctx.fresh_label("not_on_size_err")
      end_label = ctx.fresh_label("size_err_end")

      # Resolve all valid targets up front
      target_refs = []
      for target_name in stmt.targets:
          if not ctx.has_field(target_name, layout):
              logger.warning("COMPUTE target %s not found in layout", target_name)
              continue
          target_refs.append(ctx.resolve_field_ref(target_name, layout, region_reg))

      # OR overflow flags across all targets (all-or-nothing semantics)
      overflow_flags = [
          _compute_overflow_flag(ctx, result_reg, ref.fl.type_descriptor)
          for ref in target_refs
      ]
      combined_flag = overflow_flags[0]
      for flag in overflow_flags[1:]:
          new_combined = ctx.fresh_reg()
          ctx.emit_inst(
              Binop(
                  result_reg=new_combined,
                  operator=resolve_binop("or"),
                  left=Register(str(combined_flag)),
                  right=Register(str(flag)),
              )
          )
          combined_flag = new_combined

      ctx.emit_inst(
          BranchIf(
              cond_reg=Register(str(combined_flag)),
              branch_targets=(on_size_err_label, not_on_size_err_label),
          )
      )

      ctx.emit_inst(Label_(label=on_size_err_label))
      for child in stmt.on_size_error:
          ctx.lower_statement(child, layout, region_reg)
      ctx.emit_inst(Branch(label=end_label))

      ctx.emit_inst(Label_(label=not_on_size_err_label))
      result_str_reg = ctx.emit_to_string(result_reg)
      for ref in target_refs:
          ctx.emit_encode_and_write(region_reg, ref.fl, result_str_reg, ref.offset_reg)
      for child in stmt.not_on_size_error:
          ctx.lower_statement(child, layout, region_reg)
      ctx.emit_inst(Branch(label=end_label))

      ctx.emit_inst(Label_(label=end_label))
  ```

  All names (`_compute_overflow_flag`, `Binop`, `BranchIf`, `Branch`, `Label_`, `resolve_binop`, `Register`) are already imported at the top of this file.

- [ ] **Step 2: Run existing COMPUTE tests**

  ```bash
  poetry run python -m pytest tests/ -k "compute or COMPUTE" -x -q
  ```

  Expected: all pass (no ON SIZE ERROR tests yet — those come in Task 4).

- [ ] **Step 3: Commit**

  ```bash
  git add interpreter/cobol/lower_arithmetic.py
  git commit -m "feat(cobol): add ON SIZE ERROR overflow detection to lower_compute"
  ```

---

### Task 4: Integration tests — `TestComputeOnSizeError`

**Files:**
- Modify: `tests/integration/test_cobol_programs.py` (append after the `TestOnSizeError` class, currently ending around line 3073)

Memory layout for all tests below:
- `WS-COUNTER PIC 9(3) VALUE N` → bytes 0–2 (EBCDIC zoned decimal: `0xF0`=0, `0xF1`=1, …, `0xF9`=9)
- `WS-FLAG PIC 9(1) VALUE 0` → byte 3

- [ ] **Step 1: Write the four failing tests**

  Append this class after `TestOnSizeError`:

  ```python
  class TestComputeOnSizeError:
      """Integration tests for ON SIZE ERROR / NOT ON SIZE ERROR in COMPUTE."""

      @covers(CobolFeature.ON_SIZE_ERROR)
      def test_compute_overflow_fires_on_size_error(self):
          """COMPUTE that overflows PIC 9(3) fires ON SIZE ERROR; target bytes unchanged."""
          vm = _run_cobol(
              [
                  "IDENTIFICATION DIVISION.",
                  "PROGRAM-ID. TEST-COMP-OSE.",
                  "DATA DIVISION.",
                  "WORKING-STORAGE SECTION.",
                  "01 WS-COUNTER PIC 9(3) VALUE 1.",
                  "01 WS-FLAG PIC 9(1) VALUE 0.",
                  "PROCEDURE DIVISION.",
                  "MAIN-PARA.",
                  "    COMPUTE WS-COUNTER = 999 + 1",
                  "        ON SIZE ERROR MOVE 1 TO WS-FLAG",
                  "    END-COMPUTE.",
                  "    STOP RUN.",
              ],
              max_steps=500,
          )
          region = _first_region(vm)
          assert region[3] == 0xF1, f"Expected WS-FLAG=1 (0xF1), got {hex(region[3])}"
          assert list(region[:3]) == [
              0xF0,
              0xF0,
              0xF1,
          ], f"WS-COUNTER should be unchanged (1), got {[hex(b) for b in region[:3]]}"

      @covers(CobolFeature.ON_SIZE_ERROR)
      def test_compute_no_overflow_fires_not_on_size_error(self):
          """COMPUTE that fits fires NOT ON SIZE ERROR; flag is set."""
          vm = _run_cobol(
              [
                  "IDENTIFICATION DIVISION.",
                  "PROGRAM-ID. TEST-COMP-NOSE.",
                  "DATA DIVISION.",
                  "WORKING-STORAGE SECTION.",
                  "01 WS-COUNTER PIC 9(3) VALUE 1.",
                  "01 WS-FLAG PIC 9(1) VALUE 0.",
                  "PROCEDURE DIVISION.",
                  "MAIN-PARA.",
                  "    COMPUTE WS-COUNTER = 1 + 1",
                  "        NOT ON SIZE ERROR MOVE 1 TO WS-FLAG",
                  "    END-COMPUTE.",
                  "    STOP RUN.",
              ],
              max_steps=500,
          )
          region = _first_region(vm)
          assert region[3] == 0xF1, f"Expected WS-FLAG=1 (0xF1), got {hex(region[3])}"

      @covers(CobolFeature.ON_SIZE_ERROR)
      def test_compute_multi_target_any_overflow_skips_all(self):
          """COMPUTE with two targets: one would overflow → both unchanged, ON SIZE ERROR fires."""
          vm = _run_cobol(
              [
                  "IDENTIFICATION DIVISION.",
                  "PROGRAM-ID. TEST-COMP-MULTI.",
                  "DATA DIVISION.",
                  "WORKING-STORAGE SECTION.",
                  "01 WS-A PIC 9(3) VALUE 1.",
                  "01 WS-B PIC 9(1) VALUE 2.",
                  "01 WS-FLAG PIC 9(1) VALUE 0.",
                  "PROCEDURE DIVISION.",
                  "MAIN-PARA.",
                  "    COMPUTE WS-A WS-B = 999 + 1",
                  "        ON SIZE ERROR MOVE 1 TO WS-FLAG",
                  "    END-COMPUTE.",
                  "    STOP RUN.",
              ],
              max_steps=500,
          )
          region = _first_region(vm)
          # WS-A: bytes 0-2 (PIC 9(3)), WS-B: byte 3 (PIC 9(1)), WS-FLAG: byte 4
          assert region[4] == 0xF1, f"Expected WS-FLAG=1 (0xF1), got {hex(region[4])}"
          assert list(region[:3]) == [
              0xF0,
              0xF0,
              0xF1,
          ], f"WS-A should be unchanged (1), got {[hex(b) for b in region[:3]]}"
          assert region[3] == 0xF2, f"WS-B should be unchanged (2), got {hex(region[3])}"

      @covers(CobolFeature.ON_SIZE_ERROR)
      def test_compute_no_clause_overflow_silent(self):
          """COMPUTE overflow with no clause: no Python exception, vm not None."""
          vm = _run_cobol(
              [
                  "IDENTIFICATION DIVISION.",
                  "PROGRAM-ID. TEST-COMP-NOCL.",
                  "DATA DIVISION.",
                  "WORKING-STORAGE SECTION.",
                  "01 WS-COUNTER PIC 9(3) VALUE 1.",
                  "PROCEDURE DIVISION.",
                  "MAIN-PARA.",
                  "    COMPUTE WS-COUNTER = 999 + 1.",
                  "    STOP RUN.",
              ],
              max_steps=500,
          )
          assert vm is not None
  ```

- [ ] **Step 2: Run just these tests to confirm they fail (no implementation yet)**

  These tests depend on Task 3 already being complete — they should **pass** after Task 3. Run them to confirm:

  ```bash
  poetry run python -m pytest tests/integration/test_cobol_programs.py::TestComputeOnSizeError -x -q
  ```

  Expected: all 4 pass.

- [ ] **Step 3: Run the full test suite**

  ```bash
  poetry run python -m pytest -x -q
  ```

  Expected: all tests pass (count should be ≥ 13,641).

- [ ] **Step 4: Format**

  ```bash
  poetry run python -m black .
  ```

  Expected: no files changed (or only whitespace fixes).

- [ ] **Step 5: Commit**

  ```bash
  git add tests/integration/test_cobol_programs.py
  git commit -m "test(cobol): add TestComputeOnSizeError integration tests — closes red-dragon-zdac"
  ```

---

## Self-Review

**Spec coverage:**
- ✅ Java bridge: Task 1
- ✅ AST two new fields + `from_dict`: Task 2
- ✅ Fast path unchanged: Task 3 (fast path preserved at top of new `lower_compute`)
- ✅ All-or-nothing OR across targets: Task 3 (overflow_flags list + OR chain)
- ✅ Single BranchIf → three-label structure: Task 3
- ✅ Result written only in `not_on_size_err` branch: Task 3
- ✅ 4 integration tests, one scenario each: Task 4
- ✅ Div-by-zero in expressions: explicitly out of scope — no task needed

**Placeholder scan:** No TBD, no TODO, no "similar to Task N". All code is complete.

**Type consistency:**
- `_compute_overflow_flag(ctx, result_reg, ref.fl.type_descriptor)` — `result_reg` is `str` (returned by `lower_expr_node`), `ref.fl.type_descriptor` is `CobolTypeDescriptor`. Matches the existing signature at `lower_arithmetic.py:56`.
- `ctx.lower_statement(child, layout, region_reg)` — matches how `lower_arithmetic_giving` calls it at line 373.
- `ctx.fresh_label("on_size_err")` — matches label naming convention in `lower_arithmetic_giving` at line 299.
- `parse_statement` in `ComputeStatement.from_dict` — same function used by `ArithmeticStatement.from_dict` at line 150.
