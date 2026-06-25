# Alternate-Key Read in the Shared Access-Method Engine — Design

**Status:** Designed (2026-06-26). Brainstormed. Awaiting user review. Tracks red-dragon
epic `red-dragon-0wzv`. Prerequisite for the cicada VsamEngine integration (parked).

**Repo:** red-dragon (engine-side only).

## What this builds (plain terms)
The engine gains the ability to **read a flat dataset by a key it isn't physically sorted
by** — via linear scan. Read-only. This is the minimal capability behind cicada's
"alternate index" datasets (e.g. CXACAIX: a 50-byte xref read by an ACCT-ID at offset 25,
in a file sorted by its primary key at offset 0). Nothing else: no browse, no writes, no
real mainframe AIX (index cluster / BLDINDEX / PATH).

## Driver (why now)
The file-resident `IndexedDriver` finds records by **binary search**, which requires the
backing file **sorted by the key at `key_offset`** — fine for a primary key, wrong for a
secondary key the file isn't sorted by. Discovered while planning the cicada VsamEngine
integration: CXACAIX is read by an alternate key in 5 durable CardDemo CICS flows
(signon, bill pay, account update, add transaction, account view), and cicada's in-memory
engine serves it by **linear scan** today. The file-resident engine can't, so this is a
prerequisite for migrating cicada off its in-memory store.

## Scope
**In scope (minimal — exactly what's exercised):**
- A read-only `read_key(key)` that finds a record by a key at `key_offset` via **linear scan**
  over the flat fixed-length file (no sort-by-that-key assumption).
- Exposed as a focused new driver implementing the existing `FileOrganizationDriver` Protocol,
  selected via a dedicated factory entry.

**Out of scope (deferred):**
- Browse by the alternate key (`STARTBR`/`READNEXT`/`READPREV` in alt-key order) — unused.
- Writes/maintenance on an alternate-key dataset (`write`/`rewrite`/`delete`) — unused.
- Real mainframe AIX: an alternate-index cluster over a base cluster, BLDINDEX, PATH access,
  base-write upgrade. CardDemo flattens the xref to a standalone dataset, so none of this
  machinery is exercised. (The IDCAMS `DEFINE AIX`/`BLDINDEX`/`PATH` batch side is a separate
  concern — `jackal-1o2.22`.)
- Deciding *which* datasets are alternate-key: that is the **consumer's** knowledge (cicada's
  FCT), wired up in the resumed cicada integration — the engine stays language-agnostic.

## Component
**`AlternateKeyDriver`** in `interpreter/cobol/file_drivers.py`, implementing
`FileOrganizationDriver` (so consumers treat every dataset through one Protocol):
- `open(path, mode, record_length, key_offset, key_length) -> None` — open the flat
  fixed-length file read-only (`rb`); store `record_length`, `key_offset`, `key_length`.
- `read_key(key: bytes) -> AccessResult` — **linear scan**: read each `record_length`-byte
  record in physical order; return `AccessResult(OK, data=record)` for the first record whose
  `record[key_offset : key_offset + key_length] == key`; return `AccessResult(NOT_FOUND)` when
  no record matches. (`NOT_FOUND` is the "no such key" condition; `END_OF_FILE` is for
  sequential exhaustion, which a point lookup is not.)
- `close() -> None` — close the file handle.
- `read_seq`, `start`, `write`, `rewrite`, `delete` — **fail loud**: raise (e.g.
  `NotImplementedError("alternate-key datasets are read-only point lookups")`). A silent no-op
  or a fabricated status would hide a real capability gap; raising surfaces it.

**Factory:** `open_alternate_key_driver(path, mode, record_length, key_offset, key_length) ->
FileOrganizationDriver` — returns an opened `AlternateKeyDriver`. **Not** a new
`FileOrganization` enum value: that enum is COBOL's `ORGANIZATION` (`SEQUENTIAL`/`INDEXED`/
`RELATIVE`); "alternate key" is not a COBOL organization, so adding it there would conflate
language semantics with an engine access mode.

**`IndexedDriver` is untouched** — no risk to the primary-key binary-search path.

## Data flow
```
consumer (later: cicada FCT marks a dataset alternate-key)
   → open_alternate_key_driver(path, INPUT, reclen, key_offset, key_length)
   → AlternateKeyDriver.read_key(acct_id)
   → linear scan: first record with record[koff:koff+klen] == acct_id
   → AccessResult(OK, data) | AccessResult(NOT_FOUND)
```

## Error handling
- Unsupported ops **raise** (fail loud), never return a fabricated condition.
- `read_key` on an empty file or a miss → `NOT_FOUND` (a real outcome, not an error).
- No `None` defaults; no defensive guards; no regex; FP core / imperative shell.
- The neutral `AccessResult` vocabulary is unchanged (reuses `OK`/`NOT_FOUND`).

## Testing (TDD)
- **`read_key` finds an out-of-sort-order key:** seed a flat file sorted by an offset-0
  primary key; `open_alternate_key_driver(..., key_offset=25, key_length=11)`; assert
  `read_key(<an ACCT-ID at offset 25 of some record>)` returns `OK` + that exact record —
  the whole point is the match is found despite the file not being sorted by offset-25.
- **Miss → `NOT_FOUND`:** `read_key(<absent key>)` → `AccessResult(NOT_FOUND)`.
- **Multiple records:** a key matching the 3rd of several records is found (linear scan
  traverses past non-matching records).
- **Unsupported ops raise:** `read_seq`/`start`/`write`/`rewrite`/`delete` each raise.
- **`open_alternate_key_driver` returns an opened driver** of the right type.
- **Full red-dragon suite green** — purely additive; the primary-key path is untouched.
- End-to-end proof is deferred to the resumed cicada integration (CXACAIX flows through it).

## Constraints
- Additive and behavior-preserving for existing code; full red-dragon suite is the gate.
- Engine stays language-agnostic (knows "records + a key at an offset", never "AIX"/"FCT").
- FP / frozen where applicable; no `None` defaults; no defensive guards (fail loud); no regex.

## Risks
- **Linear scan is O(n).** Acceptable: alternate-key datasets here are small xrefs, and the
  mission is faithful *results*, not index performance. If a future consumer needs alt-key
  access over a large dataset, revisit (a real alternate-index structure) then — YAGNI now.
- **Fat-interface smell** (a Protocol driver supporting one method). Accepted for uniform
  consumption; the raises make the unsupported surface explicit rather than silently wrong.

## Bookkeeping
- Epic `red-dragon-0wzv`. Unblocks the cicada VsamEngine merge follow-on under
  `red-dragon-mc6u` (parked spec: cicada `docs/superpowers/specs/2026-06-26-vsam-engine-
  integration-design.md`). On completion, resume that integration — its plan scopes which
  cicada datasets use `open_alternate_key_driver`.
