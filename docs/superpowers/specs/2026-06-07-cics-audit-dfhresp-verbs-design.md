# CICS — DFHRESP Table + Verb Coverage Audit — Design Spec

**Date:** 2026-06-07
**Beads story:** `red-dragon-pz9g.11` (P2)
**Depends on:** nothing (can run anytime) — outputs feed F/D/E and may spawn follow-ups
**Fitness function:** every `DFHRESP(name)` the target programs use substitutes correctly,
and every EXEC CICS verb they use is either covered or has a filed follow-up.

This is an **audit task**, not a feature. It produces two documented lists and any follow-up
stories they reveal. No application behavior changes directly.

---

## Part 1 — DFHRESP table completeness

### Problem

The pre-pass substitutes only three DFHRESP codes: `NORMAL=0`, `NOTFND=13`, `ENDFILE=20`.
The design spec says "the full ~120-entry table is bundled." Any other `DFHRESP(name)` a
program references (candidates: `DUPREC`, `DUPKEY`, `NOTOPEN`, `LENGERR`, `INVREQ`, `MAPFAIL`,
`QIDERR`, `ITEMERR`, `PGMIDERR`, `DISABLED`, `NOSPACE`) currently substitutes wrong or not at
all → a parse error or a silently wrong literal.

### Approach

1. Scan the target programs for every `DFHRESP(<name>)` reference; produce the used-set.
2. Compare against the bundled table (currently 3 entries).
3. Bundle the full canonical DFHRESP code table (the standard CICS RESP value set) in the
   pre-pass, so substitution is complete regardless of which codes appear.
4. Add a guard: if the pre-pass encounters a `DFHRESP(name)` not in the table, **fail loudly**
   (or log a clear warning) rather than leave it unsubstituted — no silent pass-through.

### Test

- Pre-pass substitutes each code in the used-set to its correct numeric literal.
- Unknown `DFHRESP(BOGUS)` triggers the guard (raises/logs), not a silent miss.

---

## Part 2 — Verb coverage

### Currently covered (A–E + planned D)

`RETURN`, `RETURN TRANSID`, `XCTL`, `ABEND`, `ASSIGN`, `ASKTIME`, `FORMATTIME`, `INQUIRE`,
`WRITEQ TD`, `HANDLE ABEND/CONDITION/AID`, `READ`, `WRITE`, `REWRITE`, `DELETE`, `STARTBR`,
`READNEXT`, `READPREV`, `ENDBR`, `SEND MAP`, `RECEIVE MAP`, `SEND TEXT`.

### Likely-needed but unplanned (audit which the target programs actually use)

| Verb | Why it may be needed | Note |
|---|---|---|
| `LINK PROGRAM(p) COMMAREA(c)` | call a subprogram and **return** (distinct from XCTL, which transfers control with no return) | most likely real gap — needs a sub-call that resumes the caller |
| `READQ TS` / `WRITEQ TS` / `DELETEQ TS` | temporary storage queues (distinct from TD) | common for scratchpad state across turns |
| `RECEIVE` (no MAP) | raw terminal input | maybe unused if all input is mapped |
| `SEND CONTROL` | cursor/erase control without a map | maybe foldable into SEND MAP options |
| `SYNCPOINT` | commit boundary | likely safe as a no-op in a single-task emulation |
| `GETMAIN` / `FREEMAIN` | dynamic storage | likely unused in CardDemo |
| `START` / `RETRIEVE` | interval control / async start | likely unused in the online tier |

### Approach

1. Scan the target programs for every `EXEC CICS <verb>`; produce the used-verb-set.
2. Diff against the covered set above.
3. For each genuine gap, file a follow-up story under the epic with the verb's semantics.
   `LINK` and `TS` queues are the most probable; size them explicitly.

### Output

A short coverage table (used vs covered) committed alongside this spec's resolution, plus
filed follow-up stories. No silent omission — an unused-but-uncovered verb is fine; a
**used**-but-uncovered verb must become a story.

---

## Risks / open questions

- **`LINK` semantics** are non-trivial: unlike XCTL it must push a frame and resume the caller
  with the COMMAREA copied back (F's copy-back applies). If used, it deserves its own story,
  not a footnote.
- The audit reads program source to enumerate usage; keep the resulting lists in tracked docs
  free of external paths/package names per project data-handling rules — record verb/code
  names and counts only.
