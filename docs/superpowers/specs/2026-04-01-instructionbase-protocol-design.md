# InstructionBase Protocol — Design Spec

**Date:** 2026-04-01
**Issue:** red-dragon-4ei7 (parent: red-dragon-r32l)
**Status:** Approved

---

## Problem

`InstructionBase` is a frozen dataclass with only `source_location` declared. Every one of its 34 concrete subclasses carries an identical `# IRInstruction-compat fields` block:

```python
result_reg: Register = NO_REGISTER
label: CodeLabel = NO_LABEL
branch_targets: tuple[CodeLabel, ...] = ()
```

`opcode` and `operands` are declared as `@property` per subclass.

This creates two problems:

1. `InstructionBase.writes()` accesses `self.result_reg` — not declared on the base. Pyright reports `reportAttributeAccessIssue`.
2. `InstructionBase.__str__()` works around missing declarations with `inst: Any = self`, suppressing all type checking for that method. External sites (e.g., `cfg.py`) that hold an `InstructionBase`-typed variable and access `.result_reg`, `.opcode`, `.operands` also fail pyright.

---

## Solution

### 1. Promote the three shared fields to `InstructionBase`

Move `result_reg`, `label`, and `branch_targets` from every subclass up to `InstructionBase`:

```python
@dataclass(frozen=True)
class InstructionBase:
    source_location: SourceLocation = field(default_factory=lambda: NO_SOURCE_LOCATION)
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()
```

Remove the `# IRInstruction-compat fields` block from all 33 subclasses. Subclasses inherit the fields. No re-declaration needed.

**Field ordering:** Subclass-specific fields (e.g., `value_reg`, `name`, `args`) follow the base fields in the constructor. All existing construction sites use keyword arguments — no positional-arg breakage.

### 2. Declare `opcode` and `operands` as property stubs on `InstructionBase`

```python
@property
def opcode(self) -> Opcode:
    raise NotImplementedError

@property
def operands(self) -> list[Any]:
    raise NotImplementedError
```

Subclass `@property` implementations shadow these. No ABC required — `NotImplementedError` is sufficient for pyright to see the attribute as declared.

### 3. Remove the `inst: Any` cast from `__str__`

Replace `inst: Any = self` with direct `self` access. All attributes are now declared on the base.

### 4. Remove `# type: ignore` bridges in `cfg.py`

Commit `e2ba3659` added `# type: ignore[attr-defined]` bridges in `interpreter/cfg.py` as a workaround for this exact issue. Remove them once the base is fixed.

---

## Scope

| File | Change |
|------|--------|
| `interpreter/instructions.py` | Promote 3 fields; add 2 property stubs; remove `inst: Any`; remove 33 compat blocks |
| `interpreter/cfg.py` | Remove `# type: ignore[attr-defined]` bridges |

No other files change. The constructor keyword-arg interface of every subclass is unchanged.

---

## Testing

This is a structural refactor with no behaviour change. The full test suite (13,235 tests) is the regression gate. No new tests are needed beyond confirming `poetry run pyright interpreter/ mcp_server/` reports fewer errors after the change.

Verify before commit:
- `poetry run pyright interpreter/ mcp_server/` — error count drops (baseline: 852)
- `poetry run python -m pytest tests/` — all 13,235 pass

---

## Out of Scope

- Migrating `Instruction` (the old flat factory in `ir.py`) — separate issue
- Fixing str/Register mismatches in frontends and COBOL — separate issues under red-dragon-r32l
- Other P2 type bugs — separate issues under red-dragon-r32l
