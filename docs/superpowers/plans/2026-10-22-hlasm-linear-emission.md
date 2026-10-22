# HLASM: linear emission (red-dragon-6uyp.62)

## Problem

`HlasmEmitter.emit_inst` rebinds a tuple per instruction, and `locate_from` rebuilds it
per statement: O(n²) in IR size. EX of an MVC lowers to about 13,300 instructions, so
16 EX sites take 158 s to compile.

## Approach

An immutable cons-list. `ChainLink[T]` (previous, item, length) on a null-object
`EmptyChain[T]`. Emitting rebinds the tail to a new link: O(1), no copy, no list
mutation, so no lint exclusion. `instructions()` flattens once, O(n).

Rejected: per-statement chunks concatenated once. A single EX statement emits
13,300 instructions, so a tuple grown inside the chunk is still quadratic.

`locate_from(start, location)` records a `LocatedSpan(start, end, location)` on a second
chain. `instructions()` applies the spans in call order, a later span winning, which
matches the old rewrite. The frontend reads the start from `emitted_count()` instead
of `len(instructions())`. Lowerings do not change.

## Tests

`tests/unit/hlasm/test_hlasm_emitter.py`:

- extending a chain shares the chain it extends (each link's `previous` is the prior
  chain object), lengths count up, flatten keeps order;
- the emitter returns instructions in order, located by the latest span.

## Then

Time 1, 4, 8, 16 EX sites before and after. Profile the 16-site compile through
`compile_hlasm`; file a bead for linker or codec waste.

## Commits

1. This plan.
2. The chain, the emitter and frontend change, the test, `hlasm.md`.
