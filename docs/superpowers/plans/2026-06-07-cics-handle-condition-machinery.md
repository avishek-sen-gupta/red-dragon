# CICS HANDLE CONDITION/AID Runtime-Dispatch Machinery — Follow-up Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or
> superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Status:** DEFERRED follow-up. Not needed for CardDemo today — the audit found `HANDLE AID`
used 0×, `HANDLE CONDITION` used 1× (NOP'd, see below). Build this only when a target program
relies on condition/AID handlers that affect the happy path.

**Goal:** Emulate CICS `HANDLE CONDITION` / `HANDLE AID` exactly, the way production CICS does
it — a runtime handler table plus a computed branch after each command — rather than any static
analysis of which handler is "active."

**Why exact, not approximate:** IBM's CICS translator turns `HANDLE CONDITION` into a
`GO TO … DEPENDING ON …` (a computed goto) whose target is chosen at **runtime** from state set
by whichever `HANDLE` statements actually executed. Handler activation is a dynamic property
(order, branches, loops, overrides all matter); it cannot be determined statically. We mirror
CICS's own design and inherit its exactness.

**References:**
- Broadcom MetaCOBOL docs — `HANDLE CONDITION` → `GO TO … DEPENDING ON …`.
- IBM CICS TS docs — handler effective "from where it appears to end of program," overridable,
  not propagated to sub-programs.
- KICKS (open-source CICS) — preprocessor translates EXEC CICS into host COBOL statements.

**Prerequisites:** F (`pz9g.7`, field-ref wiring — provides EIBRESP/RESP write so conditions can
be detected) and the EIBAID write-back from `pz9g.8` (so AID dispatch has a value to read).

---

## Mechanism

Three moving parts, all per-program-execution:

1. **Handler table (runtime state).** A small map `condition_name -> handler_label` (and a
   parallel `aid_key -> handler_label`) held in VM-accessible state for the current program. Reset
   at program entry. CICS scope rules: a later `HANDLE` for the same condition overrides; the
   table does NOT propagate into called sub-programs.

2. **`HANDLE CONDITION`/`HANDLE AID` lowering = a runtime write.** The verb lowers to a builtin
   call that writes each `condition -> label` pair into the table *when the statement executes*.
   Because it is an ordinary runtime write, branches/loops/overrides are honored automatically —
   no static reasoning. `IGNORE CONDITION` clears a slot; `PUSH/POP HANDLE` save/restore the table
   (include if a target program uses them).

3. **Computed dispatch after each fallible command.** After every EXEC CICS command that can raise
   a condition, the translator emits:
   - compute the raised condition (from the response the call returns — F writes EIBRESP),
   - look up the handler label for that condition in the table,
   - if a label is registered, branch to it; else fall through.

   The branch is the existing `BranchIf(cond_reg, branch_targets=(L1, L2, …))` instruction — the
   IR's indexed/computed branch. `cond_reg` is derived from the table lookup; `branch_targets` are
   the registered handler labels. This is the IR equivalent of `GO TO … DEPENDING ON`. AID dispatch
   is identical but emitted after `RECEIVE MAP`, keyed on EIBAID.

---

## Files

| Action | Path |
|---|---|
| Create | `interpreter/cics/builtins/handle.py` — table writers + lookup helpers |
| Modify | `interpreter/cics/strategy.py` — lower HANDLE* to table writes; emit post-command dispatch |
| Modify | `interpreter/cics/types.py` — handler-table holder type |
| Create | `tests/unit/cics/test_handle_machinery.py` |
| Create | `tests/integration/cics/test_handle_dispatch.py` |

---

## Task 1: Handler-table state + writer builtins

**Files:** `interpreter/cics/types.py`, `interpreter/cics/builtins/handle.py`, `tests/unit/cics/test_handle_machinery.py`

- [ ] **Step 1: Failing test** — a `HandlerTable` holder; `__cics_handle_condition` writes
  `{NOTFND: "NF", ERROR: "ERR"}`; a later write of `NOTFND -> "NF2"` overrides; `IGNORE` clears.

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_handle_condition_records_and_overrides():
    table = HandlerTable()
    write = make_handle_condition_builtin(table)
    write([typed("NOTFND", UNKNOWN), typed("NF", UNKNOWN)], VMState())
    assert table.condition["NOTFND"] == "NF"
    write([typed("NOTFND", UNKNOWN), typed("NF2", UNKNOWN)], VMState())
    assert table.condition["NOTFND"] == "NF2"  # override
```

- [ ] **Step 2:** confirm it fails (no module).
- [ ] **Step 3:** implement `HandlerTable` (dataclass with `condition: dict[str,str]` and
  `aid: dict[str,str]`, reset method) and the writer builtins in `handle.py`.
- [ ] **Step 4:** tests pass.
- [ ] **Step 5:** format + commit.

## Task 2: Reset table at program entry

- [ ] Failing test: table is cleared on `on_procedure_entry`.
- [ ] Wire a reset into the strategy's procedure-entry hook (next to EIB init).
- [ ] Tests pass; commit.

## Task 3: Lower HANDLE CONDITION/AID to table writes

- [ ] Failing test (lowering): `HANDLE CONDITION NOTFND(NF) ERROR(ER)` emits writes for each pair;
  the verb no longer routes to the no-op.
- [ ] In `strategy.py`, replace the no-op routing for `HANDLE CONDITION`/`HANDLE AID` with
  per-pair `CallFunction` to the writer builtins. Parse the multi-pair option form
  (`COND1(L1) COND2(L2) …`). Keep `HANDLE ABEND` as the no-op (abend already surfaces via
  `DispatchResult`).
- [ ] Tests pass; commit.

## Task 4: Post-command computed dispatch

- [ ] Failing test: after a service verb whose RESP indicates NOTFND, a `BranchIf` to the
  registered handler label is emitted/taken; with no handler registered, control falls through.
- [ ] After each fallible command's lowering, emit: read EIBRESP/RESP → map to condition name →
  look up label in table → `BranchIf(cond_reg, branch_targets=(…registered labels…))`. Define how
  `cond_reg` indexes into `branch_targets` (e.g. lookup returns an index; 0 = no-handler/fall
  through). AID dispatch emitted after `RECEIVE MAP`, keyed on EIBAID.
- [ ] Integration test: a program with `HANDLE CONDITION NOTFND(NF)` reaches `NF` after a READ
  that misses, and proceeds normally when the READ succeeds; `HANDLE AID PF3(EXIT)` reaches `EXIT`
  on PF3 and normal flow on ENTER.
- [ ] Full suite; format; commit.

## Task 5 (optional): PUSH/POP HANDLE, IGNORE CONDITION

- [ ] Only if a target program uses them: `PUSH HANDLE`/`POP HANDLE` save/restore the table;
  `IGNORE CONDITION` clears slots. Tests + commit.

---

## Risks / open questions

- **`BranchIf` index semantics.** Confirm how `cond_reg` selects among `branch_targets` (is it a
  0-based index? what is the fall-through encoding?). Settle in Task 4 before emitting dispatch.
- **"After each fallible command" placement.** Dispatch must be emitted after every command the
  handler covers — i.e. every subsequent EXEC CICS command until overridden — matching CICS's
  program-wide scope. Emit it uniformly after every CICS command once any handler is live; log if
  a handler is registered but no command ever checks it (no silent gap).
- **Sub-program boundary.** Per CICS, the table does not propagate into `XCTL`/`LINK` targets —
  reset on entry (Task 2) handles this naturally since each program runs with a fresh table.
