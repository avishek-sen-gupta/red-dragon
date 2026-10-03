# Flat memory under every region

Date: 2026-10-04
Status: design, for review

## Goal

Give every byte of region storage one numeric address in a single flat address
space, with regions as segments allocated within it. This is the foundation for
a pointer model (ADDRESS OF, NULL, USAGE POINTER, SET ADDRESS OF, pointer
arithmetic), which is a separate design that follows this one.

This change adds no COBOL behaviour. Every existing suite — red-dragon's and
every forge package's — passes unchanged; the only new tests are for the flat
model itself.

## What exists

- `ALLOC_REGION` creates a zeroed `bytearray` keyed by a string handle
  `rgn_<N>` (`interpreter/handlers/regions.py`); `N` comes from the VM's shared
  symbolic counter.
- `LOAD_REGION` and `WRITE_REGION` address a byte as (handle, offset). A write
  is applied in `apply_update` (`interpreter/vm/vm.py`) as a slice assignment,
  which silently grows the `bytearray` when it runs past the end.
- `VMState.region_get(addr)` returns the live `bytearray`; callers mutate it in
  place. squall writes into it without calling `region_set`
  (`squall/binding_stores.py`).
- Harnesses create regions by name with `region_set`: cicada's
  `Address("rgn_commarea")`, jackal's `Address("rgn_parm")`.

Measured on 2026-10-04 with temporary instrumentation over every red-dragon and
forge suite: no region is ever replaced at a different size, and exactly two
writes run past a region's end — both from squall's Db2 sample programs, 2 and 4
bytes past a 258-byte region (filed as red-dragon-forge-h14).

## Design

### The address space

`VMState` owns the address space: a bump allocator and a segment table.

- **Allocation.** A new region gets the next free address as its base, and the
  allocator advances by the region's size. Segments are contiguous: no gaps and
  no alignment padding, so the byte after a segment's last byte is the first
  byte of the next segment allocated.
- **Address 0 is never allocated.** The first base is 4096, so a zero address
  (NULL, in the pointer model) and the low addresses z/OS keeps for its own
  control blocks never coincide with program storage.
- **The segment table** maps each region handle to its `Segment(base, size)`.
  An address resolves to the segment containing it and the offset within it.
- **Handles are unchanged.** Registers still hold `rgn_<N>` handles, and
  `LOAD_REGION`/`WRITE_REGION` still take (handle, offset). The handle names the
  segment; the segment table supplies its base. Nothing in the IR changes.

### Storage

Each segment's bytes are held in their own `bytearray`, placed at the segment's
base in the address space. The address space is the authority — every byte has
one address, and reads and writes are resolved by address — while storage is
kept per segment so `region_get` can keep returning the live buffer that squall
and the cicada builtins mutate in place. One shared `bytearray` cannot serve
that: Python refuses to resize a `bytearray` while any view of it is held, and
the address space grows with every allocation.

### Reads and writes past a segment's end

A write is resolved by address: `base + offset` onward. When it runs past its
segment's end it continues into the following segments, exactly as storage
would on the machine. Each write that crosses a segment boundary is logged as a
warning naming the segment, the offset and the length. Bytes beyond the highest
allocated address are dropped and logged the same way.

A read is resolved the same way: one past its segment's end returns the
following segments' bytes, and stops at the highest allocated address. Today
such a read returns only the bytes inside its region. Reads past an end were not
measured; the implementation logs them as it does writes, and the first full run
reports any.

Today a write past the end grows that one region instead. The two known cases
(red-dragon-forge-h14) will now write into the next segment; the suites decide
whether that is visible, and the log names them for the follow-up diagnosis.

### The VMState API

- `region_get(addr)` — unchanged: the segment's live `bytearray`, or `None`.
- `region_set(addr, data)` — for a new handle, allocates a segment of
  `len(data)` and copies `data` in; for an existing handle, copies `data` into
  the segment in place. A `data` whose length differs from the segment's size
  raises, since a segment cannot change size; none occurs today.
- The other region accessors (iteration and count) — unchanged in meaning.
- New: `segment_of(addr) -> Segment`, `read_at(address, length) -> bytes` and
  `write_at(address, data)`, which carry the cross-segment rule above.
  `apply_update` applies a `RegionWrite` through `write_at`, and the
  `LOAD_REGION` handler reads through `read_at`.
- `to_dict` keeps its per-region shape. `copy.deepcopy` of a `VMState` copies
  the segment table and every segment.

### Symbolic regions

An `ALLOC_REGION` with a symbolic size still yields a symbolic handle and no
segment. Nothing about symbolic execution changes.

## Testing

- New unit tests on the address space: bases are contiguous from 4096 in
  allocation order; an address resolves to its segment and offset; a write that
  crosses a segment boundary lands in the next segment and is logged; a write
  past the highest allocated address is dropped and logged; a read across a
  boundary returns both segments' bytes; `region_set` on an existing handle
  writes in place and rejects a different size; a named region created by
  `region_set` gets a segment like any other.
- Regression: red-dragon's full suite and every forge suite (`make test-all`)
  pass unchanged.

## Out of scope

- The pointer model itself: ADDRESS OF, NULL, USAGE POINTER contents,
  SET ADDRESS OF, pointer comparison and arithmetic, OMITTED detection
  (red-dragon-ooil). Its own design follows this one.
- Alignment of 01-level items, and emulated z/OS control blocks.
- Freeing segments: regions are never freed today, and that does not change.
