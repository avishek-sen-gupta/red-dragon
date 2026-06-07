# CICS Sub-project F — EXEC CICS Field-Ref Wiring + Copy-Back — Design Spec

**Date:** 2026-06-07
**Beads story:** `red-dragon-pz9g.7` (P1)
**Depends on:** A (`pz9g.3`), B (`pz9g.1`), C (`pz9g.2`) — all complete
**Blocks:** `pz9g.8` (HANDLE/EIBAID), `pz9g.9` (bootstrap/e2e), `pz9g.10` (symbolic maps)
**Fitness function:** EXEC CICS verbs move real application data between COBOL memory and the CICS runtime — not placeholders.

---

## Problem

Sub-projects A–E lower every field-named EXEC CICS option to a `Const` placeholder
(`Const(b"")` for regions, literal strings for names). No option data-name is resolved
to its field; no output is written back. The consequence: the CICS layer routes control
flow (RETURN/XCTL/dispatch) but **cannot move any application data**.

Concretely, with the current lowering:

- `RETURN TRANSID(x) COMMAREA(WS-AREA)` lowers the COMMAREA arg as `Const(b"")` →
  state never carries between pseudo-conversational turns.
- `READ ... INTO(rec) RIDFLD(key)` → record bytes and key are never moved.
- `SEND MAP FROM(area)` / `RECEIVE MAP INTO(area)` → screen never reflects program data,
  program never sees user input.
- `ASSIGN APPLID(WS-APPLID)` → target field unwritten (builtin is a literal no-op).
- `FORMATTIME YYYYMMDD(d) TIME(t)` → output fields unwritten.
- `RESP(rc)` and `EIBRESP` → never updated after a call, so
  `IF EIBRESP = DFHRESP(NORMAL)` reads a stale `0`.

This contradicts the epic's own architecture, which prescribes name-based field
resolution against `MaterialisedSectionedLayout` with outputs flowing back via the
existing CALL USING copy-back.

## Root cause, precisely

In `CicsLoweringStrategy.lower()` (`interpreter/cics/strategy.py`), each verb branch
emits `Const(result_reg=r, value=<placeholder>)` for options that actually name a COBOL
data item, then passes those placeholder registers to a `CallFunction`. The field's real
location (region + offset + length) is available from `materialised` but never consulted.

---

## The mechanism (settled — not new machinery)

`interpreter/cobol/lower_call.py` already implements the exact pattern, for `CALL ... USING`:

1. **Resolve** each USING data-name: `materialised.resolve(name) -> (FieldLayout, region_reg)`.
   `FieldLayout` gives `offset` and `byte_length`; `region_reg` is the WS/LS/file region
   the field lives in.
2. **Copy-in** (inputs): `LoadRegion(result_reg=tmp, region_reg, offset_reg, length)` reads
   the field's current bytes into a register.
3. **Call.**
4. **Copy-back** (outputs, BY REFERENCE): after the call,
   `WriteRegion(region_reg, offset_reg, length, value_reg=tmp)` writes updated bytes back
   into the field's region.

F applies this pattern to CICS verbs. The higher-level helper
`EmitContext.resolve_field_ref(name, materialised) -> (ResolvedFieldRef, region_reg)`
(handles subscripts) is the entry point; `ResolvedFieldRef` carries `fl` (the FieldLayout)
and `offset_reg`.

**Builtins stay value-in / value-out.** The *lowering* does the LoadRegion/WriteRegion
around the `CallFunction`; the builtin receives plain `TypedValue` args and returns plain
values. This matches the VSAM spec line ("builtins receive typed arguments, no raw memory
access") and keeps builtins pure and unit-testable. The only builtins that touch VM memory
directly remain the EIB writers (`init_eib` precedent), and even those can be reframed as
lowering-side writes where convenient.

### Direction per option

| Option role | Direction | Lowering emits |
|---|---|---|
| `FROM`, `RIDFLD`, `COMMAREA` (on RETURN/XCTL), `APPLID`-source | input | `LoadRegion` field → register, pass as arg |
| `INTO`, `ASSIGN` target, `FORMATTIME` outputs (`YYYYMMDD`/`TIME`/`DATE`), `RESP` | output | after call, `WriteRegion` returned bytes → field region |
| literals (`MAP('x')`, `LENGTH(80)`, flags) | input | `Const` (unchanged — these really are literals) |

### EIBRESP / RESP write-back

After every service verb's `CallFunction`, the builtin returns a response code (int).
Lowering writes it:
1. into the `EIBRESP` field (resolve `EIBRESP` against the layout — it's a real WS field
   from `DFHEIBLK.cpy`), and
2. into the `RESP(rc)` option's named field, if present.

Use the existing field-encode path (`emit_encode_and_write` / `WriteRegion`) so the binary
`PIC S9(8) COMP` layout is respected.

---

## Scope

**In scope** — rewire these existing verbs from placeholders to resolved field refs:

- Flow: `RETURN TRANSID ... COMMAREA(x)`, `XCTL ... COMMAREA(x)` — COMMAREA bytes copied in.
- System: `ASSIGN APPLID/SYSID(f)` (write target), `FORMATTIME` outputs (write fields),
  `INQUIRE` (write EIBRESP).
- EIBRESP write-back after every service call (and `RESP(rc)` when present).

**Touches but completes in sibling stories:**
- VSAM `READ/WRITE/REWRITE/DELETE/STARTBR/READNEXT/READPREV/ENDBR` INTO/FROM/RIDFLD —
  built in D (`pz9g.4`) using F's mechanism; F lands first so D can rely on it.
- BMS `SEND MAP FROM` / `RECEIVE MAP INTO` — F resolves the FROM/INTO region; the
  field-name ↔ symbolic-subfield mapping is `pz9g.10`.

**Out of scope:** new verbs (`pz9g.11`), HANDLE semantics (`pz9g.8`), bootstrap (`pz9g.9`).

---

## Design decisions

1. **Copy-in/copy-back lives in the lowering, not the builtins.** Rationale: reuses the
   proven `lower_call.py` path, keeps builtins pure/value-based, matches the VSAM spec.
2. **COMMAREA on RETURN TRANSID/XCTL is a single contiguous field copy.** The named
   COMMAREA data item resolves to one region slice; LoadRegion copies it into the
   `DispatchResult.commarea` arg. On the inbound side, `run_cics` already injects
   `__params_region` from `context.commarea` (C, unchanged) — so the round-trip closes.
3. **EIBRESP is written by the lowering after each call**, not held as a Python reference.
   Rationale: the EIB is a normal WS field (per spec B); writing it via WriteRegion keeps
   the "no VM special-casing" invariant and means `IF EIBRESP = DFHRESP(NORMAL)` reads
   correct bytes with zero runtime bookkeeping.
4. **`ASSIGN`/`FORMATTIME` builtins return the value(s); lowering writes them.** The
   builtins lose their no-op bodies and instead compute+return; the field write is emitted
   by the strategy. Keeps the value-in/value-out contract uniform.

---

## Components

| File | Change |
|---|---|
| `interpreter/cics/strategy.py` | Replace `Const(b"")` placeholders with `resolve_field_ref` + `LoadRegion` (inputs) and post-call `WriteRegion` (outputs). Add an EIBRESP/RESP write-back helper used by every service-verb branch. |
| `interpreter/cics/builtins/system.py` | `ASSIGN`/`FORMATTIME` return their value(s) instead of no-op; `INQUIRE` already returns a resp code (unchanged). |
| `interpreter/cics/builtins/flow.py` | `set_return_context`/`set_xctl_context` read the COMMAREA arg as bytes (already do; now they receive real bytes from LoadRegion). |
| `interpreter/cobol/emit_context.py` | Reuse `resolve_field_ref`, `emit_encode_and_write` — no change expected; verify they're importable from the strategy module without import-linter breakage (deferred import if needed). |

---

## Testing strategy (TDD)

**Unit (`tests/unit/cics/`):**
- A lowering test per option direction: assert `SEND MAP FROM(WS-X)` emits a `LoadRegion`
  against WS-X's offset (not `Const(b"")`); assert `INQUIRE`/service verbs emit a
  `WriteRegion` to `EIBRESP`'s offset after the call.
- `ASSIGN APPLID` builtin returns the configured applid; `FORMATTIME` returns formatted
  output strings.

**Integration (`tests/integration/cics/`):**
- COMMAREA round-trip: a stub/compiled program writes WS-COMMAREA, `RETURN TRANSID`, and on
  the next turn reads `DFHCOMMAREA` and sees the same bytes. This is the headline assertion —
  it proves the data path end-to-end.
- EIBRESP: after a service call configured to fail, the program's
  `IF EIBRESP = DFHRESP(NOTFND)` branch is taken.

---

## Risks / open questions

- **Does copy-back interact with `CallFunction` to a builtin the same way it does with
  `CallWithMemory`?** F sidesteps this by doing copy-in/copy-back in the lowering around a
  plain `CallFunction`, rather than relying on `CallWithMemory`'s automatic copy-back. This
  is the lower-risk path and is the recommended approach.
- **Group vs elementary COMMAREA fields:** COMMAREA is typically an `01` group; `resolve`
  returns the whole group's byte_length, which is what we want (copy the entire record).
  Verify `materialised.resolve` returns group-level byte_length for an `01` name.
