# The COBOL pointer model

Date: 2026-10-04
Status: design, for review

## Goal

Give COBOL programs real pointers: `ADDRESS OF`, `NULL`, `USAGE POINTER`
fields, `SET ADDRESS OF`, pointer arithmetic and comparison — so a program can
take an item's address, store it, hand it to a CALL, move along it and rebind LINKAGE to
it, and a callee can tell an OMITTED argument by `ADDRESS OF ... = NULL`
(red-dragon-ooil).

It builds on the flat address space (ADR-151,
`2026-10-04-flat-memory-design.md`): every region byte already has an address.

## What exists

- Regions are segments of one flat address space from 4096, but a region
  register still holds a string handle (`rgn_<N>`), and `LOAD_REGION` /
  `WRITE_REGION` address a byte as (handle, offset).
- Each LINKAGE 01 is bound in plain IR to a region register and a shift
  (`bind_linkage`); an OMITTED or unsupplied argument binds zero-filled storage
  of the parameter's own.
- `call_arguments(vm, regions)` builds a harness frame's argument array; each
  element's `region` field is the region's handle string.
- `USAGE POINTER` parses, but has no category of its own: it falls back to zoned
  decimal with no digits, so a POINTER field occupies 0 bytes.
- The bridge serialises SET's operands as flattened text: `SET P TO ADDRESS OF
  X` arrives with the value `"ADDRESSOFX"`, `SET ADDRESS OF LK TO P` with the
  target `"ADDRESS"`. A condition `ADDRESS OF X = NULL` arrives as a reference
  named `ADDRESS` compared with the literal `NULL`. `LENGTH OF` is already
  recognised as a special register and serialised as a structured operand.
- There are no COBOL compile options: behaviour such as ARITH(COMPAT) is fixed.

## Design

### 1. Region handles are addresses

`ALLOC_REGION` returns its segment's base address, an integer, in place of the
`rgn_<N>` string. `LOAD_REGION` and `WRITE_REGION` take that integer as their
region operand and read or write at `handle + offset` through the address space
(`VMState.read_at` / `write_at`), keeping the fast path for an access inside one
segment and the rule that one past a segment's end carries on into the next.

A pointer is therefore a handle with an offset already added in, and every
pointer operation below is plain IR — integer arithmetic on region registers —
with no new opcode or builtin.

The VMState region API keeps its shape for harnesses: `region_get(addr)` and
`region_set(addr, data)` still take an `Address`, and a region a harness creates
by name (`Address("rgn_commarea")`, `Address("rgn_parm")`) gets a segment as
before. A harness that reads a handle out of a register or a heap field (cicada's
and squall's WORKING-STORAGE lookups, the test helpers' `ws_handle`) holds an
integer now; `region_get(Address(str(base)))` resolves a base address's decimal
text to its segment, so those lookups keep working. `call_arguments` puts
each region's base address in the element's `region` field.

An `ALLOC_REGION` with a symbolic size still yields a symbolic handle.

### 2. The NULL page and the null-access strategy

Addresses below 4096 are never allocated; address 0 is NULL. Any read or write
that touches an address below 4096 goes to an injected `NullAccess` strategy
instead of the address space:

- `WarnAndIgnore` (the default): a read returns zeroes, a write is dropped, and
  each access is logged as a warning naming the address and length.
- `Halt`: the access raises, ending the run — the S0C4 a real system gives.

The strategy is injected into the run as `io_provider` is, and stored on the
`VMState`. A read or write past the last allocated byte keeps the rule ADR-151
set (zeroes / dropped, logged); the strategy governs the NULL page only.

### 3. The addressing mode

Pointer width follows IBM's `LP` compile option. Callers name it with an enum,
`LP.LP32` (the default, 4-byte pointers) or `LP.LP64` (8-byte), given to
`compile_cobol`; it applies to every program compiled in that call. It is
resolved there, once, into an `AddressingMode`: a protocol with an
implementation per width, supplying

- the pointer field's type — `S9(9) COMP-5` under LP32, `S9(18) COMP-5` under
  LP64 — which gives a POINTER field its size in the layout and its encoding in
  the lowering;
- the largest address that type can hold.

The `AddressingMode` is injected into the layout builder and into
`EmitContext`; nothing downstream tests which width it holds. Storing an
address above the largest the mode can hold raises. The flat address space
itself stays unaware of pointer width.

### 4. The bridge

`ADDRESS OF identifier` (with its qualifiers and subscripts) is serialised as a
structured operand, `{"kind": "address_of", "name": ..., "qualifiers": [...]}`,
wherever it occurs: SET targets and values, relation conditions, and CALL USING
arguments. `NULL` and `NULLS` are serialised as a figurative constant. SET's
targets and values become structured operands — references, `address_of`,
figuratives and literals — in place of flattened text; the typed ASG's
`SetStatement` parses them. The change goes in red-dragon's `proleap-bridge`.

### 5. COBOL behaviour

- **`USAGE POINTER` fields** take the addressing mode's size and encoding.
- **`ADDRESS OF x`** is `x`'s region register plus `x`'s offset (for a LINKAGE
  item, its binding's shift is already in that offset).
- **`SET p TO ADDRESS OF x | NULL | q`** stores the address in `p`.
- **`SET ADDRESS OF lk TO p | ADDRESS OF y | NULL`**, for a LINKAGE 01 or 77
  item only (IBM allows nothing else): rebinds the item's region register to the
  address and its shift so the item's static start lands on it. Every later
  access to `lk` and its subordinates follows.
- **`SET p UP BY n` / `DOWN BY n`** adds or subtracts `n` bytes.
- **Relations** `=` and `NOT =` compare addresses, between any two of a
  POINTER field, `ADDRESS OF`, and `NULL`.
- **OMITTED and unsupplied parameters** bind NULL — region register 0 — in
  place of zero-filled storage of their own. `ADDRESS OF lk = NULL` is then
  true, and an access to `lk` goes to the null-access strategy.

### 6. What changes for existing programs

A program that reads an OMITTED or unsupplied parameter without testing it
still reads zeroes under the default strategy, as today. One that writes to such
a parameter used to write into private storage it could read back; the write is
now dropped with a warning. The suites decide whether anything depends on that.

## Testing

- Unit tests: handles are base addresses and a load or write at handle + offset
  reaches the right bytes; each null-access strategy on a read and a write below
  4096; each addressing mode's pointer type, size and limit, and the raise above
  the limit; the bridge's serialisation of `ADDRESS OF` and `NULL` in SET,
  conditions and CALL USING.
- COBOL source-level integration tests, one per behaviour: a POINTER field's
  size and contents under LP32 and LP64; `SET p TO ADDRESS OF x` then `SET
  ADDRESS OF lk TO p` reading and writing `x` through `lk`; `SET p UP BY n`
  walking a table; pointer relations including `NULL`; `ADDRESS OF lk = NULL`
  for an OMITTED argument and `NOT = NULL` for a supplied one; the `Halt`
  strategy stopping a run that touches an OMITTED parameter.
- Regression: red-dragon's full suite and every forge suite (`make test-all`).
  cobble reads the bridge's JSON, so the plan checks what structured SET
  operands do to cobble's own SET handling.

## Out of scope

- PROCEDURE-POINTER and FUNCTION-POINTER.
- CICS `GETMAIN` and `ADDRESS` in cicada: a forge follow-up built on this model.
- Emulated z/OS control blocks (PSA, TCB, TIOT).
- Alignment of 01-level items, and freeing segments.
