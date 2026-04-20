# SLICE/SPLICE Opcode Removal — Replace with String Builtins

## Goal

Remove the `SLICE` and `SPLICE` opcodes from the IR and replace them with two
COBOL string builtins (`__string_slice`, `__string_splice`) in `byte_builtins.py`.
This brings substring read/write operations in line with the existing string
primitive family (`__string_concat`, `__string_find`, `__string_replace`, etc.)
rather than treating them as first-class IR instructions.

## Motivation

`SLICE` and `SPLICE` were added as dedicated opcodes during the COBOL reference
modification implementation. On review, they are string library operations — not
fundamental control-flow or data-flow primitives — and belong in the builtin
table alongside the other COBOL string operators. New opcodes add surface area to
the IR, opcode metadata, the MCP server, and VM dispatch; builtins add only an
entry to `BYTE_BUILTINS`.

## Architecture

### New builtins

Both live in `interpreter/cobol/byte_builtins.py` and are registered in
`BYTE_BUILTINS`. Their names are added to `BuiltinName` in
`interpreter/cobol/cobol_constants.py`.

**`__string_slice(value, start_0indexed, length) → str`**
Returns the substring `value[start : start + length]`.

- `value`: string
- `start_0indexed`: 0-based integer offset (COBOL 1-indexed positions are
  converted to 0-indexed by the lowering before this call)
- `length`: integer number of characters to extract; clamped to
  `len(value) - start` if it exceeds the remaining string

**`__string_splice(value, start_0indexed, length, replacement) → str`**
Returns `value[:start] + replacement + value[start + length:]`.

- `value`: the current string content of the target field
- `start_0indexed`, `length`: same semantics as `__string_slice`
- `replacement`: the source string to insert

Both builtins return `_UNCOMPUTABLE` when any argument is symbolic.

### Lowering changes

`interpreter/cobol/lower_arithmetic.py` replaces every `ctx.emit_inst(Slice(...))`
with `ctx.emit_inst(CallFunction(result_reg=..., func_name=FuncName(BuiltinName.STRING_SLICE), args=(...)))` and every `ctx.emit_inst(Splice(...))` with the
equivalent `CallFunction` for `STRING_SPLICE`. The `Slice` and `Splice` imports
are removed.

### Deletions

| File | What is removed |
|---|---|
| `interpreter/ir.py` | `SLICE` and `SPLICE` members of `Opcode` enum |
| `interpreter/instructions.py` | `Slice` and `Splice` dataclasses; opcode converter entries |
| `interpreter/handlers/regions.py` | `_handle_slice`, `_handle_splice` handlers; dispatch entries |
| MCP server opcode metadata | `SLICE` and `SPLICE` entries |
| Unit tests for `Slice`/`Splice` | Any test that directly constructs `Slice`/`Splice` instructions |

## Testing

The existing `TestReferenceModification` integration tests (10 tests) are the
correctness gate — they exercise the full pipeline end-to-end and do not
reference `Slice`/`Splice` by name. No new integration tests are needed.

Unit tests for the two new builtins go in `tests/unit/cobol/test_byte_builtins.py`
(alongside existing byte builtin tests):
- `test_string_slice_basic` — `"ABCDE"`, start=1, length=3 → `"BCD"`
- `test_string_slice_clamps_to_end` — length exceeds remaining chars
- `test_string_splice_basic` — replace middle section
- `test_string_splice_replacement_shorter` — replacement shorter than length
- `test_string_splice_replacement_longer` — replacement longer than length

## Out of scope

- Changing how the lowering computes `start_0indexed` (1→0 conversion stays in
  `lower_arithmetic.py` before the call)
- Any changes to the `slice` builtin in `builtins.py` (generic collection slice,
  unrelated)
- Any frontend other than COBOL
