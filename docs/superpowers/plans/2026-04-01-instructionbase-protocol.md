# InstructionBase Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote `result_reg`, `label`, `branch_targets` to `InstructionBase` and add `opcode`/`operands` property stubs so pyright can type-check all attribute accesses on the base class.

**Architecture:** Pure structural refactor — no runtime behaviour changes. Move the three shared dataclass fields from 33 subclasses up to the base. Add two `@property` stubs for `opcode`/`operands`. Remove `inst: Any` cast in `__str__`. Fix `cfg.py` which accesses `.opcode`/`.label` on `InstructionBase`-typed variables. The full test suite (13,235 tests) plus `pyright` serve as the verification gate.

**Tech Stack:** Python 3.13+, pyright ^1.1.408, pytest, poetry

---

## File Map

| Action | Path | Change |
|--------|------|--------|
| Modify | `interpreter/instructions.py` | Add 3 fields + 2 property stubs to `InstructionBase`; remove 33 compat blocks; remove `inst: Any` cast |
| Modify | `interpreter/cfg.py` | No code change needed — errors resolve automatically once `InstructionBase` declares `opcode` and `label` |

---

## Baseline

Before starting, record the current pyright error count:

```bash
poetry run pyright interpreter/ mcp_server/ 2>&1 | tail -3
```

Expected output contains: `852 errors` (approximately). Note the exact number — Task 2 must show a reduction.

---

## Task 1: File a Beads issue and claim it

- [ ] **Step 1: Verify the existing issue exists and claim it**

```bash
bd show red-dragon-4ei7
bd update red-dragon-4ei7 --claim
```

Expected: issue status moves to `in_progress`.

---

## Task 2: Promote shared fields to `InstructionBase` and add property stubs

**Files:**
- Modify: `interpreter/instructions.py:98-191` (InstructionBase class)

This task has no new behaviour — the regression gate (full test suite) is the red/green check. The "failing test" is `pyright` reporting `Cannot access attribute "result_reg" for class "InstructionBase*"` at line 158.

- [ ] **Step 1: Confirm the current pyright failure**

```bash
poetry run pyright interpreter/instructions.py 2>&1 | grep "error:" | head -10
```

Expected: errors including `Cannot access attribute "result_reg" for class "InstructionBase*"` at line 158, and `Cannot access attribute "opcode"/"label" for class "InstructionBase"` in `cfg.py`.

- [ ] **Step 2: Add fields and property stubs to `InstructionBase`**

In `interpreter/instructions.py`, update `InstructionBase` from:

```python
@dataclass(frozen=True)
class InstructionBase:
    """Shared metadata carried by every instruction."""

    source_location: SourceLocation = field(default_factory=lambda: NO_SOURCE_LOCATION)

    def map_registers(self, ...
```

to:

```python
@dataclass(frozen=True)
class InstructionBase:
    """Shared metadata carried by every instruction."""

    source_location: SourceLocation = field(default_factory=lambda: NO_SOURCE_LOCATION)
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        raise NotImplementedError

    @property
    def operands(self) -> list[Any]:
        raise NotImplementedError

    def map_registers(self, ...
```

- [ ] **Step 3: Remove the `inst: Any` cast from `__str__`**

In `InstructionBase.__str__` (around line 164–191), replace:

```python
def __str__(self) -> str:
    """Render in the same format as IRInstruction.__str__."""
    inst: Any = self  # subclass attrs not visible on InstructionBase
    parts: list[str] = []
    if (
        hasattr(inst, "label")
        and inst.label.is_present()
        and inst.opcode == Opcode.LABEL
    ):
        base = f"{inst.label}:"
    else:
        if inst.result_reg.is_present():
            parts.append(f"{inst.result_reg} =")
        parts.append(inst.opcode.value.lower())
        for op in inst.operands:
            parts.append(str(op))
        if hasattr(inst, "branch_targets") and inst.branch_targets:
            parts.append(",".join(str(t) for t in inst.branch_targets))
        elif (
            hasattr(inst, "label")
            and inst.label.is_present()
            and inst.opcode != Opcode.LABEL
        ):
            parts.append(str(inst.label))
        base = " ".join(parts)
    if not self.source_location.is_unknown():
        return f"{base}  # {self.source_location}"
    return base
```

with:

```python
def __str__(self) -> str:
    """Render in the same format as IRInstruction.__str__."""
    parts: list[str] = []
    if self.label.is_present() and self.opcode == Opcode.LABEL:
        base = f"{self.label}:"
    else:
        if self.result_reg.is_present():
            parts.append(f"{self.result_reg} =")
        parts.append(self.opcode.value.lower())
        for op in self.operands:
            parts.append(str(op))
        if self.branch_targets:
            parts.append(",".join(str(t) for t in self.branch_targets))
        elif self.label.is_present() and self.opcode != Opcode.LABEL:
            parts.append(str(self.label))
        base = " ".join(parts)
    if not self.source_location.is_unknown():
        return f"{base}  # {self.source_location}"
    return base
```

- [ ] **Step 4: Remove all `# IRInstruction-compat fields` blocks from subclasses**

Every subclass has this block (33 total):

```python
# ── IRInstruction-compat fields ──
result_reg: Register = NO_REGISTER
label: CodeLabel = NO_LABEL
branch_targets: tuple[CodeLabel, ...] = ()
```

Delete this block from every subclass. The fields are now inherited from `InstructionBase`. Do not remove subclass-specific fields that happen to have the same name but different defaults (there are none — all compat blocks are identical).

The fastest approach: remove the comment marker and the three field lines everywhere they appear together. There are 33 occurrences.

- [ ] **Step 5: Run pyright to confirm errors drop**

```bash
poetry run pyright interpreter/instructions.py interpreter/cfg.py 2>&1 | grep "error:"
```

Expected: the `result_reg`/`opcode`/`label` attribute errors are gone. Other pre-existing errors (e.g., `list[Register]` not assignable to `list[StorageIdentifier]` at lines 419/448, `_TO_TYPED` at line 1493) are separate issues and should remain untouched.

- [ ] **Step 6: Run the full test suite**

```bash
poetry run python -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all 13,235 tests pass, 1 skipped, 17 xfailed.

If any test fails, do not proceed. The field promotion changes constructor argument order for positional callers — if something breaks, search for positional construction: `grep -rn "InstructionBase(" interpreter/ tests/`.

- [ ] **Step 7: Run black and check overall pyright count**

```bash
poetry run python -m black .
poetry run pyright interpreter/ mcp_server/ 2>&1 | tail -3
```

Expected: error count is less than the baseline (was ~852). Note the new count.

- [ ] **Step 8: Close the Beads issue and backup**

```bash
bd close red-dragon-4ei7 --reason "result_reg, label, branch_targets promoted to InstructionBase as concrete fields. opcode and operands declared as @property stubs. inst: Any cast removed from __str__. cfg.py attr errors resolved automatically."
bd backup
```

- [ ] **Step 9: Commit**

```bash
git add interpreter/instructions.py
git commit -m "types: promote InstructionBase protocol fields — result_reg/label/branch_targets on base, opcode/operands stubs — resolves red-dragon-4ei7"
```

---

## Verification

After the commit, run the full gate manually to confirm clean state:

```bash
poetry run pyright interpreter/ mcp_server/ 2>&1 | tail -3   # count must be lower than baseline
poetry run python -m pytest tests/ -q 2>&1 | tail -3          # 13,235 passed
```

---

## Out of Scope

These errors appear in `interpreter/instructions.py` but are **separate issues** — do not fix them in this task:

- Line 419, 448: `list[Register]` not assignable to `list[StorageIdentifier]` in `reads()` — tracked as red-dragon-8jzr
- Line 1493: `object` not callable in `_TO_TYPED` — tracked as red-dragon-ivkr
- Any str/Register mismatches in frontends or COBOL — tracked under red-dragon-r32l children

## Testing Guidelines

This is a structural refactor with no behaviour change. There are no new behaviours to test. The regression gate — 13,235 existing tests passing — is the only test requirement. If a test fails after the field promotion, it indicates a construction site passing positional arguments where keyword arguments are required; fix those callers, do not modify the test assertion.
