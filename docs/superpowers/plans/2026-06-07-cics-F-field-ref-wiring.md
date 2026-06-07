# CICS Sub-project F — Field-Ref Wiring + Copy-Back — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use
> checkbox (`- [ ]`) syntax. TDD throughout: failing test first, then implementation.

**Spec:** `docs/superpowers/specs/2026-06-07-cics-F-field-ref-wiring-design.md`
**Beads:** `red-dragon-pz9g.7` (P1)
**Goal:** EXEC CICS verbs move real data — COMMAREA carries between turns, EIBRESP/RESP reflect
outcomes, ASSIGN/FORMATTIME write their target fields — by resolving option data-names against the
layout and copying via `LoadRegion`/`WriteRegion` (the `lower_call.py` pattern), with builtins
staying value-in/value-out.

**Decisions locked:** EIBRESP written lowering-side (not a held Python reference). SEND/RECEIVE
MAP and VSAM INTO/FROM are out of scope here (they consume F's helper in pz9g.10 / D).

**Key APIs (verified):**
- `ctx.has_field(name, materialised) -> bool`
- `ctx.resolve_field_ref(name, materialised) -> (ResolvedFieldRef, region_reg)` where
  `ResolvedFieldRef` has `.fl` (FieldLayout: `.offset`, `.byte_length`) and `.offset_reg`.
- `LoadRegion(result_reg, region_reg, offset_reg, length)` — read field bytes into a register.
- `ctx.emit_encode_and_write(region_reg, fl, value_str_reg, offset_reg)` — encode a string and
  write into a field slot (handles binary `COMP` layouts).
- `ctx.const_to_reg(v)`, `ctx.fresh_reg()`, `ctx.emit_to_string(reg)`.
- `stmt.options: dict[str, str | None]` — option arg text; a data-name if `has_field`, else literal.

All these live on `ctx` / `materialised` already passed to `CicsLoweringStrategy.lower()`. Add
`LoadRegion` to the existing `from interpreter.instructions import ...` line in `strategy.py`
(import is already permitted by the linter).

---

## Task F0: Reusable copy-in / copy-back helpers

**Files:** Modify `interpreter/cics/strategy.py`; Test `tests/unit/cics/test_field_ref_wiring.py`

Add two module-level helpers (or private methods) so F1–F3, D, and pz9g.10 all share them.

- [ ] **Step 1: Failing test** — drive each helper with a fake/real `ctx` and assert the emitted
  instructions.

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_copy_in_emits_loadregion_for_field():
    # ctx records emitted instructions; materialised has field WS-CA at offset 10 len 8.
    reg = emit_copy_in(ctx, "WS-CA", materialised)   # returns a Register or None
    assert any(isinstance(i, LoadRegion) for i in ctx.emitted)
    assert reg is not None

@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_copy_in_returns_none_for_literal():
    assert emit_copy_in(ctx, "'CC01'", materialised) is None  # not a field
```

- [ ] **Step 2:** confirm fail.
- [ ] **Step 3:** implement in `strategy.py`:

```python
def emit_copy_in(ctx, name, materialised):
    """If `name` is a data item, LoadRegion its bytes into a fresh reg and return it.
    Returns None when `name` is a literal (caller falls back to Const)."""
    if name is None or not ctx.has_field(name, materialised):
        return None
    ref, region_reg = ctx.resolve_field_ref(name, materialised)
    out = ctx.fresh_reg()
    ctx.emit_inst(
        LoadRegion(
            result_reg=out,
            region_reg=region_reg,
            offset_reg=ref.offset_reg,
            length=ref.fl.byte_length,
        )
    )
    return out

def emit_copy_back_str(ctx, name, value_str_reg, materialised):
    """Encode a string-valued result into the named field, if it is a data item."""
    if name is None or not ctx.has_field(name, materialised):
        return
    ref, region_reg = ctx.resolve_field_ref(name, materialised)
    ctx.emit_encode_and_write(region_reg, ref.fl, value_str_reg, ref.offset_reg)
```

- [ ] **Step 4:** tests pass.
- [ ] **Step 5:** format + commit (`feat(cics): copy-in/copy-back field-ref helpers (pz9g.7)`).

---

## Task F1: COMMAREA data movement on RETURN TRANSID / XCTL

**Files:** Modify `interpreter/cics/strategy.py`; Test `tests/integration/cics/test_commarea_roundtrip.py`

Today the COMMAREA arg lowers to `Const(b"")`. Replace with `emit_copy_in` of the COMMAREA
data-name; fall back to `Const(b"")` only when absent or literal.

- [ ] **Step 1: Failing integration test** (JAR-gated, pattern from `test_parse_strategy.py`):
  compile a program that `MOVE`s a value into a WS COMMAREA field and does
  `EXEC CICS RETURN TRANSID('CC01') COMMAREA(WS-CA) END-EXEC`; run via `run_cics`; assert the
  resulting `DispatchResult.commarea` equals the bytes the program wrote (not empty).

- [ ] **Step 2:** confirm fail (commarea is empty today).
- [ ] **Step 3:** in the `RETURN`/`XCTL` branches of `lower()`, replace the COMMAREA
  `Const(b"")` with:

```python
r_ca = emit_copy_in(ctx, opts.get("COMMAREA"), materialised)
if r_ca is None:
    r_ca = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=r_ca, value=b""))
```

  Verify the flow builtins (`__cics_set_return_context` / `__cics_set_xctl_context`) accept the
  loaded value: they do `bytes(args[1].value)`; `LoadRegion` yields a bytes-like register value, so
  this works — if the VM yields a `bytearray`/`list`, adjust the builtin to `bytes(...)` it.

- [ ] **Step 4:** test passes — COMMAREA round-trips.
- [ ] **Step 5:** format + full suite + commit
  (`feat(cics): COMMAREA carries real bytes on RETURN/XCTL (pz9g.7)`).

---

## Task F2: EIBRESP + RESP(rc) write-back after service verbs

**Files:** Modify `interpreter/cics/strategy.py`; Test `tests/unit/cics/test_field_ref_wiring.py` + integration

Each service verb's builtin returns a response code (e.g. `INQUIRE` returns 0 or 27). After the
`CallFunction`, write that code into `EIBRESP` and into the `RESP(rc)` field if present.

- [ ] **Step 1: Failing test** — lowering a service verb with `RESP(WS-RC)` emits a write to both
  `EIBRESP` and `WS-RC` after the call (assert a `WriteRegion`/encode targets each offset). Plus an
  integration test: a program does `INQUIRE PROGRAM(missing) RESP(WS-RC)` then
  `IF WS-RC = DFHRESP(PGMIDERR)` — the true branch is taken.

- [ ] **Step 2:** confirm fail.
- [ ] **Step 3:** add a helper used by every `_SYS_VERBS` branch after its `CallFunction`:

```python
def emit_resp_writeback(ctx, r_resp_result, opts, materialised):
    # r_resp_result holds the builtin's returned resp code (int).
    str_reg = ctx.emit_to_string(r_resp_result)
    emit_copy_back_str(ctx, "EIBRESP", str_reg, materialised)        # always
    emit_copy_back_str(ctx, opts.get("RESP"), str_reg, materialised) # if RESP(name) present
```

  Call it after the service-verb `CallFunction` (use the call's `result_reg` as
  `r_resp_result`). Builtins that have no meaningful resp can return 0 (NORMAL) — make `ASKTIME`
  etc. return 0 instead of `None` where they currently return `None`, OR guard the writeback to
  only verbs that produce a resp. Keep it explicit; do not write EIBRESP for verbs that do not set
  it.

- [ ] **Step 4:** tests pass.
- [ ] **Step 5:** format + full suite + commit
  (`feat(cics): EIBRESP/RESP write-back after CICS service calls (pz9g.7)`).

---

## Task F3: ASSIGN and FORMATTIME write their target fields

**Files:** Modify `interpreter/cics/strategy.py`, `interpreter/cics/builtins/system.py`;
Test `tests/unit/cics/test_field_ref_wiring.py` + integration

`ASSIGN APPLID(f)` / `SYSID(f)` and `FORMATTIME YYYYMMDD(f)` / `TIME(f)` / `DATE(f)` must write
their result into field `f`. Builtins currently no-op (ASSIGN) or return a value that goes nowhere
(FORMATTIME).

- [ ] **Step 1: Failing test** — integration: `ASSIGN APPLID(WS-APPLID)` leaves the configured
  applid in `WS-APPLID`; `FORMATTIME ABSTIME(WS-T) YYYYMMDD(WS-D)` leaves an 8-digit date in
  `WS-D`.

- [ ] **Step 2:** confirm fail.
- [ ] **Step 3:**
  - Make `make_assign_builtin` return the applid/sysid string (per the requested sub-option);
    `make_formattime_builtin` already returns `YYYYMMDD`. Since a single builtin call returns one
    value, lower each output sub-option to its own `CallFunction` + `emit_copy_back_str` to the
    named field (pass the sub-option name as an arg so the builtin knows which value to return), or
    return a small structured value the lowering unpacks. Choose the simpler: **one builtin call
    per output sub-option**, builtin curried/told which sub-option, lowering copies its return into
    the field via `emit_copy_back_str`.
  - For `ASSIGN`, the data-name is the sub-option arg (`APPLID(WS-APPLID)` → write to `WS-APPLID`).

- [ ] **Step 4:** tests pass.
- [ ] **Step 5:** format + full suite + commit
  (`feat(cics): ASSIGN/FORMATTIME write target fields (pz9g.7)`).

---

## Done when

- COMMAREA round-trips across a RETURN TRANSID turn (headline integration assertion).
- `IF EIBRESP = DFHRESP(...)` / `IF WS-RC = DFHRESP(...)` branches correctly after a call.
- ASSIGN/FORMATTIME populate their fields.
- `emit_copy_in` / `emit_copy_back_str` are reusable by D and pz9g.10.
- Full suite green; black clean. Close `pz9g.7`.

## Notes
- Pyright `interpreter.cics.*` import errors are known false positives — proceed.
- Every test carries `@covers(NotLanguageFeature.INFRASTRUCTURE)`.
- JAR-gated integration tests skip without the ProLeap bridge — acceptable, matches existing CICS
  integration tests; do not let a skip read as coverage.
