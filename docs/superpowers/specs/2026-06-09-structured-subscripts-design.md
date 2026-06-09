# Structured Subscripts End-to-End — Design

**Date:** 2026-06-09
**Status:** Approved (design); pending implementation plan
**Implements:** `red-dragon-6ddr` (P0) — partial close (subscripts only; ref-mod is the remaining slice)
**Related (out of scope, filed):** `red-dragon-ovzi` (COMPUTE arithmetic string round-trip), `red-dragon-cqwx` (multi-dimensional OCCURS offset arithmetic), `red-dragon-kieo` (DFHRESP pre-pass literal-awareness)

## Goal

Eliminate the structure → string → regex re-parse for COBOL **subscripted field references**. Today a subscripted reference (`WS-ELEM(WS-IDX)`) is parsed structurally, flattened back to a string, then re-parsed by regex during field resolution. This change carries the subscript **structurally** from both sources (the ProLeap bridge and the CICS EXEC parser) into `resolve_field_ref`, and retires the regex (`_SUBSCRIPT_RE` / `parse_subscript_notation`).

This is a **flag-day** change: the bridge, the JSON contract, and the Python consumers move together (no transient dual representation), and the shaded ProLeap JAR is rebuilt as part of the change.

## Background

A subscripted reference suffers a round-trip today:

1. **ProLeap bridge** (`proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java`): `extractCallName` takes a resolved `TableCall` (base name + a structured `List<Subscript>`) and concatenates it back to text — `baseName + "(" + subText + ")"` → `"WS-ELEM(WS-IDX)"`. It uses only `subscripts.get(0)` — **multi-dimensional refs lose every subscript after the first.**
2. **CICS EXEC parser** (`interpreter/cics/cics_parser.py`): the recursive `value`/`vnested` grammar parses a subscripted operand (e.g. `PROGRAM(CDEMO-MENU-OPT-PGMNAME(WS-OPTION))`) into structured parts, then `value()` does `"".join(p.text for p in items)` → the string `"CDEMO-MENU-OPT-PGMNAME(WS-OPTION)"`, stored as `CicsOperand.text`.
3. **Python field resolution** (`interpreter/cobol/emit_context.py` `resolve_field_ref`, ~line 205): calls `parse_subscript_notation(name)` (`interpreter/cobol/field_resolution.py`, regex `_SUBSCRIPT_RE = ^([A-Za-z][A-Za-z0-9-]*)\((.+)\)$`) to recover `(base, subscript)` — the structure both feeders already had.

So both feeders destroy structure they parsed, and the resolver re-derives it by regex. The regex handles only single-dimension forms and silently defaults to index 1 on a miss.

**What is NOT in scope (and why):**
- **Reference modification** `FOO(1:8)` — already fully structured. The bridge emits `ref_mod_start`/`ref_mod_length` as expression nodes; `interpreter/cobol/ref_mod.py` (`RefModLiteral/Reference/LengthOf/BinOp`, `ref_mod_expr_from_dict`) consumes them. `_SUBSCRIPT_RE` never sees the `:` form. Ref-mod is the *other half* of 6ddr's end state and remains a separate slice.
- **COMPUTE arithmetic** — the bridge serializes formulas as text (`"WS-A + WS-B * 2"`) re-tokenized by `_TOKEN_RE` in `cobol_expression.py`. A distinct subsystem; tracked as `red-dragon-ovzi`. `_TOKEN_RE` stays.
- **Multi-dimensional offset arithmetic** — currently silently wrong end-to-end (bridge keeps only subscript 0; resolver computes one dimension). This change makes multi-dim **representable and loud** (see below) but does not implement the arithmetic; tracked as `red-dragon-cqwx`.
- **Other frontends** — despite 6ddr's wording, `field_resolution.py` / `parse_subscript_notation` is imported only by COBOL (`emit_context.py`, `cobol_frontend.py`). This is a COBOL-bounded change.

## The structured operand contract

A reference operand in the bridge JSON gains a `subscripts` array (extending the shape `serializeMoveOperand` already emits):

```json
{ "name": "WS-ELEM", "subscripts": ["WS-IDX"], "ref_mod_start": ..., "ref_mod_length": ..., "qualifiers": [...] }
```

- `name` is the **bare base name** (no parentheses).
- `subscripts` is a list of subscript **strings**, in source order, each carrying ALL subscripts (no truncation). Each element is a subscript expression as text — `"WS-IDX"`, `"5"`, `"WS-I + 1"`, or the rare nested `"B(C)"`. Each is resolved exactly as the single subscript is resolved today. (Subscript *elements* are deliberately kept as strings, not recursively structured — the nested `A(B(C))` case is preserved as the element string `"B(C)"`; this is YAGNI per 6ddr's "structured subscript list" without over-modeling subscript interiors. `_SUBSCRIPT_RE` is still retired because the *outer* base/subscript split is now structural.)
- Absent/empty `subscripts` ⇒ a plain (non-subscripted) reference.

On the CICS side, `CicsOperand` gains a structured subscript carrier:

```python
@dataclass(frozen=True)
class CicsOperand:
    text: str                       # bare base name (no subscript parens)
    is_literal: bool
    subscripts: tuple[str, ...] = ()
```

## Components

### 1. ProLeap bridge (Java) — `StatementSerializer.java`
- Introduce a structured reference serializer (converge with `serializeMoveOperand`): emit `{name: <bare base>, subscripts: [...all...], ref_mod_*, qualifiers}`. For a `TABLE_CALL`, read the full `tableCall.getSubscripts()` list (not `get(0)`), serialize each subscript's value-statement text into the array, and set `name` to the bare base. For non-table calls, `subscripts` is absent.
- Convert the **data-operand** call sites that currently use `extractCallName` for a (potentially subscripted) reference — MOVE source/target, IF/relation `left`/`right` reference operands, ADD/SUBTRACT/MULTIPLY/DIVIDE operands & giving targets, SEARCH data refs, PERFORM VARYING data refs, INSPECT/STRING/UNSTRING reference operands, file-control operands — to the structured serializer.
- Genuinely **name-only** sites (PERFORM *paragraph* targets, section names, etc., which cannot be subscripted) keep a bare-name path.
- Rebuild the shaded JAR: `cd proleap-bridge && mvn -DskipTests package` (the gitignored `*-shaded.jar` is regenerated).

### 2. JSON contract / Python statement model — `cobol_statements.py`
- The operand objects (and the IF-condition relation operands) gain `subscripts: tuple[str, ...]` in their `from_dict`, read from the new bridge JSON shape. Operand positions that can carry a subscriptable reference are read as objects `{name, subscripts}`. Flag-day: after the JAR rebuild the bridge always emits the structured shape, so `from_dict` reads only the new form — no string-subscript back-compat path is kept.

### 3. CICS EXEC parser — `cics_parser.py`
- `value()` stops `"".join(...)`-ing a subscripted operand into one string. When the parsed parts are a base `CHARS` followed by a `vnested` group, produce `CicsOperand(text=<base>, is_literal=False, subscripts=(<inner text>,))`. A plain literal or bare name is unchanged (`subscripts=()`). Nested/multi subscripts are carried as separate elements.

### 4. CICS lowering — `strategy.py`
- `emit_operand_value` / `emit_copy_in` / `_resolve_into` / `has_field` pass `operand.subscripts` through to `resolve_field_ref` instead of relying on the joined `operand.text`.

### 5. Field resolution — `emit_context.py` + `field_resolution.py`
- `resolve_field_ref(name, materialised, qualifiers=(), subscripts=())` takes structured subscripts. It no longer calls `parse_subscript_notation`; `name` is already the bare base.
- For zero subscripts: the existing non-subscripted path.
- For exactly one subscript: the existing single-dimension offset arithmetic (`(idx-1) * stride`), with the subscript value resolved as today (integer literal, or a field decoded — the rare nested `B(C)` element resolves through the same path).
- For **two or more subscripts**: raise `NotImplementedError` (loud) with the field name and the subscript count — replacing today's silent `get(0)` truncation. Tracked for real arithmetic by `red-dragon-cqwx`.
- **Delete** `parse_subscript_notation` and `_SUBSCRIPT_RE` from `field_resolution.py` (and the alias in `cobol_frontend.py`). `has_field` takes a bare name.

## Multi-dimensional handling

Today: silently wrong (subscript 0 only, no error). After: all subscripts are carried in the JSON; the resolver raises `NotImplementedError` on ≥2 rather than computing a wrong single-dimension offset. This is a strict improvement (silent bug → loud failure) and unblocks `red-dragon-cqwx` to implement the arithmetic structurally later. No CardDemo / current test path uses 2-D tables, so no green test regresses.

## Error handling

- ≥2 subscripts → `NotImplementedError` (loud, names the field + count). No silent default.
- A single subscript that is a field name not found in the layout → keep the current behaviour (default to index 1 with a warning) — unchanged, not part of this change.
- A malformed bridge payload (operand missing `name`) → the existing `from_dict` defaults apply.

## Testing

The **full existing COBOL suite is the primary regression oracle** — every test exercising a subscripted reference (MOVE, IF, arithmetic, SEARCH, OCCURS layout, PERFORM VARYING, the CardDemo CICS e2e flows with `PGMNAME(WS-OPTION)`) must stay green, proving the IR is unchanged for the single-dimension case. New tests:

- **Bridge (Java/JSON):** a subscripted ref serializes to `{name: bare, subscripts: [...]}`; a 2-D ref `TBL(I, J)` carries **both** subscripts (asserting the `get(0)` truncation is gone); a non-subscripted ref has no `subscripts`.
- **CICS parser:** `parse_exec_cics_text` on an operand `PROGRAM(PGM(WS-OPTION))` yields a `CicsOperand` with bare `text` and structured `subscripts`; a literal `MAP('X')` stays `is_literal` with empty subscripts.
- **Resolution:** `resolve_field_ref` with structured subscripts produces the same offset IR as the old string path (parity); ≥2 subscripts raises `NotImplementedError`.
- **Regex retirement:** `parse_subscript_notation` / `_SUBSCRIPT_RE` no longer exist (import removed); a grep guard or an explicit "module no longer defines it" assertion.
- **IR parity:** a subscripted MOVE compiles to byte-identical IR before/after (the load-bearing proof that semantics didn't shift).

## Constraints

- No edits to `interpreter/vm/**`, `ir.py`, `run.py`, `executor.py`, `cfg.py`. Resolution lives in the COBOL frontend; the bridge is Java.
- Flag-day: the Java serializer change, the JAR rebuild, and the Python consumer changes land together so the suite is green (no permanent back-compat shim for the string-subscript form).
- Scope is COBOL (+ its CICS EXEC operands) only; other frontends are untouched (they don't use this resolver).
- `@covers(...)` on every new test; `black` + `lint-imports` + full suite green before each commit.

## Out of scope (tracked elsewhere)

- Reference-modification structuring (the remaining half of `red-dragon-6ddr`).
- COMPUTE arithmetic string round-trip — `red-dragon-ovzi`.
- Multi-dimensional OCCURS offset arithmetic — `red-dragon-cqwx`.
- DFHRESP pre-pass literal-awareness — `red-dragon-kieo`.
