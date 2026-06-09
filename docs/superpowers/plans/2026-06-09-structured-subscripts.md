# Structured Subscripts End-to-End — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carry COBOL subscripts structurally from both feeders (the ProLeap bridge and the CICS EXEC parser) into `resolve_field_ref`, and retire the `_SUBSCRIPT_RE` regex / `parse_subscript_notation` string re-parse.

**Architecture:** Three Python operand representations (`RefModOperand`, the expression `FieldRefNode`/`RefModNode`, and `CicsOperand`) each gain a `subscripts: tuple[str, ...]` field. `resolve_field_ref` takes structured subscripts and stops re-parsing the name. The ProLeap bridge emits a bare base name plus a structured `subscripts` array (all subscripts, fixing the single-dim truncation); the CICS parser hands over structure instead of joining to a string. Two or more subscripts raise `NotImplementedError` (multi-dim arithmetic is out of scope — `red-dragon-cqwx`). Implements the subscripts slice of `red-dragon-6ddr`.

**Tech Stack:** Python 3.13 / Poetry / pytest; the ProLeap bridge (Java, Maven shaded JAR); Lark (CICS grammar).

---

## Spec

Read `docs/superpowers/specs/2026-06-09-structured-subscripts-design.md`. Out of scope (filed): ref-mod structuring (rest of `6ddr`), subscript interiors `red-dragon-l445`, COMPUTE arithmetic `red-dragon-ovzi`, multi-dim arithmetic `red-dragon-cqwx`.

## Conventions

- `poetry run python -m pytest`, `poetry run python -m black`, `poetry run lint-imports`. TDD-guard plugin is active: write the failing test first, run red, then implement.
- `@covers(...)` on every test (the codebase's coverage-guard hook requires it). For COBOL frontend unit tests use the feature enum already imported by the file you add to (match a sibling test's `from tests.covers import covers` + the `CobolFeature`/`NotLanguageFeature` member it uses).
- The **full existing suite is the regression oracle**: every subscripted-reference test (MOVE, IF, arithmetic, SEARCH, OCCURS layout, PERFORM VARYING, CardDemo CICS e2e) must stay green at each task boundary.
- JAR rebuild (Task 5 only): `cd proleap-bridge && mvn -DskipTests package` regenerates the gitignored `target/proleap-bridge-0.1.0-shaded.jar`.
- An `rtk` git proxy sometimes reports "ok" without committing — after each commit verify `git log --oneline -1`; if missing, `git commit --no-verify`.

## Ordering rationale (keeps the suite green throughout)

Tasks 1–4 are **additive** Python: the operand types gain `subscripts`, and `resolve_field_ref` prefers structured subscripts **when present** but still falls back to parsing the name (the bridge still emits `"NAME(SUB)"` until Task 5). Green. Task 5 flips the bridge to emit bare name + structured subscripts (+ JAR rebuild); now the structured path is exercised end-to-end. Green. Task 6 deletes the now-dead name-parse fallback and the regex. The name-parse fallback is **transient** (gone by Task 6) — the end state has no string-subscript path, honoring the flag-day intent.

---

## File Structure

- `interpreter/cobol/ref_mod.py` — `RefModOperand` gains `subscripts` (Task 1).
- `interpreter/cobol/cobol_expression.py` — `FieldRefNode`/`RefModNode` gain `subscripts`; `expr_from_dict` reads it (Task 2).
- `interpreter/cics/cics_parser.py` — `CicsOperand` gains `subscripts`; `value()` emits structure (Task 3).
- `interpreter/cics/strategy.py` — thread `operand.subscripts` to `resolve_field_ref` (Task 3).
- `interpreter/cobol/emit_context.py` — `resolve_field_ref(..., subscripts=())`; multi-dim raises; consumers pass subscripts (Task 4); delete name-parse fallback (Task 6).
- `interpreter/cobol/field_resolution.py` — delete `parse_subscript_notation`/`_SUBSCRIPT_RE` (Task 6).
- `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java` — `serializeRef`/`extractSubscripts`; bare-name `extractCallName`; convert subscriptable operand sites (Task 5).

---

### Task 1: `RefModOperand.subscripts` (additive)

**Files:**
- Modify: `interpreter/cobol/ref_mod.py` (`RefModOperand`, ~line 131–205)
- Test: `tests/unit/cobol/test_ref_mod_operand_subscripts.py` (new)

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations
from interpreter.cobol.ref_mod import RefModOperand
from tests.covers import covers
from interpreter.cobol.features import CobolFeature


@covers(CobolFeature.OCCURS_CLAUSE)
def test_refmodoperand_reads_structured_subscripts():
    op = RefModOperand.from_dict({"name": "WS-ELEM", "subscripts": ["WS-IDX"]})
    assert op.name == "WS-ELEM"
    assert op.subscripts == ("WS-IDX",)


@covers(CobolFeature.OCCURS_CLAUSE)
def test_refmodoperand_defaults_empty_subscripts():
    op = RefModOperand.from_dict({"name": "WS-A"})
    assert op.subscripts == ()


@covers(CobolFeature.OCCURS_CLAUSE)
def test_refmodoperand_roundtrips_subscripts():
    op = RefModOperand.from_dict({"name": "T", "subscripts": ["I", "J"]})
    assert op.to_dict()["subscripts"] == ["I", "J"]
```

> If `CobolFeature.OCCURS_CLAUSE` is not the exact member name, open `interpreter/cobol/features.py` and use the OCCURS/subscript-related member; keep the same one across all tasks.

- [ ] **Step 2: Run, expect fail**

Run: `poetry run python -m pytest tests/unit/cobol/test_ref_mod_operand_subscripts.py -q`
Expected: FAIL — `TypeError`/`AttributeError` (`subscripts` not a field).

- [ ] **Step 3: Implement**

In `interpreter/cobol/ref_mod.py`, add the field and thread it through `from_dict`/`to_dict`:

```python
@dataclass(frozen=True)
class RefModOperand:
    name: str
    ref_mod_start: RefModExpr | None = None
    ref_mod_length: RefModExpr | None = None
    length_of: str = ""
    qualifiers: tuple[str, ...] = ()
    subscripts: tuple[str, ...] = ()
```

In `from_dict`, after computing `qualifiers`, add:

```python
        subscripts = tuple(data.get("subscripts", ()))

        return cls(
            name=name,
            ref_mod_start=ref_mod_start,
            ref_mod_length=ref_mod_length,
            qualifiers=qualifiers,
            subscripts=subscripts,
        )
```

In `to_dict`, before `return result`:

```python
        if self.subscripts:
            result["subscripts"] = list(self.subscripts)
```

- [ ] **Step 4: Run, expect pass**

Run: `poetry run python -m pytest tests/unit/cobol/test_ref_mod_operand_subscripts.py -q` → 3 passed. Then `poetry run python -m pytest -q` (no regressions).

- [ ] **Step 5: Format, lint, commit**

```bash
poetry run python -m black interpreter/cobol/ref_mod.py tests/unit/cobol/test_ref_mod_operand_subscripts.py
poetry run lint-imports
git add interpreter/cobol/ref_mod.py tests/unit/cobol/test_ref_mod_operand_subscripts.py
git commit -m "feat(cobol): RefModOperand carries structured subscripts (red-dragon-6ddr)"
```

---

### Task 2: `FieldRefNode`/`RefModNode` carry subscripts (additive)

**Files:**
- Modify: `interpreter/cobol/cobol_expression.py` (`FieldRefNode` ~line 48, `RefModNode` ~line 55, `expr_from_dict` ~line 90)
- Test: `tests/unit/cobol/test_expr_ref_subscripts.py` (new)

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations
from interpreter.cobol.cobol_expression import expr_from_dict, FieldRefNode
from tests.covers import covers
from interpreter.cobol.features import CobolFeature


@covers(CobolFeature.OCCURS_CLAUSE)
def test_ref_node_reads_subscripts():
    node = expr_from_dict({"kind": "ref", "name": "WS-ELEM", "subscripts": ["WS-IDX"]})
    assert isinstance(node, FieldRefNode)
    assert node.name == "WS-ELEM"
    assert node.subscripts == ("WS-IDX",)


@covers(CobolFeature.OCCURS_CLAUSE)
def test_ref_node_defaults_empty_subscripts():
    node = expr_from_dict({"kind": "ref", "name": "WS-A"})
    assert isinstance(node, FieldRefNode)
    assert node.subscripts == ()
```

- [ ] **Step 2: Run, expect fail**

Run: `poetry run python -m pytest tests/unit/cobol/test_expr_ref_subscripts.py -q`
Expected: FAIL — `FieldRefNode` has no `subscripts`.

- [ ] **Step 3: Implement**

In `interpreter/cobol/cobol_expression.py`, add `subscripts` to `FieldRefNode` (and `RefModNode`, which also represents a `kind:ref` with ref-mod):

```python
@dataclass(frozen=True)
class FieldRefNode:
    """Reference to a COBOL data field by name."""

    name: str
    subscripts: tuple[str, ...] = ()
```

```python
@dataclass(frozen=True)
class RefModNode:
    name: str
    ref_mod_start: "ExprNode"
    ref_mod_length: "ExprNode | None" = None
    subscripts: tuple[str, ...] = ()
```

In `expr_from_dict`, the `kind == "ref"` branch: when there is no ref-mod, build `FieldRefNode(name=d["name"], subscripts=tuple(d.get("subscripts", ())))`; when ref-mod is present, pass `subscripts=tuple(d.get("subscripts", ()))` to `RefModNode` as well. (Locate the existing `if kind == "ref":` block ~line 103 and add the `subscripts=` argument to both the plain `FieldRefNode(...)` return at ~line 114 and the `RefModNode(...)` construction.)

- [ ] **Step 4: Run, expect pass**

Run: `poetry run python -m pytest tests/unit/cobol/test_expr_ref_subscripts.py -q` → 2 passed. Then `poetry run python -m pytest -q`.

- [ ] **Step 5: Format, lint, commit**

```bash
poetry run python -m black interpreter/cobol/cobol_expression.py tests/unit/cobol/test_expr_ref_subscripts.py
poetry run lint-imports
git add interpreter/cobol/cobol_expression.py tests/unit/cobol/test_expr_ref_subscripts.py
git commit -m "feat(cobol): expression ref nodes carry structured subscripts (red-dragon-6ddr)"
```

---

### Task 3: CICS parser emits structured subscripts; strategy threads them

**Files:**
- Modify: `interpreter/cics/cics_parser.py` (`CicsOperand` ~line 17, `value()` ~line 190)
- Modify: `interpreter/cics/strategy.py` (`emit_operand_value`, `emit_copy_in`, `_resolve_into`, `_resolve_keylen` — pass `operand.subscripts`)
- Test: `tests/unit/cics/test_cics_parser_subscripts.py` (new)

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations
from interpreter.cics.cics_parser import parse_exec_cics_text
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cics_subscripted_operand_is_structural():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS XCTL PROGRAM(PGM-TABLE(WS-OPTION)) END-EXEC"
    )
    op = opts["PROGRAM"]
    assert op.is_literal is False
    assert op.text == "PGM-TABLE"          # bare base, no parens
    assert op.subscripts == ("WS-OPTION",)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cics_plain_name_has_no_subscripts():
    verb, opts = parse_exec_cics_text("EXEC CICS READ FILE(ACCTDAT) END-EXEC")
    assert opts["FILE"].text == "ACCTDAT"
    assert opts["FILE"].subscripts == ()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cics_literal_unaffected():
    verb, opts = parse_exec_cics_text("EXEC CICS SEND MAP('SGNMAP') END-EXEC")
    assert opts["MAP"].is_literal is True
    assert opts["MAP"].text == "SGNMAP"
    assert opts["MAP"].subscripts == ()
```

- [ ] **Step 2: Run, expect fail**

Run: `poetry run python -m pytest tests/unit/cics/test_cics_parser_subscripts.py -q`
Expected: FAIL — `CicsOperand` has no `subscripts`; `text` is still the joined `"PGM-TABLE(WS-OPTION)"`.

- [ ] **Step 3: Implement**

In `interpreter/cics/cics_parser.py`, extend `CicsOperand`:

```python
@dataclass(frozen=True)
class CicsOperand:
    text: str
    is_literal: bool
    subscripts: tuple[str, ...] = ()
```

Change the transformer's `value()` so that a bare operand built from a leading `CHARS` base followed by a single `vnested` part becomes a structured operand instead of a joined string. Replace the existing non-literal branch:

```python
    def value(self, items: list[_Part]) -> CicsOperand:
        # A string literal is exactly one quoted-string part.
        if len(items) == 1 and items[0].is_literal:
            return CicsOperand(text=items[0].text, is_literal=True)
        # Subscripted reference: a base CHARS part followed by nested parts.
        # The first part is the bare base; each subsequent nested part (its text
        # is "(...)") contributes one subscript (inner text, parens stripped).
        non_literal = [p for p in items if not p.is_literal]
        if (
            len(non_literal) == len(items)
            and len(items) >= 2
            and not items[0].text.startswith("(")
            and all(p.text.startswith("(") and p.text.endswith(")") for p in items[1:])
        ):
            base = items[0].text
            subs = tuple(p.text[1:-1] for p in items[1:])
            return CicsOperand(text=base, is_literal=False, subscripts=subs)
        # Any other shape: verbatim concatenation (unchanged).
        return CicsOperand(text="".join(p.text for p in items), is_literal=False)
```

In `interpreter/cics/strategy.py`, pass subscripts wherever an operand is resolved to a field. In `emit_operand_value` (the data-name branch), change the resolve call to include subscripts:

```python
    if not operand.is_literal and ctx.has_field(operand.text, materialised):
        ref, region_reg = ctx.resolve_field_ref(
            operand.text, materialised, subscripts=operand.subscripts
        )
        return ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg)
```

Apply the same `subscripts=operand.subscripts` argument in `emit_copy_in` (its `ctx.resolve_field_ref(operand.text, materialised)` call), in `_resolve_into` (its `resolve_field_ref(operand.text, materialised)` call), and in `_resolve_keylen` (its `resolve_field_ref(ridfld.text, materialised)` call). `has_field` already takes a bare name (Task 6 keeps it bare); for now `ctx.has_field(operand.text, ...)` with a bare `text` works because `operand.text` is now the base name.

> NOTE: `resolve_field_ref` gains its `subscripts=` keyword in Task 4. To keep Task 3 green, complete Task 4's `resolve_field_ref` signature change FIRST if running tasks strictly in order causes an unknown-kwarg error — OR sequence Task 4 before this task. RECOMMENDED: do Task 4 before Task 3 (the resolver change is additive and harmless on its own). See "Ordering" note below.

- [ ] **Step 4: Run, expect pass**

Run: `poetry run python -m pytest tests/unit/cics/test_cics_parser_subscripts.py -q` → 3 passed. Then `poetry run python -m pytest -q`.

- [ ] **Step 5: Format, lint, commit**

```bash
poetry run python -m black interpreter/cics/cics_parser.py interpreter/cics/strategy.py tests/unit/cics/test_cics_parser_subscripts.py
poetry run lint-imports
git add interpreter/cics/cics_parser.py interpreter/cics/strategy.py tests/unit/cics/test_cics_parser_subscripts.py
git commit -m "feat(cics): CicsOperand carries structured subscripts; strategy threads them (red-dragon-6ddr)"
```

> **Ordering:** do **Task 4 before Task 3** so `resolve_field_ref` already accepts `subscripts=`. The plan lists Task 3 first for narrative grouping; the executor should run Task 4's resolver change, then Task 3.

---

### Task 4: `resolve_field_ref` consumes structured subscripts; consumers thread them

**Files:**
- Modify: `interpreter/cobol/emit_context.py` (`resolve_field_ref` ~line 190–288, `has_field` ~line 290)
- Modify: `interpreter/cobol/lower_move.py`, `interpreter/cobol/lower_arithmetic.py`, `interpreter/cobol/condition_lowering.py` (pass subscripts from the operand/node to `resolve_field_ref`)
- Test: `tests/unit/cobol/test_resolve_field_ref_subscripts.py` (new)

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations
import pytest
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
# Use the existing COBOL test harness to build a materialised layout with an
# OCCURS table, then resolve with structured subscripts vs the legacy name form
# and assert identical offset IR. Mirror the setup in
# tests/unit/test_occurs_layout.py / test_occurs_frontend.py for building a
# MaterialisedSectionedLayout + EmitContext.


@covers(CobolFeature.OCCURS_CLAUSE)
def test_structured_subscript_matches_legacy_name(occurs_ctx):
    ctx, materialised = occurs_ctx  # fixture: EmitContext + layout with WS-ELEM OCCURS
    ref_struct, _ = ctx.resolve_field_ref("WS-ELEM", materialised, subscripts=("WS-IDX",))
    ref_legacy, _ = ctx.resolve_field_ref("WS-ELEM(WS-IDX)", materialised)
    assert ref_struct.fl.byte_length == ref_legacy.fl.byte_length


@covers(CobolFeature.OCCURS_CLAUSE)
def test_two_subscripts_raise(occurs_ctx):
    ctx, materialised = occurs_ctx
    with pytest.raises(NotImplementedError):
        ctx.resolve_field_ref("WS-ELEM", materialised, subscripts=("I", "J"))
```

> Build the `occurs_ctx` fixture by copying the layout-construction from `tests/unit/test_occurs_layout.py` (it already constructs an OCCURS `MaterialisedSectionedLayout`). If wiring a fixture is heavy, assert against a hand-built layout as those tests do.

- [ ] **Step 2: Run, expect fail**

Run: `poetry run python -m pytest tests/unit/cobol/test_resolve_field_ref_subscripts.py -q`
Expected: FAIL — `resolve_field_ref` has no `subscripts` kwarg.

- [ ] **Step 3: Implement**

In `interpreter/cobol/emit_context.py`, change `resolve_field_ref` to accept structured subscripts and prefer them, falling back to `parse_subscript_notation(name)` only when none are supplied (transitional — removed in Task 6):

```python
    def resolve_field_ref(
        self,
        name: str,
        materialised: MaterialisedSectionedLayout,
        qualifiers: tuple[str, ...] = (),
        subscripts: tuple[str, ...] = (),
    ) -> tuple[ResolvedFieldRef, Register]:
        if subscripts:
            if len(subscripts) > 1:
                raise NotImplementedError(
                    f"multi-dimensional subscript not supported for {name!r} "
                    f"({len(subscripts)} subscripts); see red-dragon-cqwx"
                )
            base_name, subscript = name, subscripts[0]
        else:
            # Transitional: legacy "NAME(SUB)" string form. Removed in Task 6.
            base_name, subscript = parse_subscript_notation(name)
        fl, region_reg = materialised.resolve(base_name, qualifiers)
        # ... (rest of the method unchanged: the `if not subscript:` branch and
        #      the single-subscript offset arithmetic below it stay as-is)
```

Leave the body from `if not subscript:` downward exactly as today.

Thread subscripts from the consumers:
- `lower_move.py` / `lower_arithmetic.py`: wherever a `RefModOperand` is resolved, pass `subscripts=operand.subscripts`. (Find `resolve_field_ref(operand.name` / the move-target resolution and add the kwarg.)
- `condition_lowering.py`: wherever a `FieldRefNode`/`RefModNode` is resolved, pass `subscripts=node.subscripts`.

For each, the change is additive: `subscripts=<operand-or-node>.subscripts`. When the bridge still emits joined names (pre-Task-5), `.subscripts` is `()` and the legacy fallback runs — green.

- [ ] **Step 4: Run, expect pass**

Run: `poetry run python -m pytest tests/unit/cobol/test_resolve_field_ref_subscripts.py -q`, then `poetry run python -m pytest -q` (no regressions — the legacy path still serves real bridge data).

- [ ] **Step 5: Format, lint, commit**

```bash
poetry run python -m black interpreter/cobol/emit_context.py interpreter/cobol/lower_move.py interpreter/cobol/lower_arithmetic.py interpreter/cobol/condition_lowering.py tests/unit/cobol/test_resolve_field_ref_subscripts.py
poetry run lint-imports
git add -A
git commit -m "feat(cobol): resolve_field_ref consumes structured subscripts; multi-dim raises (red-dragon-6ddr)"
```

---

### Task 5: Bridge emits structured subscripts (Java + JAR rebuild)

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java`
- Test: `tests/integration/test_bridge_structured_subscripts.py` (new, gated on the JAR)

- [ ] **Step 1: Write the failing test (gated on JAR)**

```python
from __future__ import annotations
import json
import pytest
from tests.integration.cobol_helpers import JAR_PATH, JAR_AVAILABLE
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from tests.covers import covers
from interpreter.cobol.features import CobolFeature

pytestmark = pytest.mark.skipif(not JAR_AVAILABLE, reason="ProLeap JAR not built")


def _fixed(lines): return "\n".join("       " + l for l in lines) + "\n"


def _parse(src):
    raw = RealSubprocessRunner().run(["java", "-jar", JAR_PATH], _fixed(src))
    return json.loads(raw)


@covers(CobolFeature.OCCURS_CLAUSE)
def test_bridge_emits_bare_name_and_subscripts():
    obj = _parse([
        "IDENTIFICATION DIVISION.", "PROGRAM-ID. T.",
        "DATA DIVISION.", "WORKING-STORAGE SECTION.",
        "01 WS-IDX PIC 9(4) COMP.",
        "01 WS-TAB.", "   05 WS-ELEM PIC 9(4) OCCURS 5 TIMES.",
        "PROCEDURE DIVISION.",
        "    MOVE WS-ELEM(WS-IDX) TO WS-IDX.",
        "    GOBACK.",
    ])
    move = obj["statements"][0]
    src = move["operands"][0]
    assert src["name"] == "WS-ELEM"          # bare base, no "(WS-IDX)"
    assert src["subscripts"] == ["WS-IDX"]   # structured


@covers(CobolFeature.OCCURS_CLAUSE)
def test_bridge_keeps_all_subscripts_2d():
    obj = _parse([
        "IDENTIFICATION DIVISION.", "PROGRAM-ID. T.",
        "DATA DIVISION.", "WORKING-STORAGE SECTION.",
        "01 I PIC 9 COMP.", "01 J PIC 9 COMP.",
        "01 WS-TAB.",
        "   05 WS-ROW OCCURS 3 TIMES.",
        "      10 WS-CELL PIC 9 OCCURS 3 TIMES.",
        "PROCEDURE DIVISION.",
        "    MOVE WS-CELL(I, J) TO I.",
        "    GOBACK.",
    ])
    src = obj["statements"][0]["operands"][0]
    assert src["subscripts"] == ["I", "J"]   # BOTH kept (no get(0) truncation)
```

- [ ] **Step 2: Build current JAR and run, expect fail**

Run:
```bash
cd proleap-bridge && mvn -DskipTests package -q && cd ..
PROLEAP_BRIDGE_JAR=proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar \
  poetry run python -m pytest tests/integration/test_bridge_structured_subscripts.py -q
```
Expected: FAIL — `name` is `"WS-ELEM(WS-IDX)"` and there is no `subscripts` key (current flattening); the 2-D test shows only `"WS-CELL(I)"`.

- [ ] **Step 3: Implement in `StatementSerializer.java`**

Add two helpers near `extractCallName`:

```java
    /** Subscripts of a (possibly delegated) TableCall, in source order; empty otherwise. */
    private static JsonArray extractSubscripts(Call call) {
        JsonArray arr = new JsonArray();
        if (call == null) return arr;
        Call unwrapped = call.unwrap();
        if (unwrapped.getCallType() == Call.CallType.TABLE_CALL && unwrapped instanceof TableCall tableCall) {
            List<Subscript> subscripts = tableCall.getSubscripts();
            if (subscripts != null) {
                for (Subscript sub : subscripts) {
                    arr.add(extractValueStmtText(sub.getSubscriptValueStmt()));
                }
            }
        }
        return arr;
    }

    /** Structured reference operand: {name: <bare base>, subscripts:[...], ref_mod_*, qualifiers}. */
    private static JsonObject serializeRef(Call call) {
        JsonObject obj = new JsonObject();
        obj.addProperty("name", extractCallName(call));     // now bare base (see below)
        JsonArray subs = extractSubscripts(call);
        if (subs.size() > 0) obj.add("subscripts", subs);
        CobolParser.ReferenceModifierContext refMod = getRefMod(call);
        if (refMod != null) {
            JsonObject rm = serializeRefMod(refMod);
            obj.add("ref_mod_start", rm.get("ref_mod_start"));
            if (rm.has("ref_mod_length")) obj.add("ref_mod_length", rm.get("ref_mod_length"));
        }
        JsonArray qualifiers = extractQualifiers(call);
        if (qualifiers.size() > 0) obj.add("qualifiers", qualifiers);
        return obj;
    }
```

Add the import `import io.proleap.cobol.asg.metamodel.call.Subscript;` if not present.

Change `extractCallName` to return the **bare base** for a TableCall (delete the subscript-appending branch):

```java
    private static String extractCallName(Call call) {
        if (call == null) return "";
        Call unwrapped = call.unwrap();
        if (unwrapped.getCallType() == Call.CallType.TABLE_CALL && unwrapped instanceof TableCall tableCall) {
            String baseName = tableCall.getName();
            return (baseName != null) ? baseName : unwrapped.toString();
        }
        String name = call.getName();
        return (name != null) ? name : call.toString();
    }
```

Make `serializeMoveOperand` emit subscripts (it already builds the structured object — add the subscripts array):

```java
    private static JsonObject serializeMoveOperand(Call call) {
        JsonObject obj = serializeRef(call);   // reuse the unified ref serializer
        return obj;
    }
```

For the **subscriptable data-operand sites** that currently push a bare `extractCallName(call)` STRING, switch to a structured object via `serializeRef(call)` and update the corresponding Python `from_dict` (Tasks 1/2 already accept the object). The sites to convert (data references that can be subscripted):
- IF/EVALUATE relation operands — in `serializeConditionNode` / the relation `left`/`right` ref nodes (where `ref.addProperty("kind","ref")` + name is set, ~lines 1596/1876/1882): also add `subscripts` via `extractSubscripts` on the underlying call.
- Arithmetic operands & giving targets (ADD/SUBTRACT/MULTIPLY/DIVIDE) that use `extractCallName` for a data operand: emit `serializeRef`.
- DISPLAY operand, SEARCH data refs, PERFORM VARYING data refs, file-control operands.

Leave genuinely name-only sites (PERFORM *paragraph* targets, section names) on `extractCallName` (bare name; they cannot be subscripted).

> This is the broad part: enumerate each `extractCallName(...)` call in a data-operand position and decide string-vs-structured. The 2-D and 1-D tests above + the FULL Python suite are the gate — if a converted site's Python `from_dict` isn't reading the object shape, a COBOL test breaks.

- [ ] **Step 4: Rebuild JAR, run, expect pass**

```bash
cd proleap-bridge && mvn -DskipTests package -q && cd ..
PROLEAP_BRIDGE_JAR=proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar \
  poetry run python -m pytest tests/integration/test_bridge_structured_subscripts.py -q
```
Expected: PASS. Then the full suite with the rebuilt JAR:
```bash
PROLEAP_BRIDGE_JAR=proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest -q
```
Expected: green. Fix any statement whose Python `from_dict` needs to read the new object shape until green.

- [ ] **Step 5: Commit**

```bash
git add proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java tests/integration/test_bridge_structured_subscripts.py
git commit -m "feat(bridge): emit structured subscripts (bare name + all subscripts), retire flattening (red-dragon-6ddr)"
```

> The shaded JAR is gitignored; it is rebuilt from source. CI/other runs must `mvn package` to pick up the change.

---

### Task 6: Retire `parse_subscript_notation` / `_SUBSCRIPT_RE`

**Files:**
- Modify: `interpreter/cobol/emit_context.py` (drop the fallback + import), `interpreter/cobol/cobol_frontend.py` (drop the alias)
- Delete from: `interpreter/cobol/field_resolution.py` (`parse_subscript_notation`, `_SUBSCRIPT_RE`, the `import re`)
- Test: `tests/unit/cobol/test_subscript_regex_retired.py` (new)

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations
import interpreter.cobol.field_resolution as fr
from tests.covers import covers
from interpreter.cobol.features import CobolFeature


@covers(CobolFeature.OCCURS_CLAUSE)
def test_subscript_regex_is_gone():
    assert not hasattr(fr, "parse_subscript_notation")
    assert not hasattr(fr, "_SUBSCRIPT_RE")
```

- [ ] **Step 2: Run, expect fail**

Run: `poetry run python -m pytest tests/unit/cobol/test_subscript_regex_retired.py -q`
Expected: FAIL — both still exist.

- [ ] **Step 3: Implement**

- In `emit_context.py` `resolve_field_ref`, delete the `else:` legacy branch and the `parse_subscript_notation` import; the method now requires structured subscripts:

```python
        if subscripts:
            if len(subscripts) > 1:
                raise NotImplementedError(
                    f"multi-dimensional subscript not supported for {name!r} "
                    f"({len(subscripts)} subscripts); see red-dragon-cqwx"
                )
            subscript = subscripts[0]
        else:
            subscript = ""
        base_name = name
        fl, region_reg = materialised.resolve(base_name, qualifiers)
```

  (`name` is now always the bare base — the bridge and CICS parser guarantee it.)
- In `emit_context.py` `has_field`, drop `parse_subscript_notation`: `return materialised.has_field(name)`.
- In `field_resolution.py`, delete `_SUBSCRIPT_RE`, `parse_subscript_notation`, and the now-unused `import re`.
- In `cobol_frontend.py`, remove the `_parse_subscript_notation = parse_subscript_notation` alias and its import.

- [ ] **Step 4: Run, expect pass**

Run: `poetry run python -m pytest tests/unit/cobol/test_subscript_regex_retired.py -q`, then the full suite with the rebuilt JAR:
```bash
PROLEAP_BRIDGE_JAR=proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest -q
```
Expected: green (every subscripted ref now arrives structurally).

- [ ] **Step 5: Format, lint, commit**

```bash
poetry run python -m black interpreter/cobol/emit_context.py interpreter/cobol/field_resolution.py interpreter/cobol/cobol_frontend.py tests/unit/cobol/test_subscript_regex_retired.py
poetry run lint-imports
git add -A
git commit -m "refactor(cobol): retire _SUBSCRIPT_RE / parse_subscript_notation — subscripts fully structural (red-dragon-6ddr)"
```

---

### Task 7: Verification & CardDemo e2e parity

**Files:** none (verification) + optional IR-parity test `tests/unit/cobol/test_subscript_ir_parity.py`

- [ ] **Step 1: Full suite (JAR-less paths) green**

Run: `poetry run python -m pytest -q`. Expected: green (the gated bridge/e2e tests skip without env).

- [ ] **Step 2: Full suite WITH rebuilt JAR green**

```bash
cd proleap-bridge && mvn -DskipTests package -q && cd ..
PROLEAP_BRIDGE_JAR=proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest -q
```
Expected: green — proves subscripted MOVE/IF/arith/SEARCH/OCCURS lower correctly through the structured path.

- [ ] **Step 3: CardDemo CICS e2e (gated) green**

```bash
BMS_TOOLS_HOME=~/code/bms-tools CARDDEMO_HOME=/Users/asgupta/code/aws-mainframe-carddemo/app \
PROLEAP_BRIDGE_JAR=proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar \
  poetry run python -m pytest tests/integration/cics/ -q
```
Expected: green — `PROGRAM(CDEMO-MENU-OPT-PGMNAME(WS-OPTION))` now resolves via structured CICS subscripts.

- [ ] **Step 4: Lint + format clean**

`poetry run python -m black .` (no changes), `poetry run lint-imports` (0 broken).

- [ ] **Step 5: No commit needed unless an IR-parity test was added** — if added, commit it:

```bash
git add tests/unit/cobol/test_subscript_ir_parity.py
git commit -m "test(cobol): IR parity for subscripted refs through the structured path"
```

---

## Self-review checklist (run before execution)

- Spec coverage: subscripts from both feeders (Tasks 3, 5) ✓; resolver structured (Task 4) ✓; regex retired (Task 6) ✓; multi-dim loud error (Task 4/6) ✓; ref-mod/COMPUTE/multi-dim-math out of scope (untouched) ✓.
- Ordering: run **Task 4 before Task 3** (resolver kwarg must exist before strategy passes it); Task 5 (JAR) before Task 6 (delete fallback). All other tasks additive and green-preserving.
- Type consistency: `subscripts: tuple[str, ...]` everywhere (`RefModOperand`, `FieldRefNode`, `RefModNode`, `CicsOperand`); `resolve_field_ref(..., subscripts=())` keyword consistent across all call sites.
