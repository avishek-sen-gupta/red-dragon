# COBOL `GO TO … DEPENDING ON` (computed GOTO) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lower COBOL `GO TO p1 p2 … pN DEPENDING ON idx` so the `idx`-th (1-based) paragraph is branched to, with out-of-range falling through.

**Architecture:** Model `GO TO` as a sum type (`SimpleGoto | ComputedGoto | AlteredGoto`) inside `GotoStatement.form`. The ProLeap bridge (Java) serializes the variant as JSON with an explicit `form` discriminator; the Python frontend reconstructs the variant and `lower_goto` emits a chained-`BranchIf` table for the computed form.

**Tech Stack:** Python 3.13 + Poetry; Java/Maven ProLeap bridge; pytest (xdist).

**Spec:** `docs/superpowers/specs/2026-06-23-cobol-computed-goto-design.md` (issue red-dragon-b787).

## Global Constraints

- Format before every commit: `poetry run python -m black .` (use `poetry run python -m black`, NOT `poetry run black`).
- Run tests with `poetry run python -m pytest` (NOT bare `pytest`).
- Bridge/`run()` tests require the env var `PROLEAP_BRIDGE_JAR=$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar`.
- Any change to `proleap-bridge/**.java` requires rebuilding the JAR: `cd proleap-bridge && mvn -DskipTests package -q`.
- Integration tests live in `tests/integration/`, unit tests in `tests/unit/`.
- Every `test_*` method gets a `@covers(CobolFeature.MEMBER)` decorator.
- NEVER reference any external/real-world codebase (names, files, domains) in code, tests, comments, or docs. Use only synthetic COBOL.
- Do NOT run the full suite as a gate during these tasks unless a step says to; run the named tests. (Project policy for this work.)

---

### Task 1: Variant data model + bridge protocol (atomic shape change)

The bridge's JSON shape and Python's `GotoStatement.from_dict` must change together (clean break, no dual shape). This task lands both, keeps simple/altered `GO TO` working end-to-end, and makes computed `GO TO` parse into a `ComputedGoto` that reaches lowering as a temporary no-op (computed lowering is Task 2).

**Files:**
- Modify: `interpreter/cobol/cobol_statements.py` (add variant dataclasses; rewrite `GotoStatement`; extend `__all__`)
- Modify: `interpreter/cobol/lower_arithmetic.py:1563-1569` (`lower_goto` dispatch; imports)
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java` (`serializeGoTo`; new `serializeProcedureRef`; import)
- Modify: `tests/unit/test_cobol_frontend.py:539` and `tests/unit/test_cobol_statements.py:273` (update to variant shape)
- Test: `tests/unit/test_cobol_statements.py` (round-trips), `tests/integration/test_bridge_computed_goto.py` (new, real-bridge JSON)

**Interfaces:**
- Produces:
  - `ProcedureRef(paragraph: str, section: str = "")` with `from_dict`/`to_dict`
  - `SimpleGoto(target: ProcedureRef)`
  - `ComputedGoto(targets: tuple[ProcedureRef, ...], index: RefModOperand)`
  - `AlteredGoto()`
  - `GotoStatement(form: SimpleGoto | ComputedGoto | AlteredGoto)` with `from_dict`/`to_dict`
  - Bridge GOTO JSON: `{"type":"GOTO","form":"simple","target":{paragraph,section}}` | `{"type":"GOTO","form":"computed","targets":[{paragraph,section}…],"index":<serializeRef shape>}` | `{"type":"GOTO","form":"altered"}`
- Consumes: existing `RefModOperand.from_dict/to_dict` (`interpreter/cobol/ref_mod.py`); bridge helpers `extractCallName`, `extractQualifiers`, `serializeRef`, `newStatement`.

- [ ] **Step 1: Write failing unit tests for the variant dataclass round-trips**

Add to `tests/unit/test_cobol_statements.py`:

```python
from interpreter.cobol.cobol_statements import (
    GotoStatement,
    SimpleGoto,
    ComputedGoto,
    AlteredGoto,
    ProcedureRef,
)
from interpreter.cobol.ref_mod import RefModOperand


class TestGotoVariants:
    def test_simple_goto_round_trip(self):
        d = {"type": "GOTO", "form": "simple",
             "target": {"paragraph": "REAL-PARA", "section": ""}}
        stmt = GotoStatement.from_dict(d)
        assert isinstance(stmt.form, SimpleGoto)
        assert stmt.form.target == ProcedureRef(paragraph="REAL-PARA", section="")
        assert stmt.to_dict() == d

    def test_altered_goto_round_trip(self):
        d = {"type": "GOTO", "form": "altered"}
        stmt = GotoStatement.from_dict(d)
        assert isinstance(stmt.form, AlteredGoto)
        assert stmt.to_dict() == d

    def test_computed_goto_round_trip_with_structured_index(self):
        d = {"type": "GOTO", "form": "computed",
             "targets": [
                 {"paragraph": "PARA-1", "section": "SECT-A"},
                 {"paragraph": "MENU-RTN", "section": ""},
             ],
             "index": {"name": "WS-SEL", "qualifiers": ["WS-CTL"]}}
        stmt = GotoStatement.from_dict(d)
        assert isinstance(stmt.form, ComputedGoto)
        assert stmt.form.targets == (
            ProcedureRef(paragraph="PARA-1", section="SECT-A"),
            ProcedureRef(paragraph="MENU-RTN", section=""),
        )
        assert stmt.form.index == RefModOperand(name="WS-SEL", qualifiers=("WS-CTL",))
        assert stmt.to_dict() == d
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_cobol_statements.py::TestGotoVariants -v`
Expected: FAIL — `ImportError` / `AttributeError` (`SimpleGoto`, etc. do not exist; `GotoStatement` has no `form`).

- [ ] **Step 3: Implement the variant dataclasses and rewrite `GotoStatement`**

In `interpreter/cobol/cobol_statements.py`, replace the existing `GotoStatement` (lines 480-492) with:

```python
@dataclass(frozen=True)
class ProcedureRef:
    """A COBOL procedure-name: a paragraph, optionally qualified by a section.
    A bare name has section="". Procedure-names are never subscripted or
    reference-modified, so the surface is deliberately small."""

    paragraph: str
    section: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "ProcedureRef":
        return cls(paragraph=data.get("paragraph", ""), section=data.get("section", ""))

    def to_dict(self) -> dict:
        return {"paragraph": self.paragraph, "section": self.section}


@dataclass(frozen=True)
class SimpleGoto:
    """GO TO single-paragraph."""

    target: ProcedureRef


@dataclass(frozen=True)
class ComputedGoto:
    """GO TO p1 … pN DEPENDING ON index (1-based selection)."""

    targets: tuple[ProcedureRef, ...]
    index: RefModOperand


@dataclass(frozen=True)
class AlteredGoto:
    """GO TO. with no operand — target supplied by ALTER at runtime."""


@dataclass(frozen=True)
class GotoStatement:
    """GO TO — one of three mutually exclusive forms."""

    form: SimpleGoto | ComputedGoto | AlteredGoto

    @classmethod
    def from_dict(cls, data: dict) -> GotoStatement:
        form_kind = data.get("form")
        if form_kind == "computed":
            targets = tuple(
                ProcedureRef.from_dict(t) for t in data.get("targets", [])
            )
            index = RefModOperand.from_dict(data.get("index", {}))
            return cls(form=ComputedGoto(targets=targets, index=index))
        if form_kind == "altered":
            return cls(form=AlteredGoto())
        return cls(form=SimpleGoto(target=ProcedureRef.from_dict(data.get("target", {}))))

    def to_dict(self) -> dict:
        form = self.form
        if isinstance(form, ComputedGoto):
            return {
                "type": "GOTO",
                "form": "computed",
                "targets": [t.to_dict() for t in form.targets],
                "index": form.index.to_dict(),
            }
        if isinstance(form, AlteredGoto):
            return {"type": "GOTO", "form": "altered"}
        return {"type": "GOTO", "form": "simple", "target": form.target.to_dict()}
```

Add the four new names to the `__all__`/exports list near the top of the file (where `"GotoStatement",` already appears, around line 95): add `"ProcedureRef"`, `"SimpleGoto"`, `"ComputedGoto"`, `"AlteredGoto"`. Confirm `RefModOperand` is already imported at the top of the file (it is — used by `MoveStatement`).

- [ ] **Step 4: Run the round-trip tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_cobol_statements.py::TestGotoVariants -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Update `lower_goto` to dispatch on the variant**

In `interpreter/cobol/lower_arithmetic.py`, update the `cobol_statements` import block (around line 24-42) to add `SimpleGoto` and `ComputedGoto` (keep `GotoStatement`). Then replace `lower_goto` (lines 1563-1569) with:

```python
def lower_goto(
    ctx: EmitContext,
    stmt: GotoStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """GO TO — simple, computed (DEPENDING ON), or altered."""
    form = stmt.form
    if isinstance(form, SimpleGoto):
        ctx.emit_inst(Branch(label=CodeLabel(f"para_{form.target.paragraph}")))
    elif isinstance(form, ComputedGoto):
        # Computed lowering implemented in Task 2; temporary no-op (matches the
        # pre-fix fall-through behavior — no test exercises it yet).
        pass
    # AlteredGoto: GO TO. with target supplied by ALTER — no-op, behavior
    # intentionally unchanged (not exercised by any test).
```

- [ ] **Step 6: Update the two existing unit tests to the variant shape**

In `tests/unit/test_cobol_frontend.py:539`, replace `GotoStatement(target="OTHER-PARA")` with:

```python
GotoStatement(form=SimpleGoto(target=ProcedureRef(paragraph="OTHER-PARA")))
```

Add `SimpleGoto, ProcedureRef` to that file's import from `interpreter.cobol.cobol_statements` (alongside the existing `GotoStatement`).

In `tests/unit/test_cobol_statements.py:273`, if the assertion inspects `.target`, change it to inspect `stmt.form` (e.g. `assert isinstance(stmt.form, SimpleGoto)` and `stmt.form.target.paragraph == ...`). Read the surrounding test first and adjust the assertion to the variant shape; keep its intent.

- [ ] **Step 7: Run the affected Python tests**

Run: `poetry run python -m pytest tests/unit/test_cobol_statements.py tests/unit/test_cobol_frontend.py -q`
Expected: PASS (no references to the old `target: str` field remain).

- [ ] **Step 8: Implement the bridge serialization**

In `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java`:

Add the import near the other `gotostmt` import:

```java
import io.proleap.cobol.asg.metamodel.procedure.gotostmt.DependingOnPhrase;
```

Replace `serializeGoTo` (around line 795) with:

```java
private static JsonObject serializeGoTo(GoToStatement stmt) {
    JsonObject obj = newStatement("GOTO");
    try {
        if (stmt.getGoToType() == GoToStatement.GoToType.DEPENDING_ON) {
            obj.addProperty("form", "computed");
            DependingOnPhrase dep = stmt.getDependingOnPhrase();
            JsonArray targets = new JsonArray();
            for (Call c : dep.getProcedureCalls()) {
                targets.add(serializeProcedureRef(c));
            }
            obj.add("targets", targets);
            obj.add("index", serializeRef(dep.getDependingOnCall()));
        } else if (stmt.getSimple() != null
                && stmt.getSimple().getProcedureCall() != null) {
            obj.addProperty("form", "simple");
            obj.add("target", serializeProcedureRef(stmt.getSimple().getProcedureCall()));
        } else {
            obj.addProperty("form", "altered");
        }
    } catch (Exception e) {
        LOG.fine("Could not extract GOTO: " + e.getMessage());
        obj.addProperty("form", "altered");
    }
    return obj;
}

private static JsonObject serializeProcedureRef(Call call) {
    JsonObject obj = new JsonObject();
    obj.addProperty("paragraph", extractCallName(call));
    JsonArray quals = extractQualifiers(call);
    obj.addProperty("section", quals.size() > 0 ? quals.get(0).getAsString() : "");
    return obj;
}
```

Note: `Call`, `JsonArray`, `extractCallName`, `extractQualifiers`, `serializeRef`, `newStatement`, `LOG` are already imported/defined in this file. If `extractQualifiers` does not return the section qualifier for a procedure `Call`, fall back to `section=""` (the qualifier accessor is the one detail to confirm here; targets still work flat).

- [ ] **Step 9: Rebuild the bridge JAR**

Run: `cd proleap-bridge && mvn -DskipTests package -q`
Expected: build succeeds; `proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar` updated.

- [ ] **Step 10: Write a failing real-bridge JSON test**

Create `tests/integration/test_bridge_computed_goto.py`:

```python
"""The ProLeap bridge serializes GO TO ... DEPENDING ON structurally."""

import json

from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from tests.covers import covers, NotLanguageFeature
from tests.integration.cobol_helpers import bridge_jar, to_fixed


def _asg(source_lines, bridge_jar):
    parser = ProLeapCobolParser(RealSubprocessRunner(), bridge_jar)
    return json.loads(parser.parse(to_fixed(source_lines).encode("utf-8")).decode("utf-8")
                      if False else _raw(parser, source_lines))


def _raw(parser, source_lines):
    # Parse and return the raw ASG JSON string.
    return parser.parse_to_json(to_fixed(source_lines).encode("utf-8"))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bridge_emits_computed_goto_shape(bridge_jar):
    src = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. CGOTO.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-IDX PIC 9 VALUE 1.",
        "PROCEDURE DIVISION.",
        "MAIN-PARA.",
        "    GO TO P1 P2 P3 DEPENDING ON WS-IDX.",
        "    STOP RUN.",
        "P1.",
        "    STOP RUN.",
        "P2.",
        "    STOP RUN.",
        "P3.",
        "    STOP RUN.",
    ]
    raw = _raw(ProLeapCobolParser(RealSubprocessRunner(), bridge_jar), src)
    assert '"form": "computed"' in raw or '"form":"computed"' in raw
    assert '"index"' in raw
    assert "P1" in raw and "P2" in raw and "P3" in raw
```

Before relying on `_raw`, open `interpreter/cobol/cobol_parser.py` and use the actual public parse method that returns the ASG JSON (e.g. the method `parse(...)` returns; adapt `_raw` to call the real method and obtain the JSON string). Keep the assertion: the emitted JSON contains `form: computed`, an `index`, and the three target names.

- [ ] **Step 11: Run the bridge test**

Run: `PROLEAP_BRIDGE_JAR=$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/integration/test_bridge_computed_goto.py -v`
Expected: PASS (the rebuilt JAR emits the computed shape). If FAIL because `_raw`/parse method name is wrong, fix the helper to call the real parser method, not the production code.

- [ ] **Step 12: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cobol/cobol_statements.py interpreter/cobol/lower_arithmetic.py \
        proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java \
        tests/unit/test_cobol_statements.py tests/unit/test_cobol_frontend.py \
        tests/integration/test_bridge_computed_goto.py
git commit -m "feat(cobol): structured GO TO variant model + bridge serialization (red-dragon-b787)"
```

---

### Task 2: Computed GOTO lowering + integration coverage

Implements the chained-`BranchIf` branch table and proves end-to-end behavior through `run()`.

**Files:**
- Modify: `interpreter/cobol/lower_arithmetic.py` (`lower_goto` computed branch; new `_lower_computed_goto`; imports)
- Modify: `interpreter/cobol/features.py` (add `GOTO_DEPENDING_ON`)
- Test: `tests/integration/test_cobol_computed_goto.py` (new)

**Interfaces:**
- Consumes: `ComputedGoto`, `ProcedureRef`, `RefModOperand` (Task 1); `EmitContext.resolve_field_ref(name, materialised, qualifiers, subscripts) -> (ResolvedFieldRef, Register)`, `EmitContext.emit_decode_field(rr, fl, offset_reg) -> Register`, `EmitContext.const_to_reg`, `fresh_reg`, `fresh_label`, `emit_inst`; IR `Binop`, `BranchIf`, `Label_`, `Branch`, `CodeLabel`, `Register`, `resolve_binop` (all already imported in `lower_arithmetic.py`).
- Produces: working computed GOTO; `CobolFeature.GOTO_DEPENDING_ON`.

- [ ] **Step 1: Add the feature enum member**

In `interpreter/cobol/features.py`, after the `GO_TO` member (line 40), add:

```python
    GOTO_DEPENDING_ON = "GO TO p1 ... pN DEPENDING ON idx computed/indexed control transfer"
```

- [ ] **Step 2: Write the failing integration tests**

Create `tests/integration/test_cobol_computed_goto.py`:

```python
"""End-to-end: GO TO ... DEPENDING ON selects the idx-th paragraph (1-based);
out-of-range falls through."""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,
    decode_zoned_unsigned as _decode,
    first_region as _first_region,
    run_cobol,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce the required PROLEAP_BRIDGE_JAR (fails loudly if unset)."""


def _pgm(idx: int) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. CGOTO.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        f"01 WS-IDX PIC 9 VALUE {idx}.",
        "01 WS-R   PIC 9 VALUE 0.",
        "PROCEDURE DIVISION.",
        "MAIN-PARA.",
        "    GO TO P1 P2 P3 DEPENDING ON WS-IDX.",
        "    MOVE 9 TO WS-R.",
        "    STOP RUN.",
        "P1.",
        "    MOVE 1 TO WS-R.",
        "    STOP RUN.",
        "P2.",
        "    MOVE 2 TO WS-R.",
        "    STOP RUN.",
        "P3.",
        "    MOVE 3 TO WS-R.",
        "    STOP RUN.",
    ]


class TestComputedGoto:
    @pytest.mark.parametrize("idx,expected", [(1, 1), (2, 2), (3, 3), (4, 9), (0, 9)])
    @covers(CobolFeature.GOTO_DEPENDING_ON)
    def test_depending_on_selects_target_or_falls_through(self, idx: int, expected: int):
        vm = run_cobol(_pgm(idx), max_steps=2000)
        # WS-R is the second 1-digit field: WS-IDX at offset 0, WS-R at offset 1.
        assert _decode(_first_region(vm), 1, 1) == expected
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `PROLEAP_BRIDGE_JAR=$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/integration/test_cobol_computed_goto.py -v`
Expected: FAIL — `idx=1/2/3` all decode `WS-R == 9` (Task 1's no-op falls through instead of branching).

- [ ] **Step 4: Implement the computed branch table**

In `interpreter/cobol/lower_arithmetic.py`, add `_lower_computed_goto` just above `lower_goto`:

```python
def _lower_computed_goto(
    ctx: EmitContext,
    computed: ComputedGoto,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """GO TO p1 ... pN DEPENDING ON idx — branch to the idx-th (1-based) target;
    out-of-range (idx <= 0 or idx > N) falls through to the next statement."""
    index = computed.index
    ref, rr = ctx.resolve_field_ref(
        index.name, materialised, index.qualifiers, subscripts=index.subscripts
    )
    idx_reg = ctx.emit_decode_field(rr, ref.fl, ref.offset_reg)
    for k, target in enumerate(computed.targets, start=1):
        k_reg = ctx.const_to_reg(k)
        cmp_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=cmp_reg,
                operator=resolve_binop("=="),
                left=Register(str(idx_reg)),
                right=Register(str(k_reg)),
            )
        )
        match_lbl = ctx.fresh_label("goto_dep_match")
        next_lbl = ctx.fresh_label("goto_dep_next")
        ctx.emit_inst(BranchIf(cond_reg=cmp_reg, branch_targets=(match_lbl, next_lbl)))
        ctx.emit_inst(Label_(label=match_lbl))
        ctx.emit_inst(Branch(label=CodeLabel(f"para_{target.paragraph}")))
        ctx.emit_inst(Label_(label=next_lbl))
```

Then in `lower_goto`, replace the temporary `pass` in the `ComputedGoto` branch with:

```python
    elif isinstance(form, ComputedGoto):
        _lower_computed_goto(ctx, form, materialised)
```

Add `ComputedGoto` to the `cobol_statements` import in this file if not already present from Task 1 (it is).

- [ ] **Step 5: Run the integration tests to verify they pass**

Run: `PROLEAP_BRIDGE_JAR=$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/integration/test_cobol_computed_goto.py -v`
Expected: PASS (5 parametrized cases: 1→1, 2→2, 3→3, 4→9, 0→9).

- [ ] **Step 6: Add structured-index and section-resolution tests**

Append to `tests/integration/test_cobol_computed_goto.py`:

```python
    @covers(CobolFeature.GOTO_DEPENDING_ON)
    def test_depending_on_qualified_index(self):
        """The index is a qualified data item (SEL-IX OF CTL-GRP)."""
        vm = run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. CGOTOQ.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 CTL-GRP.",
                "   05 SEL-IX PIC 9 VALUE 2.",
                "01 WS-R PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    GO TO Q1 Q2 DEPENDING ON SEL-IX OF CTL-GRP.",
                "    MOVE 9 TO WS-R.",
                "    STOP RUN.",
                "Q1.",
                "    MOVE 1 TO WS-R.",
                "    STOP RUN.",
                "Q2.",
                "    MOVE 2 TO WS-R.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        # CTL-GRP/SEL-IX occupy offset 0; WS-R at offset 1.
        assert _decode(_first_region(vm), 1, 1) == 2

    @covers(CobolFeature.GOTO_DEPENDING_ON)
    def test_depending_on_section_qualified_target(self):
        """A target paragraph living inside a section still resolves and lands."""
        vm = run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. CGOTOS.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-IDX PIC 9 VALUE 1.",
                "01 WS-R   PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    GO TO TGT-PARA DEPENDING ON WS-IDX.",
                "    MOVE 9 TO WS-R.",
                "    STOP RUN.",
                "WORK-SECTION SECTION.",
                "TGT-PARA.",
                "    MOVE 1 TO WS-R.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        assert _decode(_first_region(vm), 1, 1) == 1
```

- [ ] **Step 7: Run the new tests**

Run: `PROLEAP_BRIDGE_JAR=$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/integration/test_cobol_computed_goto.py -v`
Expected: PASS (all cases). If `test_depending_on_section_qualified_target` fails because the bridge serializes the single-target DEPENDING differently, inspect the emitted JSON and confirm the target paragraph name resolves to `para_TGT-PARA`; the flat label scheme should land it.

- [ ] **Step 8: Verify no regression in simple GO TO / ALTER**

Run: `PROLEAP_BRIDGE_JAR=$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/integration/test_cobol_programs.py -k "goto or alter or Goto or Alter" -v`
Expected: PASS (existing simple-GOTO and `test_alter_compiles_and_runs` unaffected).

- [ ] **Step 9: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cobol/lower_arithmetic.py interpreter/cobol/features.py \
        tests/integration/test_cobol_computed_goto.py
git commit -m "feat(cobol): lower GO TO ... DEPENDING ON as a branch table (red-dragon-b787)"
```

- [ ] **Step 10: Run the COBOL test suite for a final regression check**

Run: `PROLEAP_BRIDGE_JAR=$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/integration/test_cobol_programs.py tests/integration/test_cobol_computed_goto.py tests/integration/test_bridge_computed_goto.py tests/unit/test_cobol_statements.py tests/unit/test_cobol_frontend.py -q`
Expected: PASS. (Full-suite run + feature-coverage audit + Beads close-out are a separate wrap-up step outside this plan.)

---

## Self-Review

**Spec coverage:**
- Data model (sum type, `ProcedureRef`, `RefModOperand` index) → Task 1 Step 3. ✓
- Bridge `form` discriminator + `serializeProcedureRef` + `serializeRef` index → Task 1 Steps 8-9. ✓
- Lowering chained `BranchIf`, free fall-through, decode-once, flat `para_{paragraph}` → Task 2 Step 4. ✓
- `SimpleGoto`/`AlteredGoto` preserved → Task 1 Step 5. ✓
- Enum `GOTO_DEPENDING_ON` → Task 2 Step 1. ✓
- Tests: dataclass round-trips (Task 1 S1), bridge JSON (Task 1 S10), integration matrix + structured index + section resolution + fall-through (Task 2 S2, S6). ✓
- Non-goal: section resolution stays flat — encoded as the lowering using `para_{paragraph}` only, `section` carried but unused. ✓
- Future work (symbol cache) — out of scope, not a task. ✓

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to". The two acknowledged build-time confirmations (the `extractQualifiers` section accessor; the exact parser method name in the bridge JSON test) are written as explicit fallback instructions, not vague gaps.

**Type consistency:** `ProcedureRef(paragraph, section)`, `ComputedGoto(targets, index)`, `GotoStatement(form)`, `_lower_computed_goto(ctx, computed, materialised)`, and `resolve_field_ref(...) -> (ref, rr)` / `emit_decode_field(rr, ref.fl, ref.offset_reg)` are used identically across both tasks.
