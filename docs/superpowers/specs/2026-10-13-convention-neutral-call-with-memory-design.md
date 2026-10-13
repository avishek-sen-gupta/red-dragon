# Convention-neutral CALL_WITH_MEMORY — design

Date: 2026-10-13. Issue: red-dragon-qhun. Status: approved in brainstorm.

## The idea

COBOL's CALL protocol is a naming convention: each program registers its entry
function under a name when it loads, and a CALL looks that name up. Today the VM's
`CALL_WITH_MEMORY` handler spells out half of that convention itself. After this
change the COBOL lowering owns both halves, and the opcode means only "call the
function found at this location, giving it this memory".

## Why

Ruling (user, 2026-10-12): red-dragon may know COBOL only in the COBOL lowering
layer and the hooks it takes; the VM reaches lowering-supplied behaviour only
through indirection, never by name.

`_handle_call_with_memory` (`interpreter/handlers/calls.py`) breaks that ruling:

| What the handler does | What it is |
|---|---|
| builds `__prog_<NAME>` from a string | half of the registration convention |
| upper-cases the name, strips blanks | COBOL's program-name rules |
| reads the object field `__init_params__` | a lowering convention, by name |
| binds the arguments as `__call_arguments` | a lowering convention, by name |

The same names are typed again in the forge: cicada (`vm_init.py`,
`conversational.py`) and jackal (`cobol_step.py`, `le_abend.py`), which also
select the entry by testing labels for the prefix `func_init_params_`.

## Design

### 1. The opcode: two operands

```
%r = call_with_memory <location> <memory>
```

- `location: VarName | Register` — where the callee's entry function is found.
  A `VarName` for a literal CALL (`call_with_memory __entry_CALLEE %34`); a
  `Register` holding that variable's name as a string when the name is computed at
  run time (`call_with_memory %7 %34`).
- `memory: Register` — the argument array (per argument, a region and an offset,
  or an OMITTED marker), unchanged from today's `params_reg`.
- `result_reg` as today (the callee's RETURN-CODE).

`func_name`, `params_reg` and `target_reg` are removed. Both operands always
render, in that fixed order, like every other opcode. `reads()` returns the memory
register and, when the location is a register, that register. `map_registers`
already rewrites a field whose value is a `Register`, so the union field needs no
special case; the legacy operand converter (`_call_with_memory` in
`instructions.py`) builds the new shape.

### 2. The handler: neutral steps only

1. Resolve the location to a variable name: the `VarName` itself, or the string
   value of the register.
2. Find that variable in the call stack; its value is a function reference.
3. Bind the memory register's value to the function's first declared parameter
   (`registry.func_params`), push a frame returning to the next instruction with
   `result_reg`, and jump to the function.

Unresolved behaviour is unchanged in kind: a literal location falls back to the
configured call resolver (a symbolic result, so analysis continues); a register
location raises `UnresolvedProgramError` naming the variable. The handler contains
no prefix, no case rule, no field name and no variable name.

### 3. The COBOL lowering owns the convention

A new module `interpreter/cobol/program_object.py` defines the convention once:

- `entry_var(program_id) -> VarName` — `__entry_<PROGRAM-ID>`, upper case.
- `program_var(program_id) -> VarName` — `__prog_<PROGRAM-ID>`, the program
  object (the box holding WORKING-STORAGE and RETURN-CODE regions), unchanged.
- `ARGUMENTS_PARAM` — the entry function's parameter, `__call_arguments`.
- `WORKING_STORAGE_FIELD` — the program object's `ws_handle` field.

Uses:

- **Registration (init block, `lower_program_init.py`):** after building the entry
  function reference, `store_var <entry_var(pid)> %entry`. The object's
  `__init_params__` field loses its only reader and is no longer stored.
- **Entry function:** declares its parameter with `SYMBOLIC param:__call_arguments`,
  the mechanism every frontend uses; the symbolic handler already reads an argument
  the caller bound.
- **LINKAGE binding (`lower_data_division.py`):** loads `ARGUMENTS_PARAM`, as today.
- **CALL 'literal' (`lower_call.py`):** `call_with_memory <entry_var(literal)> <memory>`.
- **CALL identifier:** after the existing field decode, the lowering emits TRIM,
  UPPER-CASE and concatenation with the `__entry_` prefix, and gives the result
  register as the location.

### 4. `LinkedProgram.entry_func_label`

`CodeLabel | None = None` becomes `CodeLabel = NO_LABEL`, the existing null object.
Readers (`run.py`, `__main__.py`, one test's `getattr`) stop testing for `None`.

### 5. Forge

- **cicada:** `make_entry_point` and `_entry_point` select `entry_func_label` only;
  the `func_init_params_` fallbacks are deleted. COMMAREA injection uses
  `ARGUMENTS_PARAM`.
- **jackal:** `cobol_step` selects `linked.entry_func_label` instead of the first
  `func_symbol_table` label without the prefix, and injects the PARM area under
  `ARGUMENTS_PARAM`. `le_abend` uses `program_var("CEE3ABD")` and
  `WORKING_STORAGE_FIELD`.

After this, no forge file spells `__call_arguments`, `__prog_`, `ws_handle` or
`func_init_params_`.

## Behaviour changes

- An unlinked literal callee's symbolic result is named from the location
  (`__entry_CALLEE`) instead of `CALLEE`.
- `UnresolvedProgramError`'s message names the variable it looked up; it still
  contains the program name.
- Leading blanks in a `CALL identifier` name: today's `str.strip()` removes all
  whitespace at both ends; COBOL TRIM removes spaces at both ends. Names come from
  fixed-length fields, so only spaces occur in practice.

Everything else — CardDemo, CICS dispatch, jackal steps, RETURN-CODE copy-up,
BY REFERENCE / BY CONTENT / OMITTED arguments — behaves as today.

## Tests

- **Neutrality (unit):** a hand-built program that registers a function under a
  name with no COBOL convention (`obj_start`), declares a parameter `args`, and is
  called with `call_with_memory obj_start %m`, binds `args` and returns. Proves the
  handler holds no convention of its own.
- **Unresolved (unit):** literal location → symbolic result; register location →
  `UnresolvedProgramError` naming the variable.
- **Lowering (unit):** IR text for `CALL 'CALLEE'` is
  `call_with_memory __entry_CALLEE %n`; for `CALL WS-NAME`, the location is the
  register produced by the trim / upper-case / prefix chain; the init block stores
  `__entry_<PID>`.
- **Existing suites** keep their assertions: `test_call_with_memory.py`,
  `test_handle_call_with_memory_singleton.py`, `test_lower_call_with_memory.py`,
  `test_cobol_call_by_data_name.py` (its `"DSNTIAC" in message` holds),
  `test_cobol_return_code.py`, `test_cobol_programs.py`. Tests that construct
  `CallWithMemory` directly change its constructor arguments, and tests that
  hand-build a program object register its entry under `entry_var` instead of
  the `__init_params__` field; their assertions stay.
- **Forge:** `make test-all`, and a c3270 CardDemo recording checked frame by frame.

## Docs

ADR-182 in `docs/architectural-design-decisions.md`; `docs/ir-reference.md`
CALL_WITH_MEMORY section; `docs/notes-on-vm-design.md` and
`docs/frontend-design/cobol.md` where they describe the dispatch.

## Out of scope

- Typed function-reference CONSTs and the frontend side tables (red-dragon-ajps).
- Label kinds read from label text (red-dragon-lpye).
- Link-time resolution of literal CALLs to labels (red-dragon-ajps).
- A program registry separate from variables: registrations stay ordinary
  variables, relying on the `__` prefix not to collide.
- ENTRY alternate entry points (lowered to a bare label today; not callable).
