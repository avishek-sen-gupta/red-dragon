# HLASM unit .12: GETMAIN, FREEMAIN, STORAGE, TIME

Bead red-dragon-6uyp.12. Design: `docs/superpowers/specs/2026-10-24-hlasm-system-services-design.md`, decision 5.

## Macros (hlasm-bridge/maclib, our own text)

| Macro | Expansion |
|---|---|
| `GETMAIN R,LV=n\|(r),SP=n` | R0 = SP in bits 32-39, length in 40-63; `BAL 1,*+4` makes R1 negative; `SVC 10` |
| `FREEMAIN R,LV=,A=addr\|(r),SP=` | same R0; R1 = `L 1,addr` or `LR 1,r`; `SVC 10` |
| `GETMAIN RU\|RC`, `FREEMAIN RU\|RC` | R0 = length, R15 = SP<<8 \| flags (1 release, 2 conditional, 4 page); `SVC 120` |
| `STORAGE OBTAIN,LENGTH=,ADDR=,SP=,LOC=,COND=,BNDRY=` | as GETMAIN RU/RC, then `ST 1,addr` or `LR r,1` |
| `STORAGE RELEASE,LENGTH=,ADDR=,SP=,COND=` | as FREEMAIN RU/RC |
| `TIME [DEC\|BIN][,LINKAGE=SVC]` | `LA 0,0` (DEC) or `LA 0,1` (BIN); `SVC 11` |

LOC is accepted and ignored. BNDRY is DBLWD or PAGE (PAGE only on SVC 120 forms).
Anything else is MNOTE 8.

## Lowering (IR, interpreter/hlasm)

- `storage_services.py`: SVC 10 and SVC 120 in IR.
  - Obtain: length rounded up to 8; `ALLOC_REGION` of length + alignment - 1; the
    aligned address in R1; table[address] = entry {length, subpool}.
  - Release: the address is in the table (the core membership builtin), and length and subpool equal the
    entry's; else abend SA0A (SVC 10) / SA78 (SVC 120). The entry's length becomes -1,
    so a second release abends. Storage is not reused.
  - SVC 120 sets R15 = 0.
- Allocation table: `__hlasm_allocations`, a `NEW_OBJECT` indexed by address, created in
  `machine_allocation`. Entries are objects with fields `length` and `subpool`.
- `time_service.py`: SVC 11. Microseconds since 1900 from `__hlasm_tod_clock`; R0 = DEC
  `HHMMSSth` packed or BIN hundredths by R0 bit 63; R1 = `0CYYDDDF`; R15 = 0. Date by
  the 400/100/4/1-year cycle division, branch-free. Local time is the TOD clock (no
  zone offset, no leap seconds).
- No new builtin.

## Tests

- Unit `tests/unit/hlasm/test_time_service.py`: TOD values (1900-01-01, 1900-12-31,
  2000-02-29, 2000-12-31, 2023-10-06, 2100-03-01) give literal DEC, BIN, date words.
- Unit `tests/unit/hlasm/test_machine.py`: the allocation table starts empty.
- Integration `tests/integration/hlasm/storage_service_programs.py` + `test_storage_services.py`:
  - GETMAIN R and RU, STORAGE OBTAIN: address % 8 == 0, page case % 4096 == 0, write
    and read back through obtained storage, then release: RC 0.
  - Bad releases: unknown address, wrong length, double free, wrong subpool → SA0A / SA78.
  - GETMAIN RC and STORAGE COND=YES: R15 = 0.
  - TIME DEC and BIN with the fixed clock: exact R0, R1.
  - Bad operands: MNOTE 8.
- z390 `tests/z390/test_storage_services_differential.py`: relative facts (alignment,
  distinct areas, stored data, R15, TIME's date sign nibble and digit ranges).

## Commits

1. This plan.
2. Storage services: macros, lowering, table, tests, docs.
3. TIME: macro, lowering, tests, docs; bead note; issues.jsonl.
