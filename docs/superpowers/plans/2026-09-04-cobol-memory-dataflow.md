# COBOL Memory-Level Dataflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make COBOL field assignments visible to dataflow analysis by modelling a field as `(region, byte-range)` and aliasing as byte-range overlap, producing a field-level dependency graph.

**Architecture:** `interpreter/dataflow.py` currently decides "same storage?" by name equality hard-coded into `Definition.__eq__`. We extract that into an `AbstractLocation` protocol with `may_alias`/`must_cover`/`alias_key`, supply a second implementation (`FieldExtent`) whose relation is byte-range overlap, and have the COBOL frontend emit memory effects into a sidecar during lowering — the only place holding both the source construct and the byte layout.

**Tech Stack:** Python 3.13, pytest (xdist, 10 workers), uv, black, ProLeap COBOL parser via Java bridge JAR.

**Spec:** `docs/superpowers/specs/2026-09-04-cobol-memory-dataflow-design.md`

## Global Constraints

- **Package manager is `uv`, never Poetry.** Tests: `uv run python -m pytest`. Format: `uv run python -m black .`
- **This worktree requires `/usr/bin/git` (absolute path).** The rtk hook rewrites bare `git` → `rtk git`, which the worktree guard refuses.
- **`git commit` triggers a pre-commit hook running the full suite (~10 min).** Always run commits with `run_in_background: true` or a timeout ≥ 600000 ms. Never the default 2-minute timeout.
- **A fresh worktree needs `git submodule update --init --recursive` then `make jar`** before any COBOL test will pass. Already done in this worktree.
- **Never pipe test commands into `tail`/`head`** — the pipeline's exit code is the pipe's, not pytest's, so failures read as success. Redirect to a file and check `$?` separately.
- **Every layout test fixture must include neighbouring fields on both sides of the field under test, and assert their extents too.** Single-field fixtures cannot catch width errors; that is how `red-dragon-ilb6` and `red-dragon-r9s9` shipped.
- Baseline at plan time: 15147 tests collected, suite green, HEAD `7f11ac74`.

---

### Task 1: Universal instruction identity

**Files:**
- Modify: `interpreter/instructions.py:110-118` (`InstructionBase`)
- Modify: `interpreter/cobol/emit_context.py:139-158` (`fresh_reg` neighbourhood, `emit_inst`)
- Test: `tests/unit/test_instruction_id.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `InstructionId` (NewType over `int`), `NO_INSTRUCTION_ID: InstructionId`, field `InstructionBase.id: InstructionId`, and `EmitContext.emit_inst` assigning sequential ids.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_instruction_id.py`:

```python
"""Instruction identity — a stable coordinate independent of position."""

from interpreter.instructions import NO_INSTRUCTION_ID, Const
from interpreter.register import Register


def test_instruction_id_defaults_to_absent():
    inst = Const.int_(Register("%0"), 1)
    assert inst.id == NO_INSTRUCTION_ID


def test_instruction_id_does_not_affect_equality():
    a = Const.int_(Register("%0"), 1)
    b = Const.int_(Register("%0"), 1)
    from dataclasses import replace

    assert a == b
    assert replace(a, id=7) == replace(b, id=9)
    assert hash(replace(a, id=7)) == hash(replace(b, id=9))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/test_instruction_id.py -v -p no:xdist`
Expected: FAIL with `ImportError: cannot import name 'NO_INSTRUCTION_ID'`

- [ ] **Step 3: Add the field**

In `interpreter/instructions.py`, above `class InstructionBase`:

```python
InstructionId = NewType("InstructionId", int)
NO_INSTRUCTION_ID = InstructionId(-1)
```

Add `NewType` to the `typing` import. Then add to `InstructionBase` (after `branch_targets`, so it stays last and does not disturb positional construction):

```python
    id: InstructionId = field(default=NO_INSTRUCTION_ID, compare=False)
```

`compare=False` keeps value equality meaning "structurally identical instruction". Sidecars key on `inst.id`, never on `inst`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/test_instruction_id.py -v -p no:xdist`
Expected: PASS

- [ ] **Step 5: Write the failing test for the mint**

Append to `tests/unit/test_instruction_id.py`:

```python
def test_emit_context_assigns_sequential_ids():
    from interpreter.cobol.emit_context import EmitContext

    ctx = EmitContext()
    a = ctx.emit_inst(Const.int_(Register("%0"), 1))
    b = ctx.emit_inst(Const.int_(Register("%1"), 2))
    assert a.id != NO_INSTRUCTION_ID
    assert b.id == a.id + 1
```

If `EmitContext()` requires constructor arguments, read `interpreter/cobol/emit_context.py` for its `__init__` signature and supply the minimum; do not change that signature.

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/test_instruction_id.py::test_emit_context_assigns_sequential_ids -v -p no:xdist`
Expected: FAIL — ids are `NO_INSTRUCTION_ID`

- [ ] **Step 7: Implement the mint**

In `interpreter/cobol/emit_context.py`, add `self._inst_counter = 0` to `__init__`, and replace `emit_inst` (line 155):

```python
    def emit_inst(self, inst: InstructionBase) -> InstructionBase:
        """Emit a typed instruction directly, assigning it a stable id."""
        inst = replace(inst, id=InstructionId(self._inst_counter))
        self._inst_counter += 1
        self._instructions.append(inst)
        return inst
```

Import `replace` from `dataclasses` and `InstructionId` from `interpreter.instructions`.

- [ ] **Step 8: Preserve ids across rewriting**

In `interpreter/instructions.py`, `map_registers` constructs a new instruction from an old one — the same instruction, rewritten — so it must carry `id` through. Read its body; if it uses `dataclasses.replace` the id is preserved automatically and no change is needed. If it constructs a fresh instance field-by-field, add `id=self.id` to the construction. Add this test either way:

```python
def test_map_registers_preserves_id():
    from dataclasses import replace

    inst = replace(Const.int_(Register("%0"), 1), id=42)
    assert inst.map_registers(lambda r: r).id == 42
```

- [ ] **Step 9: Run the full suite**

Run: `uv run python -m pytest > /tmp/t1.txt 2>&1; echo "EXIT=$?"`
Expected: `EXIT=0`. Investigate any failure before committing — a failure here means something does compare instructions by value.

- [ ] **Step 10: Format and commit**

```bash
uv run python -m black .
/usr/bin/git add interpreter/instructions.py interpreter/cobol/emit_context.py tests/unit/test_instruction_id.py
/usr/bin/git commit -m "feat(ir): universal instruction id as a stable sidecar coordinate"
```

---

### Task 2: The AbstractLocation protocol

**Files:**
- Create: `interpreter/abstract_location.py`
- Modify: `interpreter/register.py` (add two methods to `Register`)
- Modify: `interpreter/var_name.py` (add two methods to `VarName`)
- Test: `tests/unit/test_abstract_location.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: protocol `AbstractLocation` with `may_alias(other) -> bool`, `must_cover(other) -> bool`, `alias_key() -> Hashable`. `Register` and `VarName` implement it with name-equality semantics.

`alias_key()` exists for performance: `compute_gen_kill` currently does an O(1) dict lookup keyed by the identifier. Overlap cannot be a dict lookup, so `alias_key()` returns a coarse **bucket** — exact identity for names (preserving O(1)), and the region for extents (a small scan within one region instead of over all definitions).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_abstract_location.py`:

```python
"""AbstractLocation — the alias relation, extracted from Definition.__eq__."""

from interpreter.abstract_location import AbstractLocation
from interpreter.register import Register
from interpreter.var_name import VarName


def test_register_aliases_only_itself():
    a, b = Register("%0"), Register("%0")
    c = Register("%1")
    assert a.may_alias(b) and a.must_cover(b)
    assert not a.may_alias(c) and not a.must_cover(c)


def test_varname_does_not_alias_register_of_same_text():
    assert not VarName("x").may_alias(Register("x"))
    assert not Register("x").may_alias(VarName("x"))


def test_alias_key_buckets_by_identity_for_names():
    assert Register("%0").alias_key() == Register("%0").alias_key()
    assert Register("%0").alias_key() != Register("%1").alias_key()
    assert VarName("x").alias_key() != Register("x").alias_key()


def test_register_and_varname_satisfy_the_protocol():
    assert isinstance(Register("%0"), AbstractLocation)
    assert isinstance(VarName("x"), AbstractLocation)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/test_abstract_location.py -v -p no:xdist`
Expected: FAIL with `ModuleNotFoundError: No module named 'interpreter.abstract_location'`

- [ ] **Step 3: Create the protocol**

Create `interpreter/abstract_location.py`:

```python
# pyright: standard
"""AbstractLocation — the alias relation between storage locations.

Reaching definitions asks one question of two accesses: do they touch the
same storage? For named locations (registers, variables) the answer is name
equality. For COBOL fields — byte slices of a shared region buffer — it is
byte-range overlap. Both are instances of this protocol, so one analysis
serves both.
"""

from __future__ import annotations

from typing import Hashable, Protocol, runtime_checkable


@runtime_checkable
class AbstractLocation(Protocol):
    """A storage location that knows how it aliases other locations."""

    def may_alias(self, other: AbstractLocation) -> bool:
        """True if a write here MIGHT be observed by a read of ``other``.

        Over-approximating: when in doubt, return True. Used to build GEN and
        to match uses against reaching definitions.
        """
        ...

    def must_cover(self, other: AbstractLocation) -> bool:
        """True if a write here DEFINITELY overwrites all of ``other``.

        Under-approximating: when in doubt, return False. Only a must-cover
        write may KILL a definition; returning True wrongly silently drops
        dependencies.
        """
        ...

    def alias_key(self) -> Hashable:
        """A coarse bucket key. Two locations that may alias MUST share a key.

        Lets the analysis narrow candidates by dict lookup before doing the
        pairwise overlap test.
        """
        ...
```

- [ ] **Step 4: Implement on Register**

In `interpreter/register.py`, inside `class Register`:

```python
    def may_alias(self, other: object) -> bool:
        return isinstance(other, Register) and other.name == self.name

    def must_cover(self, other: object) -> bool:
        return self.may_alias(other)

    def alias_key(self) -> tuple[str, str]:
        return ("register", self.name)
```

- [ ] **Step 5: Implement on VarName**

In `interpreter/var_name.py`, inside `class VarName`, mirroring the above. Read the class first to confirm its value attribute's name (it may be `name` or `value`) and use the real one:

```python
    def may_alias(self, other: object) -> bool:
        return isinstance(other, VarName) and other == self

    def must_cover(self, other: object) -> bool:
        return self.may_alias(other)

    def alias_key(self) -> tuple[str, str]:
        return ("varname", str(self))
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/test_abstract_location.py -v -p no:xdist`
Expected: PASS (4 tests)

- [ ] **Step 7: Commit**

```bash
uv run python -m black .
/usr/bin/git add interpreter/abstract_location.py interpreter/register.py interpreter/var_name.py tests/unit/test_abstract_location.py
/usr/bin/git commit -m "feat(dataflow): extract the alias relation into AbstractLocation"
```

---

### Task 3: Refactor dataflow.py onto the alias relation

**Files:**
- Modify: `interpreter/dataflow.py:137-174` (`compute_gen_kill`), `:265-...` (`extract_def_use_chains`), `_build_defs_by_variable`
- Test: `tests/unit/test_dataflow.py` (must pass **unchanged**)
- Test: `tests/unit/test_dataflow_alias_refactor.py` (create)

**Interfaces:**
- Consumes: `AbstractLocation.may_alias/must_cover/alias_key` from Task 2.
- Produces: `compute_gen_kill` and `extract_def_use_chains` with unchanged signatures, now dispatching through the alias relation.

**This is the highest-blast-radius task and it is behaviour-preserving.** With name-equality locations, `must_cover` is equality, so "remove prior definitions this one must-covers" is exactly "last write wins", and the KILL set is unchanged. If any existing test needs editing, the refactor was *not* behaviour-preserving — stop and re-derive rather than editing the test.

**Do NOT touch `Definition.__hash__` / `Definition.__eq__` (`dataflow.py:35-45`).** This addresses spec risk 7.1. They key on `(variable, block_label, instruction_index)`, and that stays correct once `variable` can be a `FieldExtent`: `FieldExtent` is a frozen dataclass, so it is hashable and its equality is field-wise. Two *different* extents are legitimately two different definitions — the aliasing question is asked separately, by `may_alias`/`must_cover`, and never by `Definition` equality. Conflating the two (making `__eq__` alias-aware) would break the hash/equality contract, since `may_alias` is not transitive and therefore cannot induce a valid hash.

- [ ] **Step 1: Write the characterization test**

Create `tests/unit/test_dataflow_alias_refactor.py`:

```python
"""GEN/KILL expressed via the alias relation, on name-equality locations."""

from interpreter.dataflow import compute_gen_kill, collect_all_definitions
from interpreter.cfg import build_cfg
from interpreter.instructions import Const, StoreVar
from interpreter.register import Register
from interpreter.var_name import VarName


def _cfg(instructions):
    return build_cfg(instructions)


def test_gen_keeps_only_the_last_write_of_a_variable():
    insts = [
        Const.int_(Register("%0"), 1),
        StoreVar(name=VarName("x"), value_reg=Register("%0")),
        Const.int_(Register("%1"), 2),
        StoreVar(name=VarName("x"), value_reg=Register("%1")),
    ]
    cfg = _cfg(insts)
    block = next(iter(cfg.blocks.values()))
    all_defs = collect_all_definitions(cfg)
    defs_by_var = {}
    for d in all_defs:
        defs_by_var.setdefault(d.variable, set()).add(d)

    gen, _kill = compute_gen_kill(block, all_defs, defs_by_var)
    x_defs = [d for d in gen if d.variable == VarName("x")]
    assert len(x_defs) == 1, "only the last write of x belongs in GEN"
    assert x_defs[0].instruction_index == 3
```

If `build_cfg` needs a different call shape, read `interpreter/cfg.py` and adapt — do not change `build_cfg`.

- [ ] **Step 2: Run it against current code to confirm it passes**

Run: `uv run python -m pytest tests/unit/test_dataflow_alias_refactor.py -v -p no:xdist`
Expected: PASS. This test pins existing behaviour *before* the refactor, so a regression is visible.

- [ ] **Step 3: Refactor GEN**

In `interpreter/dataflow.py`, replace the GEN computation in `compute_gen_kill` (lines 158-162):

```python
    # GEN = the writes that survive to the block exit. A later write removes
    # an earlier one only if it definitely overwrites all of it (must_cover);
    # a write that merely MIGHT overlap coexists with what was there.
    gen_list: list[Definition] = []
    for d in block_defs:
        gen_list = [prior for prior in gen_list if not d.variable.must_cover(prior.variable)]
        gen_list.append(d)
    gen = set(gen_list)
```

- [ ] **Step 4: Refactor KILL**

Replace the KILL computation (lines 164-172):

```python
    # KILL = definitions elsewhere that this block's writes definitely
    # overwrite. Only a must-cover write kills; a may-overlap write cannot.
    block_def_set = set(block_defs)
    kill = {
        other
        for d in block_defs
        for other in defs_by_var.get(d.variable.alias_key(), set())
        if other not in block_def_set and d.variable.must_cover(other.variable)
    }
```

- [ ] **Step 5: Rekey the definition index**

`defs_by_var` is now keyed by `alias_key()` rather than by the location. Update `_build_defs_by_variable` to key on `d.variable.alias_key()`, and update its type annotation to `dict[Hashable, set[Definition]]`. Update the annotation on `compute_gen_kill`'s `defs_by_var` parameter to match. Update the helper in the Step 1 test to use `d.variable.alias_key()` as its key too.

- [ ] **Step 6: Refactor def-use matching**

In `extract_def_use_chains`, replace the reach_in scan:

```python
                    matching_defs = [
                        d for d in reach_in if d.variable.may_alias(var)
                    ]
```

The `local_defs` dict is keyed by the location and shadows by exact identity. Leave it: for name locations it is exactly today's behaviour, and Task 8 revisits it for extents.

- [ ] **Step 7: Run the dataflow tests unchanged**

Run: `uv run python -m pytest tests/unit/test_dataflow.py tests/unit/test_dataflow_alias_refactor.py -v -p no:xdist`
Expected: PASS, with **no edits to `test_dataflow.py`**.

- [ ] **Step 8: Run the full suite**

Run: `uv run python -m pytest > /tmp/t3.txt 2>&1; echo "EXIT=$?"`
Expected: `EXIT=0`

- [ ] **Step 9: Commit**

```bash
uv run python -m black .
/usr/bin/git add interpreter/dataflow.py tests/unit/test_dataflow_alias_refactor.py
/usr/bin/git commit -m "refactor(dataflow): dispatch GEN/KILL through the alias relation"
```

---

### Task 4: RegionId

**Files:**
- Create: `interpreter/cobol/region_id.py`
- Modify: `interpreter/cobol/sectioned_layout.py:49-91` (`MaterialisedSectionedLayout.resolve`)
- Test: `tests/unit/cobol/test_region_id.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `RegionId` (str-valued `Enum`) with members `WORKING_STORAGE`, `LINKAGE`, `LOCAL_STORAGE`, `FILE`, `SPECIAL_REGISTERS`, `INDEXES`; and `MaterialisedSectionedLayout.resolve_with_region(name, qualifiers) -> tuple[FieldLayout, Register, RegionId]`.

`resolve()` already knows which section matched and discards it. Add a sibling rather than changing `resolve()`'s return arity, so existing call sites are untouched.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/cobol/test_region_id.py`:

```python
"""RegionId — which of the (at most six) section buffers a field lives in."""

import pytest

from interpreter.cobol.region_id import RegionId


def test_region_ids_are_the_six_section_buffers():
    assert {r.value for r in RegionId} == {
        "working_storage",
        "linkage",
        "local_storage",
        "file",
        "special_registers",
        "indexes",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_region_id.py -v -p no:xdist`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create the enum**

Create `interpreter/cobol/region_id.py`:

```python
# pyright: standard
"""RegionId — the DATA DIVISION section buffers a COBOL field can live in.

lower_data_division emits one AllocRegion per non-empty section, so a field
address is (region, byte offset). Two fields can alias only within the same
region; across regions there is no overlap, because they are separate byte
buffers. LINKAGE is the exception in scope 2, where CALL USING deliberately
binds a callee's linkage region onto caller storage.
"""

from __future__ import annotations

from enum import Enum


class RegionId(Enum):
    WORKING_STORAGE = "working_storage"
    LINKAGE = "linkage"
    LOCAL_STORAGE = "local_storage"
    FILE = "file"
    SPECIAL_REGISTERS = "special_registers"
    INDEXES = "indexes"
```

- [ ] **Step 4: Write the failing test for resolve_with_region**

Append to `tests/unit/cobol/test_region_id.py`:

```python
def test_resolve_reports_the_owning_region(cobol_frontend_probe):
    """WORKING-STORAGE fields resolve to the WORKING_STORAGE region."""
    materialised = cobol_frontend_probe
    _fl, _reg, region = materialised.resolve_with_region("WS-A1")
    assert region is RegionId.WORKING_STORAGE
```

Build the `cobol_frontend_probe` fixture in the same file by parsing this source and returning the `MaterialisedSectionedLayout`. Read `interpreter/cobol/cobol_frontend.py` to find how the materialised layout is reached after `lower()`; follow the pattern used by `tests/unit/cobol/test_sectioned_layout_group_leaves.py`.

```cobol
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-A.
           05  WS-A1  PIC X(10).
           05  WS-A2  PIC 9(5).
       01  WS-B      PIC X(4).
       PROCEDURE DIVISION.
           MOVE 'HI' TO WS-A1.
           STOP RUN.
```

Note the parser takes **bytes**, not `str` (`decode_source` calls `.decode`), and needs `make_cobol_parser()` from `cobol_asg.cobol_parser`.

- [ ] **Step 5: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_region_id.py -v -p no:xdist`
Expected: FAIL with `AttributeError: 'MaterialisedSectionedLayout' object has no attribute 'resolve_with_region'`

- [ ] **Step 6: Implement resolve_with_region**

In `interpreter/cobol/sectioned_layout.py`, add a method mirroring `resolve()`'s existing precedence (LOCAL-STORAGE > WORKING-STORAGE > LINKAGE > FILE > SPECIAL-REGISTERS > INDEXES), returning the `RegionId` alongside. Then re-express `resolve()` in terms of it so the precedence logic exists once:

```python
    def resolve(
        self, name: str, qualifiers: tuple[str, ...] = ()
    ) -> tuple[FieldLayout, Register]:
        fl, reg, _region = self.resolve_with_region(name, qualifiers)
        return fl, reg
```

Keep `resolve()`'s docstring and the LOCAL-STORAGE/WORKING-STORAGE collision warning — move the warning into `resolve_with_region`.

- [ ] **Step 7: Run tests**

Run: `uv run python -m pytest tests/unit/cobol/test_region_id.py -v -p no:xdist`
Expected: PASS

- [ ] **Step 8: Run the full suite and commit**

```bash
uv run python -m pytest > /tmp/t4.txt 2>&1; echo "EXIT=$?"
uv run python -m black .
/usr/bin/git add interpreter/cobol/region_id.py interpreter/cobol/sectioned_layout.py tests/unit/cobol/test_region_id.py
/usr/bin/git commit -m "feat(cobol): report the owning region from field resolution"
```

---

### Task 5: FieldExtent and its alias algebra

**Files:**
- Create: `interpreter/cobol/field_extent.py`
- Test: `tests/unit/cobol/test_field_extent.py` (create)

**Interfaces:**
- Consumes: `RegionId` (Task 4), `AbstractLocation` (Task 2).
- Produces: `Precision` enum (`EXACT`, `CLAMPED`) and

```python
@dataclass(frozen=True)
class FieldExtent:
    region: RegionId
    start: int
    length: int
    precision: Precision
    field_name: str
```

implementing `may_alias`, `must_cover`, `alias_key`.

`must_cover` requires `EXACT` precision: a CLAMPED extent is "somewhere in this range", so it can never be known to overwrite all of anything. This is the predicate whose failure mode is silent dependency loss, so it is tested directly.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/cobol/test_field_extent.py`:

```python
"""FieldExtent alias algebra — overlap, subsumption, and the laws they obey."""

import pytest

from interpreter.cobol.field_extent import FieldExtent, Precision
from interpreter.cobol.region_id import RegionId

WS = RegionId.WORKING_STORAGE
LK = RegionId.LINKAGE


def ext(start, length, region=WS, precision=Precision.EXACT, name="F"):
    return FieldExtent(
        region=region, start=start, length=length, precision=precision, field_name=name
    )


def test_group_covers_its_children():
    group = ext(0, 15, name="WS-A")
    child_a = ext(0, 10, name="WS-A1")
    child_b = ext(10, 5, name="WS-A2")
    assert group.must_cover(child_a) and group.must_cover(child_b)
    assert not child_a.must_cover(group)


def test_adjacent_fields_do_not_overlap():
    """WS-A1 is bytes 0-9 and WS-A2 is bytes 10-14; they must not alias."""
    assert not ext(0, 10).may_alias(ext(10, 5))
    assert not ext(10, 5).may_alias(ext(0, 10))


def test_redefines_overlap_at_the_same_offset():
    assert ext(0, 15, name="WS-A").may_alias(ext(0, 4, name="WS-A-ALT"))


def test_different_regions_never_alias():
    assert not ext(0, 10, region=WS).may_alias(ext(0, 10, region=LK))
    assert not ext(0, 10, region=WS).must_cover(ext(0, 10, region=LK))


def test_clamped_extent_may_alias_but_never_covers():
    """A computed subscript lands SOMEWHERE in the table, so it cannot kill."""
    table = ext(20, 50, precision=Precision.CLAMPED, name="WS-TAB")
    element = ext(22, 3, name="WS-QTY")
    assert table.may_alias(element)
    assert not table.must_cover(element)


def test_must_cover_implies_may_alias():
    a, b = ext(0, 15), ext(0, 10)
    assert a.must_cover(b)
    assert a.may_alias(b)


def test_may_alias_is_symmetric():
    a, b = ext(0, 15), ext(10, 20)
    assert a.may_alias(b) == b.may_alias(a)


def test_zero_length_extent_aliases_nothing():
    assert not ext(0, 0).may_alias(ext(0, 10))


def test_alias_key_buckets_by_region():
    assert ext(0, 10, region=WS).alias_key() == ext(99, 1, region=WS).alias_key()
    assert ext(0, 10, region=WS).alias_key() != ext(0, 10, region=LK).alias_key()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_field_extent.py -v -p no:xdist`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement FieldExtent**

Create `interpreter/cobol/field_extent.py`:

```python
# pyright: standard
"""FieldExtent — a COBOL field as a byte range, and how ranges alias.

A COBOL field is not a variable: it is a slice of a section's region buffer.
Two fields alias exactly when their byte ranges intersect within the same
region, which subsumes group/elementary containment, REDEFINES, RENAMES,
OCCURS elements and reference modification without a rule for each.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from interpreter.cobol.region_id import RegionId


class Precision(Enum):
    """How exactly the extent locates the access."""

    EXACT = auto()
    """The access covers precisely this range (literal or absent subscript)."""

    CLAMPED = auto()
    """The access lands somewhere inside this range (computed subscript).

    A CLAMPED extent can never must_cover anything: we know where it might
    be, not where it is.
    """


@dataclass(frozen=True)
class FieldExtent:
    region: RegionId
    start: int
    length: int
    precision: Precision
    field_name: str

    @property
    def end(self) -> int:
        """Exclusive end offset."""
        return self.start + self.length

    def may_alias(self, other: object) -> bool:
        if not isinstance(other, FieldExtent) or other.region is not self.region:
            return False
        if self.length <= 0 or other.length <= 0:
            return False
        return self.start < other.end and other.start < self.end

    def must_cover(self, other: object) -> bool:
        if not isinstance(other, FieldExtent) or other.region is not self.region:
            return False
        if self.precision is not Precision.EXACT:
            return False
        if self.length <= 0 or other.length <= 0:
            return False
        return self.start <= other.start and other.end <= self.end

    def alias_key(self) -> tuple[str, str]:
        return ("extent", self.region.value)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/cobol/test_field_extent.py -v -p no:xdist`
Expected: PASS (9 tests)

- [ ] **Step 5: Add the protocol conformance test**

```python
def test_field_extent_satisfies_abstract_location():
    from interpreter.abstract_location import AbstractLocation

    assert isinstance(ext(0, 10), AbstractLocation)
```

Run it; expected PASS.

- [ ] **Step 6: Commit**

```bash
uv run python -m black .
/usr/bin/git add interpreter/cobol/field_extent.py tests/unit/cobol/test_field_extent.py
/usr/bin/git commit -m "feat(cobol): FieldExtent with byte-range alias algebra"
```

---

### Task 6: Attach extents to resolved field references

**Files:**
- Modify: `interpreter/cobol/field_resolution.py:12-24` (`ResolvedFieldRef`)
- Modify: `interpreter/cobol/emit_context.py:229-...` (`resolve_field_ref`), `:400-409` (`resolve_field_ref_from`)
- Test: `tests/unit/cobol/test_resolved_extent.py` (create)

**Interfaces:**
- Consumes: `FieldExtent`, `Precision` (Task 5), `RegionId` and `resolve_with_region` (Task 4).
- Produces: `ResolvedFieldRef.extent: FieldExtent`.

This is where the ⊤ cliff is avoided: `resolve_field_ref` already receives `subscripts: tuple[ExprNode, ...]` as structured nodes, so it can see whether a subscript is a literal without reasoning about `BINOP` arithmetic.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/cobol/test_resolved_extent.py`. Reuse the probe-program fixture pattern from Task 4, with this source (note: neighbours on both sides of every field under test, per the Global Constraints):

```cobol
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-LEAD     PIC X(7).
       01  WS-REC.
           05  WS-NAME PIC X(20).
           05  WS-TAB.
               10  WS-ENT OCCURS 10 TIMES.
                   15  WS-CODE PIC X(2).
                   15  WS-QTY  PIC 999.
       01  WS-TRAIL    PIC X(3).
       PROCEDURE DIVISION.
           MOVE 'HI' TO WS-NAME.
           STOP RUN.
```

```python
def test_bare_field_gets_an_exact_extent(probe):
    ref, _reg = probe.resolve_field_ref("WS-NAME")
    assert ref.extent.precision is Precision.EXACT
    assert ref.extent.region is RegionId.WORKING_STORAGE
    assert ref.extent.length == 20


def test_neighbours_do_not_overlap(probe):
    """WS-LEAD and WS-TRAIL bracket WS-REC; a width bug shows up as overlap."""
    lead, _ = probe.resolve_field_ref("WS-LEAD")
    name, _ = probe.resolve_field_ref("WS-NAME")
    trail, _ = probe.resolve_field_ref("WS-TRAIL")
    assert not lead.extent.may_alias(name.extent)
    assert not name.extent.may_alias(trail.extent)
    assert lead.extent.end == name.extent.start


def test_literal_subscript_gives_an_exact_element_extent(probe):
    ref, _reg = probe.resolve_field_ref("WS-QTY", subscripts=(literal_expr(2),))
    assert ref.extent.precision is Precision.EXACT
    assert ref.extent.length == 3


def test_computed_subscript_clamps_to_the_table(probe):
    """An unbounded offset must clamp to the OCCURS extent, never the region."""
    ref, _reg = probe.resolve_field_ref("WS-QTY", subscripts=(field_expr("WS-IDX"),))
    assert ref.extent.precision is Precision.CLAMPED
    assert ref.extent.length == 50, "clamped to WS-TAB (10 entries x 5 bytes)"


def test_clamped_extent_never_spans_the_whole_region(probe):
    """The cliff: a clamped extent must stay inside its own table."""
    tab, _ = probe.resolve_field_ref("WS-TAB")
    ref, _reg = probe.resolve_field_ref("WS-QTY", subscripts=(field_expr("WS-IDX"),))
    assert tab.extent.must_cover(ref.extent)
```

Build `literal_expr` / `field_expr` helpers from the real `ExprNode` constructors — read `cobol_asg/cobol_expression.py` for the actual node types and construct them directly. Add `WS-IDX PIC 9(4)` to the probe source as a sibling `01` so `field_expr("WS-IDX")` resolves.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_resolved_extent.py -v -p no:xdist`
Expected: FAIL with `AttributeError: 'ResolvedFieldRef' object has no attribute 'extent'`

- [ ] **Step 3: Add the field**

In `interpreter/cobol/field_resolution.py`, add to `ResolvedFieldRef`:

```python
    extent: FieldExtent
```

Document it: "Statically-known byte range this reference touches. EXACT when the subscript is absent or literal; CLAMPED to the enclosing OCCURS extent when computed. Never widens beyond a declared construct."

- [ ] **Step 4: Populate it in resolve_field_ref**

In `emit_context.py`'s `resolve_field_ref`, switch the lookup to `materialised.resolve_with_region(...)` and build the extent:

- No subscripts → `FieldExtent(region, fl.offset, fl.byte_length, Precision.EXACT, name)`.
- All subscripts literal → compute the element offset with the same stride arithmetic the register path already uses (`subscript_stride()` / the per-dimension accumulation), then `Precision.EXACT` with `fl.byte_length`.
- Any subscript non-literal → clamp: walk to the enclosing OCCURS construct and use its offset and full extent (`element_size * occurs_count`), `Precision.CLAMPED`.

Do not change how `offset_reg` is computed — the extent is additional, parallel information. Keep the register arithmetic exactly as-is so runtime behaviour is untouched.

- [ ] **Step 5: Populate it in resolve_field_ref_from**

`resolve_field_ref_from(fl, region_reg)` has no name lookup and so no region. Add a `region: RegionId` parameter and update its call sites (find them with `grep -rn "resolve_field_ref_from" interpreter/`). It always produces `Precision.EXACT` over `fl.offset`/`fl.byte_length`.

- [ ] **Step 6: Run tests**

Run: `uv run python -m pytest tests/unit/cobol/test_resolved_extent.py -v -p no:xdist`
Expected: PASS (5 tests)

- [ ] **Step 7: Run the full suite and commit**

```bash
uv run python -m pytest > /tmp/t6.txt 2>&1; echo "EXIT=$?"
uv run python -m black .
/usr/bin/git add interpreter/cobol/field_resolution.py interpreter/cobol/emit_context.py tests/unit/cobol/test_resolved_extent.py
/usr/bin/git commit -m "feat(cobol): carry a static byte extent on every resolved field ref"
```

---

### Task 7: The memory effect recorder and its funnel

**Files:**
- Create: `interpreter/cobol/memory_effects.py`
- Modify: `interpreter/cobol/emit_context.py` — 7 region sites at lines 426, 525, 641, 723, 751, 793, 1015
- Modify: `interpreter/cobol/lower_call.py` — 4 region sites at lines 75, 84, 125, 134
- Test: `tests/unit/cobol/test_memory_effects.py` (create)
- Test: `tests/unit/cobol/test_region_funnel_invariant.py` (create)

**Interfaces:**
- Consumes: `FieldExtent` (Task 5), `InstructionId` (Task 1).
- Produces: `EffectKind` (`READ`/`WRITE`), `MemoryEffect`, `MemoryEffectRecorder` protocol, `NullRecorder`, `CollectingRecorder`, and `EmitContext._emit_load_region` / `_emit_write_region`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/cobol/test_memory_effects.py`:

```python
"""Memory effects — what the lowering tells the analysis about each access."""

from interpreter.cobol.memory_effects import (
    CollectingRecorder,
    EffectKind,
    MemoryEffect,
    NullRecorder,
)


def test_null_recorder_discards_and_costs_nothing():
    NullRecorder().record(1, object())  # must not raise


def test_collecting_recorder_keys_effects_by_instruction_id(sample_extent):
    rec = CollectingRecorder()
    effect = MemoryEffect(kind=EffectKind.WRITE, extent=sample_extent)
    rec.record(7, effect)
    assert rec.effects[7] is effect
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_memory_effects.py -v -p no:xdist`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create the module**

Create `interpreter/cobol/memory_effects.py`:

```python
# pyright: standard
"""Memory effects — the COBOL lowering's declaration of what each access touches.

emit_context is the only place holding BOTH the source construct (FieldLayout,
structured subscripts, source location) AND the byte layout (offset, length,
region). Neither the ASG nor the IR has both, so the extent is recorded here
rather than reconstructed later from arithmetic on offset registers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol

from interpreter.cobol.field_extent import FieldExtent
from interpreter.instructions import InstructionId
from interpreter.source_location import SourceLocation


class EffectKind(Enum):
    READ = auto()
    WRITE = auto()


@dataclass(frozen=True)
class MemoryEffect:
    kind: EffectKind
    extent: FieldExtent
    source_location: SourceLocation | None = None


class MemoryEffectRecorder(Protocol):
    def record(self, inst_id: InstructionId, effect: MemoryEffect) -> None: ...


class NullRecorder:
    """Default. Analysis off; recording costs nothing."""

    def record(self, inst_id: InstructionId, effect: MemoryEffect) -> None:
        return None


@dataclass
class CollectingRecorder:
    """Builds the sidecar consumed by the memory dataflow analysis."""

    effects: dict[InstructionId, MemoryEffect] = field(default_factory=dict)

    def record(self, inst_id: InstructionId, effect: MemoryEffect) -> None:
        self.effects[inst_id] = effect
```

Import `SourceLocation` from wherever `instructions.py` imports it; read the top of `interpreter/instructions.py` to confirm the module path.

- [ ] **Step 4: Run test to verify it passes**

Add a `sample_extent` fixture returning any `FieldExtent`. Run: `uv run python -m pytest tests/unit/cobol/test_memory_effects.py -v -p no:xdist`
Expected: PASS

- [ ] **Step 5: Add the funnel helpers**

In `EmitContext.__init__`, add `recorder: MemoryEffectRecorder = NullRecorder()` as a keyword parameter stored on `self._recorder`. Add:

```python
    def _emit_load_region(
        self, result_reg: Register, region_reg: Register,
        offset_reg: Register, extent: FieldExtent,
    ) -> None:
        """Emit a region read AND declare its memory effect. The only way to
        construct a LoadRegion — see test_region_funnel_invariant."""
        inst = self.emit_inst(
            LoadRegion(
                result_reg=result_reg, region_reg=region_reg,
                offset_reg=offset_reg, length=extent.length,
            ),
        )
        self._recorder.record(
            inst.id,
            MemoryEffect(kind=EffectKind.READ, extent=extent,
                         source_location=inst.source_location),
        )

    def _emit_write_region(
        self, region_reg: Register, offset_reg: Register,
        value_reg: Register, extent: FieldExtent,
    ) -> None:
        """Emit a region write AND declare its memory effect."""
        inst = self.emit_inst(
            WriteRegion(
                region_reg=region_reg, offset_reg=offset_reg,
                length=extent.length, value_reg=value_reg,
            ),
        )
        self._recorder.record(
            inst.id,
            MemoryEffect(kind=EffectKind.WRITE, extent=extent,
                         source_location=inst.source_location),
        )
```

- [ ] **Step 6: Route all 11 sites through the funnel**

Rewrite each of the 7 sites in `emit_context.py` (lines 426, 525, 641, 723, 751, 793, 1015) and the 4 in `lower_call.py` (lines 75, 84, 125, 134) to call the helpers. Each site already has an `fl` or an explicit length in scope; derive the extent from the `ResolvedFieldRef` where one is available.

Worked example — `emit_read_region_raw` (currently `emit_context.py:735-767`) becomes:

```python
    def emit_read_region_raw(
        self, region_reg: Register, fl: FieldLayout,
        offset_reg: Register = NO_REGISTER,
        region: RegionId = RegionId.WORKING_STORAGE,
    ) -> Register:
        """Read a region slot as its verbatim byte-image (LATIN1 identity)."""
        if not offset_reg.is_present():
            offset_reg = self.fresh_reg()
            self.emit_inst(Const.int_(offset_reg, fl.offset))
        data_reg = self.fresh_reg()
        self._emit_load_region(
            result_reg=data_reg,
            region_reg=region_reg,
            offset_reg=offset_reg,
            extent=FieldExtent(
                region=region, start=fl.offset, length=fl.byte_length,
                precision=Precision.EXACT, field_name=fl.name,
            ),
        )
        encoding_reg = self.const_to_reg(CobolEncoding.LATIN1.value)
        ...  # rest of the method unchanged
```

The remaining ten follow the same shape: build the `FieldExtent` from the `fl`
(or from `ref.extent` where a `ResolvedFieldRef` is in scope) and swap the
direct `LoadRegion(...)`/`WriteRegion(...)` construction for the helper call.
Where a caller already threads a `ResolvedFieldRef`, prefer `ref.extent` over
rebuilding it, so a subscripted access keeps its `CLAMPED` precision instead of
being flattened to `EXACT`. **Rebuilding an EXACT extent for a subscripted
access is the one mistake here that silently breaks correctness** — it would let
a computed-subscript write kill definitions it cannot actually overwrite.

The `lower_call.py` sites are the `CALL USING` params/results marshalling. In this scope they record effects but get **no** cross-region binding — a caller/callee alias edge is explicitly out of scope. Use the region the marshalling buffer actually belongs to.

- [ ] **Step 7: Write the completeness invariant test**

Create `tests/unit/cobol/test_region_funnel_invariant.py`:

```python
"""No region access may be emitted without declaring its memory effect.

The silent failure mode this guards: a lowering path that emits a write
without an effect simply vanishes from the analysis, producing a quietly
incomplete dependency graph rather than a visible error. That is exactly the
shape of the WriteRegion.writes() -> None bug this work exists to fix.
"""

import subprocess
from pathlib import Path

ALLOWED = {"interpreter/cobol/emit_context.py"}


def test_region_instructions_are_constructed_only_in_the_funnel():
    out = subprocess.run(
        ["grep", "-rnE", r"\b(LoadRegion|WriteRegion)\(", "interpreter"],
        capture_output=True, text=True,
    ).stdout
    offenders = sorted(
        {
            line.split(":")[0]
            for line in out.splitlines()
            if line and not line.startswith("interpreter/instructions.py")
        }
        - ALLOWED
    )
    assert offenders == [], (
        f"LoadRegion/WriteRegion constructed outside the funnel: {offenders}. "
        "Use EmitContext._emit_load_region / _emit_write_region so the memory "
        "effect is declared alongside the instruction."
    )


def test_the_funnel_itself_still_constructs_them():
    """Guards against the invariant passing vacuously."""
    src = Path("interpreter/cobol/emit_context.py").read_text()
    assert "LoadRegion(" in src and "WriteRegion(" in src
```

- [ ] **Step 8: Run tests**

Run: `uv run python -m pytest tests/unit/cobol/test_memory_effects.py tests/unit/cobol/test_region_funnel_invariant.py -v -p no:xdist`
Expected: PASS

- [ ] **Step 9: Run the full suite and commit**

```bash
uv run python -m pytest > /tmp/t7.txt 2>&1; echo "EXIT=$?"
uv run python -m black .
/usr/bin/git add interpreter/cobol/memory_effects.py interpreter/cobol/emit_context.py interpreter/cobol/lower_call.py tests/unit/cobol/
/usr/bin/git commit -m "feat(cobol): declare memory effects at every region access"
```

---

### Task 8: The memory dataflow analysis

**Files:**
- Create: `interpreter/cobol/memory_dataflow.py`
- Test: `tests/unit/cobol/test_memory_dataflow.py` (create)

**Interfaces:**
- Consumes: `CollectingRecorder.effects` (Task 7), `FieldExtent` (Task 5), `analyze`/`Definition`/`Use` (Task 3).
- Produces:

```python
@dataclass
class MemoryDataflowResult:
    extent_graph: dict[FieldExtent, set[FieldExtent]]
    field_graph: dict[str, set[str]]
    edge_locations: dict[tuple[str, str], list[SourceLocation]]

def analyze_memory_dataflow(
    cfg: CFG, effects: dict[InstructionId, MemoryEffect]
) -> MemoryDataflowResult: ...
```

The analysis substitutes each region instruction's location with its recorded `FieldExtent` before running the existing fixpoint, so `may_alias`/`must_cover` do the aliasing work.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/cobol/test_memory_dataflow.py`:

```python
"""Field-level dependency graph over COBOL memory."""

def test_value_flows_between_fields(analyze_probe):
    """MOVE WS-SRC TO WS-DST makes WS-DST depend on WS-SRC."""
    result = analyze_probe("""
           MOVE WS-SRC TO WS-DST.
    """)
    assert "WS-SRC" in result.field_graph["WS-DST"]


def test_group_write_reaches_every_child(analyze_probe):
    """MOVE to a group must define all children by range subsumption."""
    result = analyze_probe("""
           MOVE WS-SRC TO WS-REC.
           MOVE WS-NAME TO WS-DST.
    """)
    assert "WS-SRC" in result.field_graph["WS-DST"]


def test_disjoint_records_do_not_create_edges(analyze_probe):
    """WS-OTHER neither overlaps nor feeds WS-DST, so no edge."""
    result = analyze_probe("""
           MOVE WS-SRC TO WS-DST.
    """)
    assert "WS-OTHER" not in result.field_graph.get("WS-DST", set())


def test_edges_carry_the_source_locations_that_produced_them(analyze_probe):
    result = analyze_probe("""
           MOVE WS-SRC TO WS-DST.
    """)
    assert result.edge_locations[("WS-SRC", "WS-DST")]
```

Build the `analyze_probe` fixture: splice the statements into a fixed program skeleton with `WS-SRC`, `WS-DST`, `WS-OTHER`, and a `WS-REC` group containing `WS-NAME`; lower it with a `CollectingRecorder`; build the CFG; call `analyze_memory_dataflow`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_memory_dataflow.py -v -p no:xdist`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the analysis**

Create `interpreter/cobol/memory_dataflow.py`. Structure:

1. Walk the CFG; for each instruction with an entry in `effects`, substitute its dataflow location with the recorded `FieldExtent` (WRITE effects become definitions, READ effects become uses). Non-region instructions keep their `Register`/`VarName` locations unchanged — both kinds coexist, which is required because `%4 = LOAD_REGION ...` defines a *register* from an *extent*.
2. Run reaching definitions using the Task 3 machinery.
3. Trace register chains back to extents. Extend the existing `_trace_to_named_vars` logic so a chain terminates at a `FieldExtent` as well as a `VarName`.
4. Project extents onto declared field names: each extent maps to the field names of every extent it overlaps.
5. Transitively close, reusing `_transitive_closure` from `interpreter/dataflow.py`.

`local_defs` in `extract_def_use_chains` shadows by exact identity, which is correct for registers but wrong for extents — an extent write should shadow prior local writes it `must_cover`. Handle this in the memory analysis rather than changing shared code.

- [ ] **Step 4: Run tests**

Run: `uv run python -m pytest tests/unit/cobol/test_memory_dataflow.py -v -p no:xdist`
Expected: PASS (4 tests)

- [ ] **Step 5: Add the imprecision characterization tests**

These assert the *known, accepted* over-approximations. They document behaviour rather than aspiration — do not "fix" them.

```python
def test_computed_subscript_write_does_not_kill(analyze_probe):
    """A clamped write may-overlaps but cannot must-cover, so the earlier
    definition survives alongside it. Over-approximating by design."""
    result = analyze_probe("""
           MOVE WS-SRC TO WS-QTY(1).
           MOVE WS-OTHER TO WS-QTY(WS-IDX).
           MOVE WS-QTY(1) TO WS-DST.
    """)
    deps = result.field_graph["WS-DST"]
    assert "WS-SRC" in deps, "surviving exact definition"
    assert "WS-OTHER" in deps, "clamped write cannot kill, so it also reaches"


def test_perform_merges_paragraph_contexts(analyze_probe):
    """KNOWN IMPRECISION (spec 7.4): context-insensitive PERFORM merges call
    sites, so a value written before one PERFORM reaches a read after
    another. Upgrade path is paragraph summaries. Asserted so the imprecision
    is visible and its scope tracked, not silently tolerated."""
    result = analyze_probe_with_paragraphs()
    assert "WS-FEE" in result.field_graph["WS-FIRST-OUT"]
```

Write `analyze_probe_with_paragraphs` to build the two-`PERFORM` shape from the spec (`1000-CALC` writes `WS-WORK`, `2000-FEES` writes `WS-WORK` from `WS-FEE`, `9000-FORMAT` reads `WS-WORK` into an output field, performed after each).

- [ ] **Step 6: Run the full suite and commit**

```bash
uv run python -m pytest > /tmp/t8.txt 2>&1; echo "EXIT=$?"
uv run python -m black .
/usr/bin/git add interpreter/cobol/memory_dataflow.py tests/unit/cobol/test_memory_dataflow.py
/usr/bin/git commit -m "feat(cobol): field-level memory dataflow analysis"
```

---

### Task 9: JSON serialization

**Files:**
- Modify: `interpreter/cobol/memory_dataflow.py`
- Test: `tests/unit/cobol/test_memory_dataflow_json.py` (create)

**Interfaces:**
- Consumes: `MemoryDataflowResult` (Task 8).
- Produces: `MemoryDataflowResult.to_json() -> dict`.

Edge direction follows **data flow**: `{"from": "WS-SRC", "to": "WS-DST"}` means a value flowed from `WS-SRC` into `WS-DST`. This is the reverse of `field_graph`, which maps *field → fields it depends on*.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/cobol/test_memory_dataflow_json.py`:

```python
"""JSON projection of the field graph, for graph visualisation."""

import json


def test_edges_point_along_data_flow(analyze_probe):
    result = analyze_probe("""
           MOVE WS-SRC TO WS-DST.
    """)
    doc = result.to_json()
    assert {"from": "WS-SRC", "to": "WS-DST"} in [
        {"from": e["from"], "to": e["to"]} for e in doc["edges"]
    ]


def test_nodes_list_every_field_mentioned(analyze_probe):
    result = analyze_probe("""
           MOVE WS-SRC TO WS-DST.
    """)
    doc = result.to_json()
    assert {"WS-SRC", "WS-DST"} <= set(doc["nodes"])


def test_output_is_json_serialisable(analyze_probe):
    result = analyze_probe("""
           MOVE WS-SRC TO WS-DST.
    """)
    json.dumps(result.to_json())  # must not raise


def test_edges_carry_via_source_locations(analyze_probe):
    result = analyze_probe("""
           MOVE WS-SRC TO WS-DST.
    """)
    edge = next(e for e in result.to_json()["edges"] if e["to"] == "WS-DST")
    assert edge["via"], "an edge must say which statements produced it"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_memory_dataflow_json.py -v -p no:xdist`
Expected: FAIL with `AttributeError: 'MemoryDataflowResult' object has no attribute 'to_json'`

- [ ] **Step 3: Implement to_json**

```python
    def to_json(self) -> dict:
        """Edge-oriented projection for graph visualisation.

        Direction follows data flow: from -> to means a value flowed from
        the source field into the target. This is the reverse of
        field_graph, which maps a field to the fields it depends on.
        """
        nodes = sorted(
            set(self.field_graph)
            | {dep for deps in self.field_graph.values() for dep in deps}
        )
        edges = [
            {
                "from": dep,
                "to": target,
                "via": [str(loc) for loc in self.edge_locations.get((dep, target), [])],
            }
            for target in sorted(self.field_graph)
            for dep in sorted(self.field_graph[target])
        ]
        return {"nodes": nodes, "edges": edges}
```

- [ ] **Step 4: Run tests**

Run: `uv run python -m pytest tests/unit/cobol/test_memory_dataflow_json.py -v -p no:xdist`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
uv run python -m black .
/usr/bin/git add interpreter/cobol/memory_dataflow.py tests/unit/cobol/test_memory_dataflow_json.py
/usr/bin/git commit -m "feat(cobol): JSON projection of the field dependency graph"
```

---

### Task 10: Integration test on real COBOL

**Files:**
- Test: `tests/integration/test_cobol_memory_dataflow.py` (create)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing consumed by later tasks.

This deliberately departs from the project's usual "integration exercises the VM via `run()`" rule: the analysis is a static pass that never executes. Integration here means the real pipeline — parse → lower → CFG → analyze — on real COBOL source rather than hand-built IR.

- [ ] **Step 1: Write the integration tests**

Create `tests/integration/test_cobol_memory_dataflow.py` covering, each on a complete parsed program:

```python
def test_redefines_creates_an_alias_edge():
    """WS-RAW REDEFINES WS-NUM: writing one is observable through the other."""


def test_group_move_propagates_to_every_child():
    """MOVE to a group defines all children; a later read of any child
    depends on the group's source."""


def test_occurs_element_write_reaches_a_read_of_the_table():
    """Element writes and table reads overlap and therefore link."""


def test_unrelated_records_stay_disconnected():
    """The anti-mush check: two 01 records with no data path between them
    must not be connected, or the report is worthless."""


def test_analysis_is_off_by_default():
    """Lowering without a CollectingRecorder records no effects and costs
    nothing — the NullRecorder path."""
```

Each writes its own COBOL source with neighbours bracketing the fields under test.

- [ ] **Step 2: Run and iterate to green**

Run: `uv run python -m pytest tests/integration/test_cobol_memory_dataflow.py -v -p no:xdist`

If `test_unrelated_records_stay_disconnected` fails, that is the **mush signal** — the graph is over-connected. Do not weaken the test. Diagnose which edge is spurious and report it; it likely indicates either a `must_cover` that is too strict (nothing ever kills) or the `PERFORM` merge from spec risk 7.4.

- [ ] **Step 3: Run the full suite and commit**

```bash
uv run python -m pytest > /tmp/t10.txt 2>&1; echo "EXIT=$?"
uv run python -m black .
/usr/bin/git add tests/integration/test_cobol_memory_dataflow.py
/usr/bin/git commit -m "test(cobol): end-to-end memory dataflow on real COBOL source"
```

---

### Task 11: Evaluation on a real program

**Files:**
- Create: `scripts/memory_dataflow_density.py`
- Create: `docs/superpowers/specs/2026-09-04-cobol-memory-dataflow-evaluation.md`

**Interfaces:**
- Consumes: `analyze_memory_dataflow`, `to_json`.
- Produces: a recorded density baseline. **Not a pass/fail gate.**

This settles spec risk 7.4 — whether context-insensitive `PERFORM` is empirically usable — with evidence rather than a guess.

- [ ] **Step 1: Write the density script**

Create `scripts/memory_dataflow_density.py` taking a COBOL file path and printing: field count; edge count; mean out-degree; fraction of ordered field pairs connected after transitive closure; and the ten fields with the highest in-degree.

- [ ] **Step 2: Run it on a real CardDemo program**

Find one under `tests/` (the CardDemo sources used by the `carddemo_e2e` marker). Run the script on at least two programs of different sizes.

- [ ] **Step 3: Record the findings**

Write `docs/superpowers/specs/2026-09-04-cobol-memory-dataflow-evaluation.md` with the numbers, and a verdict on this question: **is the transitively-connected fraction low enough that an impact query returns a useful subset rather than most of the program?**

If it is high, the recommendation is paragraph summaries (spec §8), which `interpreter/interprocedural/summaries.py` already shapes and which scope (2) needs anyway. State the finding plainly either way — a negative result here is a real result and changes the roadmap.

- [ ] **Step 4: Commit**

```bash
/usr/bin/git add scripts/memory_dataflow_density.py docs/superpowers/specs/2026-09-04-cobol-memory-dataflow-evaluation.md
/usr/bin/git commit -m "docs(cobol): density evaluation of the memory dataflow graph"
```

---

## Deferred (not in this plan)

Per the spec, explicitly out of scope: `CALL USING` region-to-region binding; dataset-mediated cross-program flow; control dependence; element-level subscript precision via strided intervals; retrofitting `Definition`/`Use` onto instruction ids; TUI `DataflowGraphPanel` wiring; MCP query tool.

## Known unknown

Spec risk 7.3: reference modification with **both** a computed start and a computed length (`WS-FIELD(I:J)`) is unverified. Everything else clamps to a declared extent. Probe this before Task 6 — read how `interpreter/cobol/ref_mod.py` (or `cobol_asg/ref_mod.py`) lowers it, and confirm the extent can be clamped to the field's own extent. If it cannot, that is the one remaining route back to the ⊤ cliff and Task 6 needs a design amendment before proceeding.
