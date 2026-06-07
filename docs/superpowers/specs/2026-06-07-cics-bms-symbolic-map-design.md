# CICS — BMS Symbolic Map Modeling — Design Spec

**Date:** 2026-06-07
**Beads story:** `red-dragon-pz9g.10` (P2)
**Depends on:** F (`pz9g.7`) — needs field-ref wiring for FROM/INTO regions
**Fitness function:** SEND/RECEIVE MAP exchange data via the symbolic-map subfield names a
program actually references (e.g. an output subfield with the `O` suffix, an input subfield
with the `I` suffix).

---

## Problem

The BMS loader built in E (`pz9g.5`) models a map as flat `{field_name: (offset, length)}`.
Real BMS symbolic maps are richer: each map field generates a **group of COBOL subfields**
distinguished by name suffix:

| Suffix | Meaning |
|---|---|
| `L` | input length (halfword) |
| `F` / `A` | flag / attribute byte |
| `I` | input data (what the program reads after RECEIVE) |
| `O` | output data (what the program writes before SEND) |

A program does `MOVE WS-NAME TO ACCTNAMO` (output) and reads `ACCTNAMI` (input) — it never
references the bare field name. The flat model has no concept of these subfields, so even
after F wires the FROM/INTO region, the names will not line up with what the program touches.

---

## Design

### Enriched map model

Extend the BMS field model so each map field carries its symbolic subfield layout:

```
BmsField:
    name: str            # base BMS field name
    offset: int          # within the physical map buffer
    length: int
    # symbolic subfields (offsets within the symbolic-map COBOL group):
    input_name: str      # ...I
    output_name: str     # ...O
    length_name: str     # ...L
    attr_name: str       # ...A / ...F
```

The symbolic-map COBOL group is itself a normal data structure in the program's
WORKING-STORAGE (generated from the map definition and `COPY`'d in). So the offsets the
runtime needs are already in `MaterialisedSectionedLayout` under the suffixed names — the BMS
model only needs to know **which suffixed names belong to which map field**, then resolve
each against the layout (F's mechanism).

### SEND MAP

For each field, resolve `<field>O` against the layout, `LoadRegion` its bytes, and place them
in the outbound screen dict keyed by the BMS field name. (Attribute/length subfields optional
for a headless runtime.)

### RECEIVE MAP

For each field present in the inbound event, resolve `<field>I` against the layout and
`WriteRegion` the event's value into it. Also set `<field>L` to the input length where the
program inspects it.

### Map model source

Two options for producing the enriched model:

- **(a) In-house enrichment (recommended first).** Derive the suffixed-subfield names by
  convention from the base field name and look them up in the layout. Requires no external
  tooling and works because the symbolic copybook is already parsed by ProLeap.
- **(b) External map-generation tool as a submodule.** Heavier; only needed if convention-based
  naming proves insufficient for some map. Decide after (a).

---

## Components

| File | Change |
|---|---|
| `interpreter/cics/bms/loader.py` | Enrich `BmsField`/`BmsMap` with symbolic subfield names; derive by suffix convention. |
| `interpreter/cics/builtins/screen.py` | SEND reads `...O` subfields; RECEIVE writes `...I` (+ `...L`) subfields. |
| `interpreter/cics/strategy.py` | SEND/RECEIVE lowering resolves the per-field subfields against the layout (via F). |

---

## Testing (TDD)

**Unit:**
- Loader derives `ACCTNAMI`/`ACCTNAMO`/`ACCTNAML` for a field `ACCTNAM`.
- SEND MAP reads from `...O` offsets; RECEIVE MAP writes to `...I` offsets — asserted against
  a representative symbolic-map layout fixture.

**Integration:**
- A program that `MOVE`s into output subfields, `SEND MAP`s, then on the next turn `RECEIVE
  MAP`s and reads input subfields — assert the screen dict carries the output values and the
  program sees the scripted input values.

---

## Risks / open questions

- **Suffix convention variance.** Map generators differ in suffix letters and truncation rules
  for long names. Verify the convention against a representative map before committing to
  pure derivation; fall back to (b) only if needed.
- **Attribute/length subfields** are largely irrelevant to a headless runtime but a program
  may inspect `...L` (input length) to detect empty fields — populate it on RECEIVE.
