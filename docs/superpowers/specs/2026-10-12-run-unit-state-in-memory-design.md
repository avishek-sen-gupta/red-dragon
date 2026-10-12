# Run-unit state in program memory

Date: 2026-10-12
Status: design, for review

## Goal

Remove the COBOL-only fields from the core VM's state. The run unit's RETURN-CODE and
the FUNCTION RANDOM sequence move into a byte region that COBOL start-up code
allocates, so the VM holds no COBOL state and learns no new concept.

This is the first step of decoupling red-dragon's core from COBOL. The ruling (user,
2026-10-12): red-dragon may know COBOL only in the COBOL lowering layer and the hooks
it takes. The other steps — intrinsic handlers reached only by indirection, the
`Language.COBOL` branches in `run.py` and `project/`, moving the file drivers to the
forge, the CALL protocol in the VM (red-dragon-qhun), and the value types — are separate
designs.

## What exists

`VMState` (`interpreter/vm/vm_types.py`) carries three fields for COBOL:

| Field | Written by | Read by |
|---|---|---|
| `cobol_run_unit_return_code: int \| None` | builtin `__cobol_publish_return_code`, emitted at every program exit and before every `STOP RUN` (`lower_program_exit.py`, `lower_arithmetic.py`) | `return_code_readback.read_return_code`, which the forge uses for a step's return code |
| `cobol_random: Any` (a `random.Random`) | builtin `__random` | the same builtin |
| `cobol_random_seed: int \| None` | builtin `__random` | the same builtin |

Builtins receive the whole mutable `VMState` and assign to these fields. Each new
COBOL feature with lasting state has so far meant a new field on the core VM.

`read_return_code` falls back to scanning the heap for a program's special-registers
region when nothing was published.

`compile_cobol` (`interpreter/project/cobol_compile.py`) builds one module per program.
With one module it skips the linker. With several, it makes the main program depend on
every other module and calls `link_modules`. The linker concatenates each module's
top-level code in dependency order, entry last, so all of it runs once before any
procedure code.

## Source

| Key | Document |
|---|---|
| LR | [Enterprise COBOL for z/OS 6.5 Language Reference, SC27-8713-04](https://www.ibm.com/docs/en/SS6SG3_6.5/pdf/lrmvs.pdf), ch. 83 "RANDOM", p. 637 |

## Design

### R1. A synthetic start-up module allocates the run-unit region

The COBOL compile path adds one generated module, the **run-unit start-up module**, to
every COBOL link. Its top-level code is:

```
CONST         %size, 6
ALLOC_REGION  %rgn, %size
STORE_VAR     __cobol_run_unit, %rgn
```

The region is zero-filled. Its layout:

| Offset | Length | Field | Encoding |
|---|---|---|---|
| 0 | 2 | run unit's RETURN-CODE | big-endian two's complement, as the per-program `S9(4) COMP` register |
| 2 | 4 | RANDOM generator state | big-endian unsigned binary |

The layout is a COBOL-layer constant beside `SPECIAL_REGISTERS_LAYOUT`.
`__cobol_run_unit` is a naming convention between COBOL lowering, the start-up module
and the read-back. The VM never names it.

The compile path records the start-up module as a dependency of the main program. The
existing ordering then places its top-level code first, and the existing reachability
filter keeps it in the link. The linker is not changed.

Every COBOL compile now has at least two modules, so the single-module branch of
`compile_cobol`, which skips the linker, is removed.

### R2. Publishing RETURN-CODE is a region write

At every program exit and before every `STOP RUN`, lowering emits:

```
LOAD_VAR      %rgn, __cobol_run_unit
WRITE_REGION  %rgn, 0, 2, %rc_bytes
```

`%rc_bytes` is the 2-byte RETURN-CODE value that lowering already loads for the
return. Last writer wins, which is the program that ended the run unit (red-dragon-cvwu
is unchanged). The builtin `__cobol_publish_return_code` and `BuiltinName.PUBLISH_RETURN_CODE`
are deleted.

### R3. RANDOM follows IBM, with its state in the region

LR p. 637:
- "If the first reference to this function in the run unit does not specify
  argument-1, the seed value used will be zero."
- "If a subsequent reference specifies argument-1, a new sequence of pseudorandom
  numbers is started."
- "For a given seed value, the sequence of pseudorandom numbers is always the same."
- The returned value lies strictly between zero and one.
- argument-1 "must be zero or a positive integer", and only 0 to 2,147,483,645 yield a
  distinct sequence.

IBM does not publish its generator, so red-dragon's numbers will not match z/OS's. This
design chooses the Lehmer "minimal standard" generator: modulus M = 2^31 − 1, multiplier
16807. It has exactly 2^31 − 2 states, which matches the 2,147,483,646 distinct seeds that
IBM allows, and its whole state fits in 4 bytes.

- State 0 means "no sequence started". The region starts zero-filled, so a first
  reference without an argument starts from seed 0, as LR requires.
- Seed s starts the sequence at state s + 1. A seed above 2,147,483,645 is reduced
  modulo 2,147,483,646, which repeats an earlier sequence ("not distinct").
- Each reference advances the state, state ← state × 16807 mod M, and returns
  state / M, which lies strictly between 0 and 1.

Lowering of `FUNCTION RANDOM [(seed)]`:

```
LOAD_VAR      %rgn, __cobol_run_unit
LOAD_REGION   %st, %rgn, 2, 4
CALL_FUNCTION %next, __random_next_state(%st [, %seed])
WRITE_REGION  %rgn, 2, 4, %next
CALL_FUNCTION %val, __random_value(%next)
```

`__random_next_state` and `__random_value` are pure builtins. They read no VM state and
write none. `__random` and its dependence on Python's `random` module are deleted.

A symbolic state or seed gives a symbolic result and leaves the region unwritten, as
today's symbolic arguments do.

A negative argument breaks LR's "must be" rule. This design treats it as seed 0 and
logs a warning. That is red-dragon's own choice, since IBM does not say what happens.

The old seed rules are deleted: seed 0 reseeding from system entropy, and a negative
seed restarting from the last positive seed (red-dragon-clpn's accepted deviation).
Runs become reproducible.

### R4. The host reads RETURN-CODE from the region

`read_return_code(vm)` reads `__cobol_run_unit` from the finished VM's outermost frame
and decodes offset 0, length 2. The heap-scan fallback is deleted. A run in which no
program ended reads 0, the zero-filled initial value, which is also RETURN-CODE's
initial value. A `VMState` assembled by hand for a test has to allocate the region the
way the start-up module does.

The signature stays the same, so the forge's caller (jackal's step return code) does not
change.

### R5. The VM loses its COBOL fields

`cobol_run_unit_return_code`, `cobol_random` and `cobol_random_seed` are deleted from
`VMState`. Nothing replaces them.

## What this does not change

- The per-program special-registers region and RETURN-CODE's propagation from callee
  to caller through the return value (red-dragon-ltq6).
- The linker, the VM's instruction set and its handlers.
- `io_provider` on `VMState`, which belongs to the intrinsic-handler design.

## Testing

- **Unit:**
  - the start-up module's IR;
  - `__random_next_state` and `__random_value`, covering: state 0 with no argument
    starting from seed 0; a seed restarting the sequence; the same seed giving the same
    sequence; a seed above the range reduced; a negative seed warning and treated as 0;
    values strictly between 0 and 1;
  - `read_return_code` on a hand-built VM with the region.
- **Integration:**
  - RETURN-CODE from GOBACK, from STOP RUN in a subprogram, and from a CALL chain
    (`tests/integration/test_cobol_return_code.py`, unchanged assertions);
  - RANDOM sequences across a CALL: a seed set in one program continues in another,
    since the sequence belongs to the run unit;
  - two runs giving the same numbers.
- **Removal is checked:** the three fields no longer exist on `VMState`, and no
  builtin takes the VM to mutate COBOL state.
- **Forge:** jackal's suite passes unchanged after the submodule bump.
