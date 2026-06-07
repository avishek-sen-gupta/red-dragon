# CICS — HANDLE CONDITION/AID Semantics + EIBAID Write-Back — Design Spec

**Date:** 2026-06-07
**Beads story:** `red-dragon-pz9g.8` (P1)
**Depends on:** F (`pz9g.7`) — needs the EIB write path
**Fitness function:** PF-key navigation and conditional handlers work — a program that
branches on `EIBAID = DFHPF3` or registers `HANDLE AID PF3(label)` behaves correctly.

---

## Problem

Two distinct gaps, both currently papered over by aliasing `HANDLE CONDITION`,
`HANDLE AID`, and `HANDLE ABEND` to a single no-op builtin (`__cics_handle_abend`):

1. **EIBAID is never written into the EIB between turns.** `init_eib` writes the *initial*
   EIBAID from `CicsContext.eibaid`, but when an input event arrives (RECEIVE MAP, or the
   next pseudo-conversational turn), the terminal's attention key is dropped. Programs that
   do `IF EIBAID = DFHPF3` see a stale value.
2. **HANDLE CONDITION/AID have no real semantics.** They should register a handler label
   and cause a branch to it when the condition (e.g. NOTFND) or AID (e.g. PF3) fires after
   a subsequent command. Today they do nothing, so the registered label is never reached.

CardDemo menu navigation and program exit depend on both.

---

## Design

### EIBAID write-back

When an input event carries an attention id (`InputEvent.eibaid` in the dispatcher, or the
value returned by `RECEIVE MAP`), write it into the `EIBAID` field of the EIB region before
control returns to the program — the same single-byte write `init_eib` already performs.
Because F establishes the EIB write path, this is a small, localized addition:

- **Dispatcher path:** when a `RETURN TRANSID` turn resumes on the next `InputEvent`,
  the new `CicsContext.eibaid` is set from the event (already wired in C). `init_eib` on
  the resumed program writes it. **Verify** this already holds after F; if so, this half is
  a test-only confirmation.
- **RECEIVE MAP path:** within a single execution, `RECEIVE MAP` consumes an input event
  whose `eibaid` differs from program entry. The receive-map builtin (or its lowering) must
  update `EIBAID` in the EIB region at that point. This is the genuinely new write.

### HANDLE semantics

Follow the epic's prescribed approach:

> `HANDLE CONDITION/AID/ABEND -> CALL __cics_handle(...) + injected BRANCH_IF after
> subsequent commands; prefer normalizing to RESP-check form where CardDemo allows.`

Two-tier strategy:

1. **RESP-check normalization (preferred where applicable).** For `HANDLE CONDITION`, the
   modern idiom is `RESP(rc)` + an explicit `IF`. Where a program uses `HANDLE CONDITION`
   to guard a single following command, lower it to the equivalent post-command RESP check
   (F already writes EIBRESP). This avoids global handler state.
2. **Label registration + branch injection (fallback).** For `HANDLE AID` (PF-key dispatch,
   which has no RESP equivalent) and any `HANDLE CONDITION` that spans multiple commands:
   - `__cics_handle_*` records `{condition/aid: label}` in a per-execution handler table.
   - After each subsequent applicable command (or, for AID, after `RECEIVE MAP`), the
     translator injects a conditional branch: if the fired condition/AID has a registered
     label, branch to it.
   - `HANDLE ABEND` stays a no-op (logged) — abend already surfaces as a `DispatchResult`.

Handler state is per-execution (cleared at program entry), held in a holder injected into
the strategy, mirroring the `result_holder` pattern.

---

## Components

| File | Change |
|---|---|
| `interpreter/cics/builtins/system.py` (or new `handle.py`) | Split `__cics_handle_abend` into `__cics_handle_condition`, `__cics_handle_aid`, `__cics_handle_abend`; condition/aid record into a handler holder. |
| `interpreter/cics/strategy.py` | Stop aliasing the three HANDLE verbs; inject handler holder; emit branch-injection IR after applicable commands; EIBAID write on RECEIVE MAP. |
| `interpreter/cics/dispatcher.py` | Confirm resumed-turn EIBAID reaches `init_eib` (likely no change). |

---

## Testing (TDD)

**Unit:**
- `HANDLE AID PF3(L)` records `{PF3: L}` in the holder.
- After `RECEIVE MAP` with an event whose eibaid is PF3, the injected branch targets `L`.
- EIBAID byte in the EIB region equals the event's attention id after RECEIVE MAP.

**Integration:**
- A program with `HANDLE AID PF3(EXIT-PARA)` reaches `EXIT-PARA` when the scripted input
  event carries PF3; reaches normal flow on ENTER.
- A program with `HANDLE CONDITION NOTFND(NF)` reaches `NF` after a READ that misses.

---

## Risks / open questions

- **Branch-injection placement.** "After subsequent commands" is ambiguous in scope —
  classic CICS HANDLE persists until overridden. Start with the narrowest correct behavior
  (inject after the next applicable command; AID checked after RECEIVE/SEND), and widen only
  if a target program needs persistent handlers. Log when a handler is registered but never
  checked, so gaps are visible (no silent drop).
- **Interaction with F's RESP write-back.** RESP-normalized HANDLE CONDITION relies on F
  writing EIBRESP before the injected check. Sequencing: F lands first.
