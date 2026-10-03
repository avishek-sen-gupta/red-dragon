# CALL USING by Address Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CALL passes one address (region + offset) per USING argument, and each
callee LINKAGE 01 is bound to its own address, so BY REFERENCE shares the caller's
bytes, BY CONTENT/VALUE/literals pass a copy, and OMITTED keeps its slot.

**Architecture:** The caller builds an argument array in plain IR (`NewArray`,
`NewObject`, `StoreField`, `StoreIndex`) and hands it to `CallWithMemory`, whose
handler injects it as `__call_arguments`. The callee prologue binds each LINKAGE 01
in plain IR (a region register and a delta register), and every LINKAGE field access
adds its 01's delta to the field's static offset. LINKAGE keeps its static
end-to-end layout, so strides and analysis extents are unchanged.

**Tech Stack:** Python 3.13, red-dragon IR and VM, pytest, the ProLeap bridge JAR
(`PROLEAP_BRIDGE_JAR`) for integration tests.

**Spec:** `docs/superpowers/specs/2026-10-03-call-using-addresses-design.md`

## Deviations from the spec (decided with the user, 2026-10-03)

1. **Argument count.** The callee does not use `__list_len`, which measures only
   Python lists, while a `NewArray` is a heap object. The caller stores the
   argument count as a `count` field on the array, and the callee compares its
   position against `LoadField(args, "count")`. No builtin is used at all.
2. **No call-site memory effects.** The effect recorder holds one effect per
   instruction id (`CollectingRecorder` asserts it). The user deferred modelling the
   CALL's effects to red-dragon-9u0r. The CALL records only what its real copies
   touch, i.e. the BY CONTENT/VALUE temporaries, through the region funnel. It does
   not declare that the callee may write its BY REFERENCE arguments.

## Global Constraints

- No new builtin. Parameter passing is plain IR, plus the existing `CallWithMemory`
  handler.
- Recorded LINKAGE extents keep their static coordinates: each 01 at its offset in
  `laid_end_to_end(_in_using_order(asg))`.
- The fresh region for a BY CONTENT/VALUE copy or a literal gets
  `RegionId.CALL_ARGUMENT`.
- A program with no PROCEDURE DIVISION USING binds argument *i* to its *i*-th LINKAGE
  01 in declaration order.
- An absent or OMITTED argument binds to a fresh zero-filled region of the
  parameter's declared length, at offset 0.
- A LINKAGE 01 that USING does not name binds to a zero-filled placeholder.
- The user approved these behaviour changes in the spec:
  1. a parameter wider than its argument reads the caller's next bytes;
  2. a CALL with no USING binds no LINKAGE;
  3. the zerg xfail flips;
  4. the IR-shape tests are rewritten.
- Red-dragon's commit hooks run the full suite, so every commit is green. The forge
  hooks skip suites on a pure submodule bump, so forge suites are run by hand.
- No comments except one-line class/module headers. Frozen dataclasses. No `Any`.
  `Sequence`/`Mapping` for read-only parameters.

## Review Focus

1. **A LINKAGE field at a non-zero shift** (second 01, argument not at offset
   `start`) used by the statement kinds that resolve fields through different
   paths: MOVE, arithmetic, IF, a subscripted MOVE, ADD CORRESPONDING, a
   reference modification, and STRING INTO. Each must read and write the caller's bytes. A
   site that emits `Const(fl.offset)` without the delta reads the wrong bytes. Task
   2's `test_a_shifted_parameter_works_in_every_statement_kind` pins this.
2. **A subscripted LINKAGE field** (OCCURS inside the second 01). Its base offset is
   built in a different branch of `resolve_field_ref`. The same test covers it.
3. **A LINKAGE item passed on to a further CALL BY REFERENCE.** The callee's own
   argument address must be its binding region plus delta, not the static offset.
   Pinned by `test_a_parameter_passed_down_is_the_original_storage`.
4. **A REDEFINES 01 in LINKAGE.** It shares the redefined 01's binding. Pinned by
   `test_a_redefining_01_reads_through_the_same_argument`.
5. **A CALL whose callee lists more parameters than it was passed.** The extra ones
   read zeros and do not raise. Pinned by
   `test_a_parameter_the_caller_did_not_pass_reads_zeros`.

---

### Task 1: Additive pieces — `RegionId.CALL_ARGUMENT` and the `call_arguments` helper

**Files:**
- Modify: `cobol_memory/region_id.py`
- Create: `interpreter/cobol/call_arguments.py`
- Test: `tests/unit/cobol/test_call_arguments.py`

**Interfaces:**
- Produces: `RegionId.CALL_ARGUMENT = "call_argument"`.
- Produces: `call_arguments(vm: VMState, regions: Sequence[Address]) -> TypedValue`.
  It builds the argument array the callee reads. Every region is passed BY
  REFERENCE at offset 0, and the result is a `TypedValue` holding a `Pointer` to the
  array.
- Produces: the argument array's shape, which Task 2's IR must match exactly.
  - Array fields: `FieldName("count")` = int; `FieldName(str(i), FieldKind.INDEX)` =
    the element pointer.
  - Element fields: `FieldName("region")` = the region address string;
    `FieldName("offset")` = int; `FieldName("omitted")` = bool.

- [ ] **Step 1: Write the failing test**

```python
"""call_arguments builds the argument array a callee's LINKAGE binds to."""

from interpreter.address import Address
from interpreter.cobol.call_arguments import call_arguments
from interpreter.field_name import FieldKind, FieldName
from interpreter.vm.vm_types import Pointer, VMState


def test_each_region_is_an_element_at_offset_zero_and_the_count_is_stored() -> None:
    vm = VMState()
    vm.region_set(Address("rgn_commarea"), bytearray(b"\x00" * 4))

    args = call_arguments(vm, [Address("rgn_commarea")])

    assert isinstance(args.value, Pointer)
    array = vm.heap_get(args.value.base)
    element = array.fields[FieldName("0", FieldKind.INDEX)].value
    assert isinstance(element, Pointer)
    fields = vm.heap_get(element.base).fields
    assert (
        array.fields[FieldName("count")].value,
        fields[FieldName("region")].value,
        fields[FieldName("offset")].value,
        fields[FieldName("omitted")].value,
    ) == (1, "rgn_commarea", 0, False)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run --no-sync python -m pytest tests/unit/cobol/test_call_arguments.py -q`
Expected: FAIL. `ModuleNotFoundError: interpreter.cobol.call_arguments`.

- [ ] **Step 3: Implement**

In `cobol_memory/region_id.py`, add `CALL_ARGUMENT = "call_argument"` to `RegionId`.
Extend the module docstring's last sentence:
"…binds a callee's linkage region onto caller storage; CALL_ARGUMENT is the fresh
copy a BY CONTENT or BY VALUE argument is passed in."

Create `interpreter/cobol/call_arguments.py`:

```python
"""The argument array a CALL hands its callee: one region and offset per argument."""

from __future__ import annotations

from collections.abc import Sequence

from interpreter import constants
from interpreter.address import Address
from interpreter.field_name import FieldKind, FieldName
from interpreter.types.type_expr import UNKNOWN
from interpreter.types.typed_value import TypedValue, typed
from interpreter.vm.vm_types import HeapObject, Pointer, VMState


def call_arguments(vm: VMState, regions: Sequence[Address]) -> TypedValue:
    """For a harness frame: each region passed BY REFERENCE at offset 0."""
    elements = tuple(_element(vm, region) for region in regions)
    array = _fresh(vm, constants.ARR_ADDR_PREFIX)
    vm.heap_set(
        array,
        HeapObject(
            fields={
                FieldName("count"): typed(len(elements), UNKNOWN),
                **{
                    FieldName(str(position), FieldKind.INDEX): element
                    for position, element in enumerate(elements)
                },
            }
        ),
    )
    return typed(Pointer(base=array, offset=0), UNKNOWN)


def _element(vm: VMState, region: Address) -> TypedValue:
    element = _fresh(vm, constants.OBJ_ADDR_PREFIX)
    vm.heap_set(
        element,
        HeapObject(
            fields={
                FieldName("region"): typed(region.value, UNKNOWN),
                FieldName("offset"): typed(0, UNKNOWN),
                FieldName("omitted"): typed(False, UNKNOWN),
            }
        ),
    )
    return typed(Pointer(base=element, offset=0), UNKNOWN)


def _fresh(vm: VMState, prefix: str) -> Address:
    address = Address(f"{prefix}{vm.symbolic_counter}")
    vm.symbolic_counter += 1
    return address
```

- [ ] **Step 4: Run it and watch it pass**

Run: `uv run --no-sync python -m pytest tests/unit/cobol/test_call_arguments.py -q`
Expected: 1 passed.

- [ ] **Step 5: Mutation-check**

Change `FieldKind.INDEX` to the default kind, and the test fails. Change the offset
to 1, and the test fails. Restore both.

- [ ] **Step 6: Commit** (the hooks run the full suite; nothing else changes)

```bash
git add cobol_memory/region_id.py interpreter/cobol/call_arguments.py tests/unit/cobol/test_call_arguments.py
git commit -m "feat(cobol): call_arguments builds a CALL's argument array for harnesses"
```

---

### Task 2: The switch — caller array, handler, callee binding, shifted offsets

One commit, because the full suite runs at commit time. The packed-buffer shape tests
break the moment the caller changes.

**Files:**
- Modify: `interpreter/cobol/lower_call.py` (`lower_call`, plus removing `_params_extent`)
- Modify: `interpreter/instructions.py` (`CallWithMemory` loses `results_reg`;
  deserialiser `_call_with_memory`)
- Modify: `interpreter/handlers/calls.py` (`_handle_call_with_memory`)
- Modify: `interpreter/cobol/sectioned_layout.py` (`SectionedLayout`,
  `MaterialisedSectionedLayout`, `build_sectioned_layout`)
- Create: `interpreter/cobol/linkage_binding.py` (`LinkageRecord`, `LinkageBinding`,
  `bind_linkage`)
- Modify: `interpreter/cobol/lower_data_division.py` (`lower_sectioned_data_division`)
- Modify: `interpreter/cobol/emit_context.py` (`resolve_field_ref`,
  `resolve_field_ref_from`, new `_field_offset`)
- Modify: `interpreter/cobol/lower_arithmetic.py` (`_find_group_and_reg` and the
  `resolve_field_ref_from` callers at :881, :887, :948, :953)
- Modify: `interpreter/cobol/lower_string_inspect.py:303`
- Modify: `mcp_server/tools.py:552-558` (CALL_WITH_MEMORY opcode docs)
- Modify: `docs/frontend-design/cobol.md` (the `CALL 'prog' USING params` row)
- Test: `tests/integration/test_cobol_call_using_slots.py` (exists, untracked: the
  four reproductions)
- Test: `tests/integration/test_cobol_call_using_addresses.py` (new: Review Focus 1–5)
- Rewrite: `tests/unit/test_lower_call_with_memory.py`,
  `tests/unit/test_call_with_memory.py`,
  `tests/unit/test_handle_call_with_memory_singleton.py`,
  `tests/unit/test_lower_sectioned_data_division.py`,
  `tests/unit/cobol/test_recorded_memory_effects.py`
  (`test_call_using_a_linkage_item_records_the_linkage_region`,
  `test_the_call_argument_extent_cannot_alias_working_storage`)
- Flip: `tests/integration/test_cobol_programs.py`
  - `test_stop_run_loses_by_reference_write_known_gap` (:6733): remove the xfail and
    rename it to `test_stop_run_keeps_by_reference_writes`.
  - `test_callee_linkage_wider_than_caller_arg_reads_zero_pad` (TestCallUsingLinkageRead,
    :6177): assert the caller's next bytes and rename it to
    `test_callee_linkage_wider_than_caller_arg_reads_the_next_bytes`. Approved
    behaviour change 1.
  - A no-USING CALL test (TestSectionedDataDivision, :5507): the callee's LINKAGE
    reads zeros. Approved behaviour change 2.

**Interfaces:**
- Consumes: `RegionId.CALL_ARGUMENT` and the argument-array shape from Task 1.
- Produces:
  - `LinkageRecord(name: str, start: int, length: int)`, frozen.
  - `LinkageBinding(start: int, length: int, region_reg: Register, delta_reg: Register)`,
    frozen.
  - `SectionedLayout.linkage_parameters: tuple[LinkageRecord, ...]` (by USING
    position) and `SectionedLayout.linkage_unbound: tuple[LinkageRecord, ...]`.
  - `MaterialisedSectionedLayout.linkage_bindings: tuple[LinkageBinding, ...]` and
    `MaterialisedSectionedLayout.linkage_binding(fl: FieldLayout) -> LinkageBinding`.

- [ ] **Step 1: Write the Review Focus tests** — `tests/integration/test_cobol_call_using_addresses.py`

```python
"""Each callee LINKAGE 01 is bound to its own argument's address.

SHIFT declares LK-FIRST (8 bytes), LK-REC (11), a REDEFINES of LK-REC, and LK-OUT
(7), so their static starts are 0, 8, 8 and 19. The caller passes fields at offsets
13, 2 and 21, so every parameter runs at a non-zero shift (+13, -6, +2): a site
that adds no shift touches the wrong bytes.

Caller WORKING-STORAGE offsets:
- WS-HEAD 0-1;
- WS-REC 2-12 (WS-NUM 2-4, WS-TXT 5-8, WS-TAB 9-12);
- WS-FIRST 13-20;
- WS-OUT 21-27 (WS-NUM 21-23, WS-TXT 24-27);
- WS-SPARE 28-30.
"""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. ADDRS.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-HEAD   PIC X(2)  VALUE 'HH'.",
    "01 WS-REC.",
    "   05 WS-NUM  PIC 9(3) VALUE 5.",
    "   05 WS-TXT  PIC X(4) VALUE 'ABCD'.",
    "   05 WS-TAB  PIC X(2) OCCURS 2 VALUE 'TT'.",
    "01 WS-FIRST  PIC X(8)  VALUE 'FFFFFFFF'.",
    "01 WS-OUT.",
    "   05 WS-NUM  PIC 9(3) VALUE 0.",
    "   05 WS-TXT  PIC X(4) VALUE SPACES.",
    "01 WS-SPARE  PIC X(3)  VALUE 'SSS'.",
    "PROCEDURE DIVISION.",
    "    CALL 'SHIFT' USING WS-FIRST WS-REC WS-OUT.",
    "    CALL 'FEWER' USING WS-SPARE.",
    "    STOP RUN.",
]

_SHIFT = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. SHIFT.",
    "DATA DIVISION.",
    "LINKAGE SECTION.",
    "01 LK-FIRST  PIC X(8).",
    "01 LK-REC.",
    "   05 LK-NUM  PIC 9(3).",
    "   05 LK-TXT  PIC X(4).",
    "   05 LK-TAB  PIC X(2) OCCURS 2.",
    "01 LK-ALIAS REDEFINES LK-REC PIC X(11).",
    "01 LK-OUT.",
    "   05 LK-NUM  PIC 9(3).",
    "   05 LK-TXT  PIC X(4).",
    "PROCEDURE DIVISION USING LK-FIRST LK-REC LK-OUT.",
    "    ADD 1 TO LK-NUM OF LK-REC.",
    "    IF LK-TXT OF LK-REC = 'ABCD'",
    "        MOVE 'WXYZ' TO LK-TXT OF LK-REC",
    "    END-IF.",
    "    MOVE 'QQ' TO LK-TAB(2).",
    "    ADD CORRESPONDING LK-REC TO LK-OUT.",
    "    MOVE 'R' TO LK-ALIAS(11:1).",
    "    STRING 'AB' DELIMITED BY SIZE INTO LK-FIRST.",
    "    CALL 'DOWN' USING LK-REC.",
    "    GOBACK.",
]

_DOWN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. DOWN.",
    "DATA DIVISION.",
    "LINKAGE SECTION.",
    "01 LK-PASSED PIC X(11).",
    "PROCEDURE DIVISION USING LK-PASSED.",
    "    MOVE 'D' TO LK-PASSED(10:1).",
    "    GOBACK.",
]

_FEWER = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. FEWER.",
    "DATA DIVISION.",
    "LINKAGE SECTION.",
    "01 LK-GOT     PIC X(3).",
    "01 LK-NOTHING PIC X(3).",
    "PROCEDURE DIVISION USING LK-GOT LK-NOTHING.",
    "    MOVE LK-NOTHING TO LK-GOT.",
    "    GOBACK.",
]


def _ws() -> str:
    subs = {"SHIFT": _SHIFT, "DOWN": _DOWN, "FEWER": _FEWER}
    return bytes(ws_region(run_cobol_programs(_MAIN, subs), "ADDRS")).decode("cp037")


@covers(CobolFeature.CALL_USING)
def test_a_shifted_parameter_works_in_every_statement_kind() -> None:
    ws = _ws()

    assert (ws[0:2], ws[2:5], ws[5:9], ws[13:21], ws[21:28]) == (
        "HH",
        "006",
        "WXYZ",
        "ABFFFFFF",
        "006    ",
    )


@covers(CobolFeature.CALL_USING)
def test_a_parameter_passed_down_is_the_original_storage() -> None:
    assert _ws()[9:13] == "TTDR"


@covers(CobolFeature.CALL_USING)
def test_a_redefining_01_reads_through_the_same_argument() -> None:
    assert _ws()[12] == "R"


@covers(CobolFeature.CALL_USING)
def test_a_parameter_the_caller_did_not_pass_reads_zeros() -> None:
    assert _ws()[28:31].encode("cp037") == b"\x00\x00\x00"
```

Expected values, worked through by hand:
- **ADD 1:** `005` becomes `006`.
- **IF / MOVE:** `ABCD` becomes `WXYZ`.
- **MOVE 'QQ' TO LK-TAB(2):** WS-TAB becomes `TTQQ`.
- **ADD CORRESPONDING:** adds only the numeric `LK-NUM`, so WS-OUT becomes `006`
  followed by its original spaces.
- **LK-ALIAS(11:1):** writes byte 12, giving `TTQR`.
- **DOWN's LK-PASSED(10:1):** writes byte 11, giving `TTDR`.
- **FEWER's LK-NOTHING:** never passed, so it reads zeros into WS-SPARE.
- **STRING 'AB' INTO LK-FIRST:** overwrites the first two of its 8 bytes, giving
  `ABFFFFFF`.
- **WS-HEAD** is untouched. A wrong shift on any parameter would land inside it or
  inside a neighbouring field.

MOVE CORRESPONDING is deliberately absent: it ignores LINKAGE today
(`statement_dispatch.py:101` uses WORKING-STORAGE only), independent of this plan.

- [ ] **Step 2: Run the new tests and the four slot tests, and watch them fail**

Run: `uv run --no-sync python -m pytest tests/integration/test_cobol_call_using_slots.py tests/integration/test_cobol_call_using_addresses.py -q`
Expected: FAIL. Record each failing value in the ledger.

- [ ] **Step 3: `LinkageRecord`, `LinkageBinding`, and the static records** — `interpreter/cobol/linkage_binding.py`

```python
"""Each callee LINKAGE 01 bound to the address its caller passed for it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class LinkageRecord:
    """A LINKAGE 01 in the section's static, end-to-end layout."""

    name: str
    start: int
    length: int


@dataclass(frozen=True)
class LinkageBinding:
    """Where a LINKAGE 01 lives at run time: a region, and the shift from its
    static start to the argument's offset in that region."""

    start: int
    length: int
    region_reg: Register
    delta_reg: Register

    def holds(self, offset: int) -> bool:
        return self.start <= offset < self.start + max(self.length, 1)


def binding_at(bindings: Sequence[LinkageBinding], offset: int) -> LinkageBinding:
    return next(binding for binding in bindings if binding.holds(offset))
```

In `sectioned_layout.py`:
- add `linkage_parameters: tuple[LinkageRecord, ...] = ()` and
  `linkage_unbound: tuple[LinkageRecord, ...] = ()` to `SectionedLayout`;
- add `linkage_bindings: tuple[LinkageBinding, ...] = ()` to
  `MaterialisedSectionedLayout`, plus:

```python
    def linkage_binding(self, fl: FieldLayout) -> LinkageBinding:
        return binding_at(self.linkage_bindings, fl.offset)
```

- in `resolve_with_region`'s LINKAGE branch, return the 01's own region:

```python
        lk_layout, _ = self.linkage
        lk_fl = lk_layout.lookup_as_storage(name, qualifiers)
        if lk_fl is not None:
            return lk_fl, self.linkage_binding(lk_fl).region_reg, RegionId.LINKAGE
```

- in `build_sectioned_layout`, build the records from the same layout the static
  offsets come from:

```python
def build_sectioned_layout(asg: CobolASG) -> SectionedLayout:
    linkage_fields = laid_end_to_end(_in_using_order(asg))
    records = tuple(
        LinkageRecord(item.name.upper(), item.offset, _record_length(item))
        for item in linkage_fields
        if not item.redefines and not item.renames_from
    )
    named = [param.name.upper() for param in asg.procedure_using] or [
        record.name for record in records
    ]
    by_name = {record.name: record for record in records}
    return SectionedLayout(
        working_storage=build_data_layout(asg.data_fields),
        linkage=build_data_layout(linkage_fields),
        local_storage=build_data_layout(asg.local_storage_fields),
        file=build_data_layout(asg.file_fields),
        indexes=build_index_layout(
            asg.data_fields,
            asg.local_storage_fields,
            asg.linkage_fields,
            asg.file_fields,
        ),
        linkage_parameters=tuple(by_name[name] for name in named if name in by_name),
        linkage_unbound=tuple(r for r in records if r.name not in named),
    )
```

`_record_length` is `data_layout._compute_group_length`. Expose it as a public
`record_length(field: CobolField) -> int` in `data_layout.py` instead of importing
a private name.

- [ ] **Step 4: Callee prologue** — `bind_linkage` in `linkage_binding.py`, called from `lower_sectioned_data_division`

For each parameter at position *i*, emit:

```python
def bind_linkage(
    ctx: EmitContext,
    parameters: Sequence[LinkageRecord],
    unbound: Sequence[LinkageRecord],
) -> tuple[LinkageBinding, ...]:
    return (
        *(
            _bind_parameter(ctx, record, position)
            for position, record in enumerate(parameters)
        ),
        *(_placeholder(ctx, record) for record in unbound),
    )


def _bind_parameter(ctx: EmitContext, record: LinkageRecord, position: int) -> LinkageBinding:
    region_var = VarName(f"__linkage_{record.name}_region")
    delta_var = VarName(f"__linkage_{record.name}_delta")
    present, bind, absent, done = (
        ctx.fresh_label(f"lk_{tag}") for tag in ("present", "bind", "absent", "done")
    )
    args = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=args, name=VarName("__call_arguments")))
    count = ctx.fresh_reg()
    ctx.emit_inst(LoadField(result_reg=count, obj_reg=args, field_name=FieldName("count")))
    index = ctx.const_to_reg(position)
    passed = ctx.fresh_reg()
    ctx.emit_inst(Binop(result_reg=passed, operator=resolve_binop("<"), left=index, right=count))
    ctx.emit_inst(BranchIf(cond_reg=passed, branch_targets=(present, absent)))
    ctx.emit_inst(Label_(label=present))
    element = ctx.fresh_reg()
    ctx.emit_inst(LoadIndex(result_reg=element, arr_reg=args, index_reg=index))
    omitted = ctx.fresh_reg()
    ctx.emit_inst(LoadField(result_reg=omitted, obj_reg=element, field_name=FieldName("omitted")))
    ctx.emit_inst(BranchIf(cond_reg=omitted, branch_targets=(absent, bind)))
    ctx.emit_inst(Label_(label=bind))
    region = ctx.fresh_reg()
    ctx.emit_inst(LoadField(result_reg=region, obj_reg=element, field_name=FieldName("region")))
    offset = ctx.fresh_reg()
    ctx.emit_inst(LoadField(result_reg=offset, obj_reg=element, field_name=FieldName("offset")))
    _store_binding(ctx, record, region_var, delta_var, region, offset)
    ctx.emit_inst(Branch(label=done))
    ctx.emit_inst(Label_(label=absent))
    _store_zeroed(ctx, record, region_var, delta_var)
    ctx.emit_inst(Label_(label=done))
    return _loaded(ctx, record, region_var, delta_var)
```

The helpers behave as follows:
- `_store_binding` stores `region` and `offset − record.start` (`Binop "-"`) into the
  two variables.
- `_store_zeroed` stores an `AllocRegion` of `record.length` bytes and `−record.start`.
- `_placeholder` calls `_store_zeroed` unconditionally.
- `_loaded` `LoadVar`s both variables into fresh registers and returns
  `LinkageBinding(record.start, record.length, region_reg, delta_reg)`.

Every instruction here gets `span=None`. In `lower_sectioned_data_division`, replace
the `__params_region` load with:

```python
    bindings = bind_linkage(ctx, layout.linkage_parameters, layout.linkage_unbound)
```

Pass `linkage=(layout.linkage, NO_REGISTER)` and `linkage_bindings=bindings` to
`MaterialisedSectionedLayout`. Update the function's docstring to say LINKAGE is
bound per 01 from `__call_arguments`.

- [ ] **Step 5: Shifted offsets** — `emit_context.py`

Add a single offset funnel and use it at every site that resolves a named field:

```python
    def _field_offset(
        self,
        fl: FieldLayout,
        region: RegionId,
        materialised: MaterialisedSectionedLayout,
        *,
        span: SourceSpan | None = None,
    ) -> Register:
        """The field's offset in its region at run time: a LINKAGE field moves by
        its 01's shift, every other field sits at its static offset."""
        static = self.const_to_reg(fl.offset, span=span)
        if region is not RegionId.LINKAGE:
            return static
        shifted = self.fresh_reg()
        self.emit_inst(
            Binop(
                result_reg=shifted,
                operator=resolve_binop("+"),
                left=static,
                right=materialised.linkage_binding(fl).delta_reg,
            ),
            span=span,
        )
        return shifted
```

Replace these with `_field_offset`:
- `Const.int_(offset_reg, fl.offset)` at :531 (unsubscripted `resolve_field_ref`);
- `self.const_to_reg(fl.offset, span=span)` at :602 and :652 (subscripted bases);
- the same constant at :718, after giving `resolve_field_ref_from` a
  `materialised: MaterialisedSectionedLayout` parameter. Pass it at
  `lower_arithmetic.py` :881, :887, :948 and :953.

In `lower_arithmetic.py` `_find_group_and_reg` (:897), the LINKAGE candidate's
register becomes the group's binding region:

```python
    lk_layout, _ = materialised.linkage
    candidates = (
        (*materialised.working_storage, RegionId.WORKING_STORAGE),
        (*materialised.local_storage, RegionId.LOCAL_STORAGE),
    )
```

Search LINKAGE separately. When a group is found there, return
`materialised.linkage_binding(group_fl).region_reg`.

For `lower_string_inspect.py:303`, read the surrounding function. If
`target_ref.fl.offset` is used as a run-time offset, use `target_ref.offset_reg`
instead.

**Audit step.** List every call to `_materialise_offset`, i.e. every
`emit_encode_and_write` / `emit_decode_field` / encode and decode helper call that
passes no offset register:

```bash
rg -n "emit_encode_and_write\(|emit_decode_field\(|emit_decode\(|emit_encode\(" interpreter/cobol --type py -A6 | rg -v "offset_reg|\.offset_reg"
```

Each call whose field can be a LINKAGE field must pass the resolved
`offset_reg`. Record each call site and its verdict in the ledger.

- [ ] **Step 6: Caller builds the argument array** — `lower_call.py`

Replace the body of `lower_call` from `param_fls` through the `CallWithMemory`
emission, and delete the copy-back block and `_params_extent`:

```python
    span = stmt.span
    args_reg = _argument_array(ctx, stmt.using, materialised, span=span)
    target = stmt.target
    target_reg = (
        _emit_callee_name(ctx, target.identifier, materialised, span=span)
        if target.identifier is not None
        else NO_REGISTER
    )
    result_reg = emit_return_code_load(ctx, materialised, span=span)
    ctx.emit_inst(
        CallWithMemory(
            result_reg=result_reg,
            func_name=FuncName(target.literal),
            params_reg=args_reg,
            target_reg=target_reg,
        ),
        span=span,
    )
```

Keep `emit_return_code_store`, the `__ws_region` repair and GIVING exactly as they
are. Add:

```python
def _argument_array(
    ctx: EmitContext,
    using: Sequence[CallUsingParam],
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    """One element per USING argument, by position: a region, an offset, and
    whether it was OMITTED."""
    args = ctx.fresh_reg()
    ctx.emit_inst(
        NewArray(result_reg=args, size_reg=ctx.const_to_reg(len(using), span=span)),
        span=span,
    )
    _store_field(ctx, args, "count", ctx.const_to_reg(len(using), span=span), span)
    for position, param in enumerate(using):
        element = _argument(ctx, param, materialised, span=span)
        ctx.emit_inst(
            StoreIndex(
                arr_reg=args,
                index_reg=ctx.const_to_reg(position, span=span),
                value_reg=element,
            ),
            span=span,
        )
    return args
```

`_argument` builds one `NewObject` with `region`, `offset` and `omitted` fields:
- **OMITTED:** `omitted=True`; `region` and `offset` are left unset.
- **Literal:** `_literal_copy`, i.e. `AllocRegion(len(text))`, then
  `emit_encode_and_write` of the literal text (quotes stripped with
  `strip_cobol_literal`) through a synthetic
  `FieldLayout(name="%LITERAL", type_descriptor=parse_pic(f"X({len(text)})"), offset=0, byte_length=len(text))`.
  Its extent is `FieldExtent(RegionId.CALL_ARGUMENT, 0, len(text), Precision.EXACT, "%LITERAL")`.
  The element gets region = that copy, `offset=0`, `omitted=False`.
- **BY REFERENCE:** `ref, region_reg = ctx.resolve_field_ref(param.name, materialised, span=span)`.
  The element gets region = `region_reg`, offset = `ref.offset_reg`, `omitted=False`.
- **BY CONTENT / BY VALUE:** resolve the same way, then
  `AllocRegion(ref.fl.byte_length)`. Copy with `_emit_load_region` (extent
  `ref.extent`) and `_emit_write_region` (extent
  `FieldExtent(RegionId.CALL_ARGUMENT, 0, n, Precision.EXACT, param.name)`). The
  element gets region = the copy, `offset=0`, `omitted=False`.

`_store_field(ctx, obj, name, value_reg, span)` emits
`StoreField(obj_reg=obj, field_name=FieldName(name), value_reg=value_reg)`.

The old no-USING branch, which passed the caller's WORKING-STORAGE, is gone: an
empty `using` builds an empty array.

- [ ] **Step 7: Handler and instruction**

In `instructions.py`, delete `CallWithMemory.results_reg`, its operand, its
`reads()` entry, and the deserialiser's reading of it (`_call_with_memory`, :1424).
Update the class docstring: `params_reg` holds the argument array.

In `handlers/calls.py` `_handle_call_with_memory`:
- drop `results_tv`;
- inject `{VarName("__call_arguments"): params_tv}`;
- update the protocol docstring and the `reasoning` string.

In `mcp_server/tools.py:552-558`, describe the operand as the argument array.

- [ ] **Step 8: Run the slot and Review Focus tests and watch them pass**

Run: `uv run --no-sync python -m pytest tests/integration/test_cobol_call_using_slots.py tests/integration/test_cobol_call_using_addresses.py -q`
Expected: 8 passed.

- [ ] **Step 9: Rewrite the shape tests, flip the approved behaviour changes, run the suite**

Rewrite the unit tests listed under **Files** to pin the new shape:
- `NewArray` / `StoreField count` / `StoreIndex` per argument;
- no `ALLOC_REGION` for a BY REFERENCE argument;
- one `ALLOC_REGION` and one copy per BY CONTENT argument, written with
  `RegionId.CALL_ARGUMENT`;
- `__call_arguments` injected;
- no copy-back after the call.

Flip the three integration tests named under **Files**. Then:

Run: `uv run --no-sync python -m pytest tests -q -x -p no:randomly > /tmp/rd-suite.log 2>&1; tail -3 /tmp/rd-suite.log`
Expected: all pass, with 1 fewer xfail than before (zerg).

- [ ] **Step 10: Mutation-check**

Each of these must fail at least one of the eight tests:
1. `_field_offset` returns `static` for LINKAGE too.
2. `_argument` passes `offset=0` for BY REFERENCE.
3. `bind_linkage` treats OMITTED as present.
4. BY CONTENT passes the caller's region instead of the copy.

Restore all four.

- [ ] **Step 11: Living docs, then commit**

In `docs/frontend-design/cobol.md`, rewrite the `CALL 'prog' USING params` row:
- the argument array;
- BY REFERENCE shares the caller's bytes;
- BY CONTENT / BY VALUE / literal pass a fresh `CALL_ARGUMENT` copy;
- OMITTED and absent parameters bind zero-filled storage;
- each LINKAGE 01 is bound from `__call_arguments` with a shift added to its
  fields' static offsets;
- the BY REFERENCE writes STOP RUN used to lose are kept.

Remove the STOP RUN known-gap bullet (`cobol.md:245`).

```bash
git add -A interpreter cobol_memory mcp_server tests docs/frontend-design/cobol.md
git commit  # message: "feat(cobol): CALL USING passes one address per argument" — body lists the four fixed cases, zerg, the approved behaviour changes; Closes w8t3, zerg.
```

Then push, close w8t3 and zerg in `bd`, and export and commit `issues/issues.jsonl`.

---

### Task 3 (forge): bump red-dragon and move cicada and jackal to `call_arguments`

**Files (in `~/code/red-dragon-forge`):**
- Modify: `vendor/red-dragon` (pointer)
- Modify: `cicada/cics/vm_init.py:16-40`, `cicada/cics/conversational.py:36-60`,
  `jackal/jackal/cobol_step.py:72-114`

**Interfaces:**
- Consumes: `call_arguments(vm, regions)` from Task 1.

- [ ] **Step 1: Bump and rebuild**

```bash
cd vendor/red-dragon && git fetch -q && git checkout <task-2 head> && git submodule update --init --recursive && cd ../.. && make jar-force
```

- [ ] **Step 2: Watch the harness tests fail**

Run: `. ./bridge-env.sh && cd cicada && uv run --no-sync python -m pytest tests/integration/cics/test_commarea_roundtrip.py tests/integration/cics/test_link.py -q; cd ../jackal && uv run --no-sync python -m pytest tests/integration/test_parm_cobol_step.py -q`
Expected: FAIL, because the callee reads `__call_arguments` and the harnesses still
set `__params_region`.

- [ ] **Step 3: Move the harnesses**

In each of the three frames, replace the `__params_region` entry with:

```python
VarName("__call_arguments"): call_arguments(vm, [commarea_addr]),
```

Use `parm_vm` and `parm_addr` in `jackal/jackal/cobol_step.py`, importing
`from interpreter.cobol.call_arguments import call_arguments`. Create the VM, then
the region, then the frame, because `call_arguments` writes heap objects into the VM
it is given. Update `make_cics_initial_vm`'s docstring: COMMAREA is argument 0 and
binds DFHCOMMAREA.

- [ ] **Step 4: Run every forge suite**

Run: `docker inspect --format '{{.State.Health.Status}}' squall-db2` (restart if not
healthy), then `. ./bridge-env.sh && SQUALL_DIR=squall . squall/db2/dsn-env.sh && make test-all`.
Expected: all five suites pass.

- [ ] **Step 5: Commit both together and push**

```bash
git add vendor/red-dragon cicada/cics/vm_init.py cicada/cics/conversational.py jackal/jackal/cobol_step.py
git commit  # "chore: bump red-dragon to <sha> (CALL USING by address); move cicada and jackal to call_arguments"
git push
```
