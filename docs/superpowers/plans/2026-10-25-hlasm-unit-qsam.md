# HLASM unit .14: DCB, DCBD, OPEN, CLOSE, GET, PUT, DD definitions

Bead red-dragon-6uyp.14. Design: `docs/superpowers/specs/2026-10-24-hlasm-system-services-design.md`,
decision 5. Rulings R68 (locate GET, DCBD in scope; DD definitions are run inputs) and R78
(HLASM run inputs live in `interpreter.hlasm_run_inputs`).

## IBM facts checked

DFSMS Macro Instructions for Data Sets, "Data control block — BPAM, BSAM, QSAM" and its
QSAM interface table; DFSMS Using Data Sets, "EODAD end-of-data-set exit routine".
Re-checked in this unit: DSORG, DDNAM, MACR (before OPEN) and OFLGS (OPEN-complete X'10')
against IBM's DCB field table (DFSMS Using Data Sets, "DCB fields common to all uses").
The MACR bit values are not on that page; they agree with z390's DCBD equates.

| Offset | Field | Width | Notes |
|---|---|---|---|
| 26 | DCBDSORG | 2 | X'40' in the first byte is PS |
| 32 | DCBEODAD | 4 | flag byte, then the 24-bit EODA; the DCB macro's default is 1; we take 0 or 1 as no routine |
| 36 | DCBRECFM | 1 | F X'80', V X'40', B X'10' |
| 37 | DCBEXLST | 3 | not used |
| 40 | DCBDDNAM | 8 | EBCDIC, blank padded |
| 48 | DCBOFLGS | 1 | DCBOFOPN X'10' once OPEN succeeded |
| 50 | DCBMACRF | 2 | byte 1 GET X'40', move X'10', locate X'08'; byte 2 the same for PUT: GM X'5000', GL X'4800', PM X'0050', PL X'0048' |
| 56 | DCBSYNAD | 4 | flag byte, then the 24-bit SYNA |
| 62 | DCBBLKSI | 2 | |
| 82 | DCBLRECL | 2 | for V it counts the 4-byte RDW |

- OPEN and CLOSE take a list of fullwords: an option byte, then the DCB's 24-bit address;
  X'80' in the option byte ends the list. OPEN's mode is the option byte's low four bits:
  INPUT 0, OUTPUT 15, EXTEND 14 (UPDAT 4 and the BSAM modes are not lowered). MODE=31
  lists are not supported.
- OPEN sets R15 to 0 when every DCB opened, 8 when one did not; a failed DCB keeps
  DCBOFOPN off.
- GET: R1 = DCB, R0 = area in move mode; locate mode returns the record's address in R1.
  PUT: R1 = DCB, R0 = area. GET and PUT branch and link through R14.
- At end of data control goes to EODAD with R2-R13 as before the GET and R14 the address
  after it; R0, R1 and R15 are not defined. Without EODAD the task abends 337.
- RECFM V records start with the RDW: the length with the RDW, then two zero bytes.

## Macros (hlasm-bridge/maclib, our own text)

| Macro | Expansion |
|---|---|
| `DCB DSORG=PS,MACRF=,RECFM=,LRECL=,BLKSIZE=,DDNAME=,EODAD=,SYNAD=` | 96 bytes at the offsets above; MACRF any of GM, GL, PM, PL; RECFM F, FB, V, VB; a self-defining EODAD or SYNAD at or above 2^24 is MNOTE 8 |
| `DCBD` | DSECT IHADCB with the names above, DCBOFOPN, DCBRECF, DCBRECV, DCBRECBR, DCBDSGPS |
| `OPEN (dcb,(opt),...)` | `CNOP 0,4`, `BRAS 1` over the list (`AL1(opt),AL3(dcb)`), `SVC 19` |
| `CLOSE (dcb,,...)` | the same list with option 0, `SVC 20` |
| `GET dcb[,area]`, `PUT dcb[,area]` | R1 = DCB, R0 = area, `LARL 14` to the address after the SVC; `SVC 200` / `SVC 201` |

## Run input and the declaration builtin

`interpreter/hlasm_run_inputs`: `DdDefinition(path, recfm, lrecl, blksize)` per DDNAME and
`dd_builtins(dds)`: `__hlasm_dd(name)` answers `[supplied, recfm, lrecl, blksize]`.
`run_input_builtins(clock, parm, dds)`; run() supplies none. The paths go to the file
provider as path overrides, one per DDNAME (`RunInputs.path_overrides`).

`declare_file_builtins()` (same package) gives `__hlasm_declare_file(ddname, variable,
record_length)`: it builds the provider's sequential `FileFrame` from run-time values and
hands it to the provider's declaration. It imports `interpreter.cobol.file_frame`, so
run() cannot compose it (cobol-isolation); callers compose it, as with the FP builtins.

## Lowering (interpreter/hlasm/data_set_services.py)

- SVC 19: for each list entry: DDNAME from the DCB, cut at the first blank; unsupplied
  → failed. Each zero RECFM, LRECL, BLKSIZE takes the DD's and is written back. Mode
  from the option's low four bits (0, 15, 14; any other → failed).
  `__hlasm_declare_file(ddname, variable, record length)` (V: LRECL less the RDW), then
  `__cobol_open_file`; not OK → failed. Opened: DCBOFOPN on; MACRF GL or PL obtains an
  LRECL buffer through .12's allocation, kept by DCB address with a pending-PUT flag.
  R15 = 0, or 8 if any entry failed.
- SVC 20: each open DCB: a pending locate PUT is written, `__cobol_close_file`,
  DCBOFOPN off. R15 = 0.
- SVC 200: `__cobol_read_record`; end of data → EODAD (R14 already set) or S337.
  The record (V: RDW + data) is copied byte by byte to R0's area, or to the buffer whose
  address goes to R1.
- SVC 201: F: LRECL bytes from the area; V: the RDW's length less 4 bytes after it;
  `__cobol_write_record`. PL: the buffer's pending record is written, then R1 = the
  buffer; CLOSE writes the last one.
- GET or PUT on a DCB that is not open abends S0C1: IBM's GET/PUT branches through the
  DCB's routine address, which an unopened DCB does not hold, and our unowned branches
  abend S0C1.
- Driver outcomes are compared by their `AccessCondition` positions (OK 0, END_OF_FILE 2),
  named in `hlasm_constants`, since interpreter.hlasm cannot import interpreter.cobol.

## Tests

- Unit: `__hlasm_dd` supplied and unsupplied; OPEN and GET IR shape (provider calls, no SYMBOLIC).
- Integration `tests/integration/hlasm/test_data_set_services.py`: DCB image; DCBD names;
  bad DCB operands; copy F input to output (move); locate GET; RECFM V; EODAD; S337;
  unsupplied DD; DCB fields from the DD.
- z390: copy F, RECFM V, EODAD; DDNAMEs through environment variables. z390's DCB has its
  own layout, so the DCB image and DCBD tests stay VM-only.

## Commits

1. DCB, DCBD, DD run input (with this plan).
2. OPEN, CLOSE, GET, PUT lowering, `__hlasm_declare_file`; docs; bead note; issues.jsonl.
