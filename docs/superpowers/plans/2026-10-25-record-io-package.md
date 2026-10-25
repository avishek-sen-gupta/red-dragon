# Record I/O out of interpreter.cobol

Bead red-dragon-0iua. The file provider, its drivers and their data are record I/O that COBOL
and HLASM share. They move to a sibling package `interpreter.record_io`, held by a contract that
it imports neither `interpreter.cobol` nor `interpreter.hlasm`. Composing the mixed COBOL+HLASM
run-time stack is red-dragon-6lic, in red-dragon-forge, and is not done here.

## Survey

| Module | Goes to | COBOL rule held | `interpreter.cobol` imports |
|---|---|---|---|
| `access_result` | `record_io` | none; FILE STATUS is mapped from it by the lowering's IR | none |
| `prime_key` | `record_io` | none | none |
| `alternate_key` | `record_io` | none | `prime_key` |
| `record_shape` | `record_io` | none | `prime_key` `alternate_key` |
| `relative_slot` `flagged_slot` `described_slot` | `record_io` | none; slot layouts on disk | `relative_slot` |
| `alternate_index` | `record_io` | none | `alternate_key` |
| `file_drivers` | `record_io` | none; the sequential and relative and indexed drivers | `access_result` `alternate_index` `alternate_key` `flagged_slot` `prime_key` `record_shape` `relative_slot` |
| `variable_sequential_driver` | `record_io` | none; RDW records | `access_result` `file_drivers` `prime_key` |
| `alternate_index_driver` | `record_io` | none | `access_result` `alternate_key` `file_drivers` `prime_key` `record_shape` |
| `file_frame` | `record_io` | none; the declaration's record | `alternate_key` `data_literals` `prime_key` `record_shape` |
| `data_literals` | `interpreter.data_literals` beside `data_value`; it is not record I/O and the COBOL lowering uses it too | none | none |
| `run_inputs` | `record_io` | none; it carries SELECT entries and SYSIN records and UPSI switches as data | none |
| `io_provider` | split (below) | ACCEPT and the implementor switches and KEY OF REFERENCE | `access_result` |
| `real_file_provider` | split (below) | SYSIN for ACCEPT and UPSI switch state and KEY OF REFERENCE | all of the above |

`io_provider` splits: `RecordIOProvider`, `IOResult` and `NoIOProvider` go to
`record_io/io_provider.py`; `CobolIOProvider`, `NullIOProvider` and `StubIOProvider` stay.
`real_file_provider` splits: `RealFileProvider` (path resolution, frames, drivers, record
operations) goes to `record_io`; `RealFileIOProvider` stays and adds the COBOL operations.

What stays COBOL: FILE STATUS mapping, OPTIONAL files, record-length and key-sequence checks
are already IR in the lowering (`file_verb_ir`, `file_logic_status`), so no module above holds
them. The provider's COBOL operations (ACCEPT FROM a device, implementor switch status and SET,
KEY OF REFERENCE) stay on `CobolIOProvider` in `interpreter.cobol`.

The record-operation dispatch names stay `__cobol_*`: HLASM's IR already calls them, and
renaming the primitives is a separate change.

`record_io` imports `cobol_asg.file_enums`, `cobol_asg.cobol_statements` and
`cobol_asg.switch_status` (organisation, open mode, SELECT entries, switch status). `cobol_asg`
is a leaf every package may import, and HLASM already does.

## RECFM

`data_set_services` already reads its variable-format bits from `RecordFormat.V`; the other
constant, `FORMAT_BITS`, is the DCB mask, not a second encoding. Nothing left to share.

## Commits

1. Pure move. `git mv` the whole modules above (not `io_provider`, `real_file_provider`, which
   are split in 2, so their COBOL halves do not move out and back). Every import site rewritten,
   found with ast-grep, then a text grep for the old dotted paths. The `record-io-is-neutral`
   contract, this plan, the ADR and the module maps.
2. Split the interface. `RecordIOProvider` holds declare, open, close, read, write, rewrite,
   start, delete and the result accessors; `CobolIOProvider(RecordIOProvider)` adds the COBOL
   operations. `RealFileProvider` in `record_io`; `RealFileIOProvider(CobolIOProvider,
   RealFileProvider)` in COBOL. Null, Stub and RealFile serve COBOL unchanged.
3. Collect. `run.py` types `io_provider` as `RecordIOProvider`, defaulting to `NO_IO_PROVIDER`,
   which dispatches nothing, so a run without a provider behaves as one given `None` did.
   `data_set_services` compares `AccessCondition` positions directly; `PROVIDER_OK`,
   `PROVIDER_END_OF_FILE` and the mirror test go. The HLASM test helper uses `RealFileProvider`.
   `run()`'s docstring and `hlasm.md` say which parts exist and that forge composes them.

`VMState.io_provider` and `VMConfig.io_provider` stay untyped: `record_io` imports
`interpreter.vm.vm` for `UNCOMPUTABLE`, and `vm.vm` imports `vm_types`, so typing the VM's field
would be an import cycle.
