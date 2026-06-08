# BMS-Tools Pipeline Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace red-dragon's regex BMS stub with the real `bms-tools` pipeline: generate symbolic copybooks from `.bms` sources, include them as ordinary copybooks, and drive `SEND/RECEIVE MAP` off the program's COBOL layout — deleting `BmsLoader`.

**Architecture:** A stage-0 generation step (gated on `BMS_TOOLS_HOME`) runs `hlasm_export <map>.bms | bms-copybook-gen` to emit symbolic copybooks into a dir; that dir is appended to `copybook_dirs`, so programs `COPY` their symbolic maps normally and `data_layout` holds the map groups. `SEND/RECEIVE MAP` resolve the symbolic group from the static `FROM`/`INTO` operand at lowering, pass the group's field names into the builtin, which reads/writes those fields from the WS region via `vm.data_layout`. `BmsLoader`/`BmsMap`/`_parse_bms_file`/stubs are deleted.

**Tech Stack:** Python 3.13, subprocess (no new Python import deps), pytest, ProLeap COBOL parser, the external `~/code/bms-tools` toolchain (C++ `hlasm_export` + `bms_copybook_gen`).

**Spec:** `docs/superpowers/specs/2026-06-08-bms-tools-pipeline-integration-design.md`

---

## Key facts (grounding — verified)

- **Gating pattern** (`tests/integration/cobol_helpers.py`): `JAR_PATH = os.environ.get("PROLEAP_BRIDGE_JAR", <default>)`; `JAR_AVAILABLE = os.path.isfile(JAR_PATH)`. Mirror this for `BMS_TOOLS_HOME`.
- **`hlasm_export`** CLI: `hlasm_export <source.bms> [--pretty] [--output <file>]` → JSON (with a `macro_invocations` array) to stdout or `--output`. Built binary lands at `$BMS_TOOLS_HOME/che-che4z-lsp-for-hlasm-fork/build/bin/hlasm_export` (per `build.sh` `BUILD_DIR=build`, `RUNTIME_OUTPUT_DIRECTORY=$BUILD_DIR/bin`). **Not built by red-dragon.**
- **`bms-copybook-gen`** CLI: `python -m bms_copybook_gen --input <json|-> --output <cpy|->` (package at `$BMS_TOOLS_HOME/python/bms_copybook_gen/src`, has `__main__.py`, `requires-python >=3.13`). Run via subprocess with `PYTHONPATH=$BMS_TOOLS_HOME/python/bms_copybook_gen/src` — **no install into red-dragon's venv**.
- **Generated copybook shape** (per `generator.py`): for a map `M` with field label `L`, the output record `01 MO.` contains `LL PIC S9(4) COMP` (length), `LA PIC X` (+ `LF` redefine, attr/flag), `LO PIC <picout|X(len)>` (data); the input record `01 MI REDEFINES MO.` contains `LI PIC <picin|X(len)>` (data) with FILLER length/attr. So the **output data field is `<L>O`, input data field is `<L>I`, length field is `<L>L`** — exactly the suffix convention `screen.py` already uses (`symbolic_names`: `base+"O"/"I"/"L"`).
- **Every CardDemo `SEND MAP` has `FROM(<group>O)`; every `RECEIVE MAP` has `INTO(<group>I)`** — a static data-name even when `MAP()` is dynamic. (Verified across COSGN00C/COACTVWC/COACTUPC/COCRDLIC/COCRDSLC/COADM01C/COBIL00C.)
- **`SEND/RECEIVE MAP` lowering today** (`strategy.py` ~466-504): for SEND TEXT emits `(r_text,)`; for MAP emits `(r_map, r_set, r_region)` where `r_region = Const(b"")` (the region arg is unused by the preferred path). `FROM`/`INTO` are **not** currently resolved.
- **`screen.py` preferred path today**: enumerates `bms_map.fields` (base names from the loader), derives `<base>O/<base>I/<base>L` via `symbolic_names`, and reads/writes them in the WS region via `vm.data_layout[name]` (`_read_ws_field`/`_write_ws_field`). The loader is the *only* source of the base-name set — that is what we replace.
- **Layout access**: lowering has `materialised: MaterialisedSectionedLayout` (`.resolve(name) -> (FieldLayout, Register)`, `.has_field(name)`). The structured `DataLayout` (per section) has `lookup_group(name)` and `all_leaves()`. `FieldLayout.offset` is **absolute** within its section/record. `vm.data_layout` is a flat `name -> {offset,length,...}` dict built from `DataLayout.all_fields()`.
- **Builtin wiring**: `CicsLoweringStrategy.__init__` registers the builtins via `make_send_map_builtin(bms_loader, screen_queue)`, `make_receive_map_builtin(bms_loader, input_queue)`, `make_send_text_builtin(screen_queue)` (only when `bms_loader`, `screen_queue`, `input_queue` are all non-None). `bms_loader` is captured in the closures, not stored on `self`.
- **`register_stub` call sites** (migration targets): `tests/unit/cics/test_screen_builtins.py`, `tests/unit/cics/test_bms_loader.py`, `tests/integration/cics/test_carddemo_signon_real.py`, `tests/integration/cics/test_sign_on_flow.py`, `tests/integration/cics/test_region_e2e.py`.

## File structure

- **Create** `interpreter/cics/bms/generate.py` — stage-0 generation: `.bms` dir → symbolic-copybook dir via the subprocess pipeline. One responsibility: run the external tool.
- **Create** `tests/integration/cics/bms_tools_helpers.py` — `BMS_TOOLS_HOME`/`HLASM_EXPORT`/`BMS_TOOLS_AVAILABLE` gating constants + the binary/CLI paths.
- **Create** `tests/fixtures/bms/SImpleMap.cpy` (committed real symbolic copybook fixture) for pure-unit `SEND/RECEIVE MAP` tests (no `BMS_TOOLS_HOME` needed).
- **Modify** `interpreter/cobol/sectioned_layout.py` — add `MaterialisedSectionedLayout.group_leaf_names(group_name)`.
- **Modify** `interpreter/cics/builtins/screen.py` — rewrite `make_send_map_builtin`/`make_receive_map_builtin` to drop `loader` and take the field-name list as a call arg.
- **Modify** `interpreter/cics/strategy.py` — `SEND/RECEIVE MAP` lowering resolves `FROM`/`INTO` group → field names → Const arg; drop `bms_loader` constructor param + its use.
- **Modify** `interpreter/cics/bootstrap.py` + test harnesses — append the generated copybook dir to `copybook_dirs`.
- **Delete** `interpreter/cics/bms/loader.py` and `tests/unit/cics/test_bms_loader.py`.
- **Modify** all `register_stub` test sites.

---

### Task 1: `BMS_TOOLS_HOME` gating helper

**Files:**
- Create: `tests/integration/cics/bms_tools_helpers.py`
- Test: `tests/unit/cics/test_bms_tools_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cics/test_bms_tools_helpers.py
"""Gating constants for the bms-tools pipeline (mirror cobol_helpers JAR gating)."""
from __future__ import annotations

from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_helpers_expose_gating_constants() -> None:
    from tests.integration.cics import bms_tools_helpers as h

    # The module exposes a home, the two tool paths, and a boolean availability gate.
    assert hasattr(h, "BMS_TOOLS_HOME")
    assert hasattr(h, "HLASM_EXPORT_BIN")
    assert hasattr(h, "BMS_COPYBOOK_GEN_SRC")
    assert isinstance(h.BMS_TOOLS_AVAILABLE, bool)
    # Availability is exactly "the hlasm_export binary exists".
    import os
    assert h.BMS_TOOLS_AVAILABLE == (
        h.HLASM_EXPORT_BIN is not None and os.path.isfile(h.HLASM_EXPORT_BIN)
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cics/test_bms_tools_helpers.py -v`
Expected: FAIL — `ModuleNotFoundError: ... bms_tools_helpers`.

- [ ] **Step 3: Write the helper**

```python
# tests/integration/cics/bms_tools_helpers.py
"""Gating + path constants for the external bms-tools pipeline.

Mirrors tests/integration/cobol_helpers.py (JAR_PATH/JAR_AVAILABLE). The pipeline
is an EXTERNAL, locally-built toolchain; everything that needs it skips when
BMS_TOOLS_HOME is unset or the hlasm_export binary is absent.
"""
from __future__ import annotations

import os
from pathlib import Path

BMS_TOOLS_HOME: str | None = os.environ.get("BMS_TOOLS_HOME") or (
    os.path.expanduser("~/code/bms-tools")
    if os.path.isdir(os.path.expanduser("~/code/bms-tools"))
    else None
)

HLASM_EXPORT_BIN: str | None = (
    str(Path(BMS_TOOLS_HOME) / "che-che4z-lsp-for-hlasm-fork" / "build" / "bin" / "hlasm_export")
    if BMS_TOOLS_HOME
    else None
)

BMS_COPYBOOK_GEN_SRC: str | None = (
    str(Path(BMS_TOOLS_HOME) / "python" / "bms_copybook_gen" / "src")
    if BMS_TOOLS_HOME
    else None
)

BMS_TOOLS_AVAILABLE: bool = bool(
    HLASM_EXPORT_BIN is not None and os.path.isfile(HLASM_EXPORT_BIN)
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cics/test_bms_tools_helpers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/cics/bms_tools_helpers.py tests/unit/cics/test_bms_tools_helpers.py
git commit -m "test(cics): BMS_TOOLS_HOME gating helper for the bms-tools pipeline"
```

---

### Task 2: Stage-0 generation module

**Files:**
- Create: `interpreter/cics/bms/generate.py`
- Test: `tests/integration/cics/test_bms_generate.py` (gated on `BMS_TOOLS_AVAILABLE`)

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/cics/test_bms_generate.py
"""Gated: the real bms-tools pipeline generates a symbolic copybook from a .bms."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.covers import covers, NotLanguageFeature
from tests.integration.cics.bms_tools_helpers import (
    BMS_TOOLS_AVAILABLE,
    HLASM_EXPORT_BIN,
    BMS_COPYBOOK_GEN_SRC,
)

_CARDDEMO_HOME = os.environ.get("CARDDEMO_HOME")

pytestmark = pytest.mark.skipif(
    not BMS_TOOLS_AVAILABLE or not _CARDDEMO_HOME,
    reason="needs BMS_TOOLS_HOME (built hlasm_export) and CARDDEMO_HOME",
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_generate_symbolic_copybooks_from_bms_dir(tmp_path: Path) -> None:
    from interpreter.cics.bms.generate import generate_symbolic_copybooks

    bms_dir = Path(_CARDDEMO_HOME) / "bms"
    out_dir = tmp_path / "sym"
    written = generate_symbolic_copybooks(
        bms_dir=bms_dir,
        out_dir=out_dir,
        hlasm_export_bin=HLASM_EXPORT_BIN,
        bms_copybook_gen_src=BMS_COPYBOOK_GEN_SRC,
    )
    # Every .bms produced a .cpy; the sign-on map's output group + a field are present.
    assert out_dir in {p.parent for p in written}
    cosgn = (out_dir / "COSGN00.cpy")
    assert cosgn.is_file()
    text = cosgn.read_text().upper()
    assert "01  COSGN0AO" in text or "01 COSGN0AO" in text
    assert "USERIDO" in text  # the USERID field's output data subfield
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BMS_TOOLS_HOME=~/code/bms-tools CARDDEMO_HOME=/Users/asgupta/code/aws-mainframe-carddemo/app poetry run python -m pytest tests/integration/cics/test_bms_generate.py -v`
Expected: FAIL — `ModuleNotFoundError: ...bms.generate` (or SKIP if the binary isn't built — build it first per bms-tools `build.sh`).

- [ ] **Step 3: Write the generation module**

```python
# interpreter/cics/bms/generate.py
"""Stage-0 BMS generation: .bms sources -> symbolic COBOL copybooks via bms-tools.

Runs the external pipeline `hlasm_export <map>.bms | bms-copybook-gen` once per
.bms file, writing <out_dir>/<stem>.cpy. The pipeline is an external, locally
built toolchain (see tests/integration/cics/bms_tools_helpers.py); callers gate
on its availability. No fallback parser — a failure is surfaced loudly.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_symbolic_copybooks(
    *,
    bms_dir: Path,
    out_dir: Path,
    hlasm_export_bin: str,
    bms_copybook_gen_src: str,
) -> list[Path]:
    """Generate one symbolic copybook per .bms file in bms_dir into out_dir.

    Returns the list of written .cpy paths. Raises on any tool failure (no
    silent empty output).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    env = dict(os.environ)
    env["PYTHONPATH"] = bms_copybook_gen_src + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    for bms_file in sorted(bms_dir.glob("*.bms")):
        export = subprocess.run(
            [hlasm_export_bin, str(bms_file)],
            capture_output=True,
            check=True,
        )
        gen = subprocess.run(
            ["python", "-m", "bms_copybook_gen"],
            input=export.stdout,
            capture_output=True,
            check=True,
            env=env,
        )
        out_path = out_dir / (bms_file.stem + ".cpy")
        out_path.write_bytes(gen.stdout)
        written.append(out_path)
        logger.info("BMS: generated %s from %s", out_path.name, bms_file.name)
    return written
```

- [ ] **Step 4: Run test to verify it passes** (requires the built binary)

Run: `BMS_TOOLS_HOME=~/code/bms-tools CARDDEMO_HOME=/Users/asgupta/code/aws-mainframe-carddemo/app poetry run python -m pytest tests/integration/cics/test_bms_generate.py -v`
Expected: PASS. (If `hlasm_export` is not built, the test SKIPs — build it once: `cd ~/code/bms-tools/che-che4z-lsp-for-hlasm-fork && ./build.sh`.)

- [ ] **Step 5: Commit**

```bash
git add interpreter/cics/bms/generate.py tests/integration/cics/test_bms_generate.py
git commit -m "feat(cics): stage-0 bms-tools generation (.bms -> symbolic copybooks)"
```

---

### Task 3: `group_leaf_names` on the layout

**Files:**
- Modify: `interpreter/cobol/sectioned_layout.py`
- Test: `tests/unit/cobol/test_sectioned_layout_group_leaves.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cobol/test_sectioned_layout_group_leaves.py
"""MaterialisedSectionedLayout exposes a group's leaf field names."""
from __future__ import annotations

from interpreter.cobol.data_layout import DataLayout, FieldLayout
from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.register import Register
from tests.covers import covers, NotLanguageFeature


def _alpha(n: int) -> CobolTypeDescriptor:
    return CobolTypeDescriptor(category=CobolDataCategory.ALPHANUMERIC, total_digits=n)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_group_leaf_names_returns_children_in_order() -> None:
    grp = DataLayout(
        fields={
            "USERIDO": FieldLayout(name="USERIDO", type_descriptor=_alpha(8), offset=12, byte_length=8),
            "ERRMSGO": FieldLayout(name="ERRMSGO", type_descriptor=_alpha(78), offset=20, byte_length=78),
        },
        offset=0,
        total_bytes=98,
    )
    ws = DataLayout(groups={"COSGN0AO": grp}, offset=0, total_bytes=98)
    empty = DataLayout()
    mat = MaterialisedSectionedLayout(
        working_storage=(ws, Register("%ws")),
        linkage=(empty, Register("%lk")),
        local_storage=(empty, Register("%ls")),
    )
    assert mat.group_leaf_names("COSGN0AO") == ["USERIDO", "ERRMSGO"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_group_leaf_names_missing_group_returns_empty() -> None:
    empty = DataLayout()
    mat = MaterialisedSectionedLayout(
        working_storage=(empty, Register("%ws")),
        linkage=(empty, Register("%lk")),
        local_storage=(empty, Register("%ls")),
    )
    assert mat.group_leaf_names("NOPE") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cobol/test_sectioned_layout_group_leaves.py -v`
Expected: FAIL — `AttributeError: ...has no attribute 'group_leaf_names'`.

- [ ] **Step 3: Implement the method** (add to `MaterialisedSectionedLayout` in `interpreter/cobol/sectioned_layout.py`)

```python
    def group_leaf_names(self, group_name: str) -> list[str]:
        """Return the leaf field names of a group, searched across sections.

        Order is the layout's depth-first order. Returns [] if no such group.
        Precedence mirrors resolve(): LOCAL-STORAGE > WORKING-STORAGE > LINKAGE.
        """
        for layout, _reg in (
            self.local_storage,
            self.working_storage,
            self.linkage,
        ):
            try:
                grp = layout.lookup_group(group_name)
            except KeyError:
                continue
            return [leaf.name for leaf in grp.all_leaves()]
        return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cobol/test_sectioned_layout_group_leaves.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add interpreter/cobol/sectioned_layout.py tests/unit/cobol/test_sectioned_layout_group_leaves.py
git commit -m "feat(cobol): MaterialisedSectionedLayout.group_leaf_names"
```

---

### Task 4: Rewrite `SEND MAP` builtin (drop loader; take field names)

**Files:**
- Modify: `interpreter/cics/builtins/screen.py`
- Test: `tests/unit/cics/test_screen_builtins.py` (rewrite the SEND MAP portion)

**Context:** The new `__cics_send_map` takes args `(map_name, base_names)`, where `base_names` is the list of output **base** names (e.g. `["USERID","ERRMSG"]`) — derived at lowering by stripping the `O` suffix from the output group's `<base>O` leaves. It reads each `<base>O` from the WS region via `vm.data_layout` (unchanged read mechanics), keys the screen dict on `base`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cics/test_screen_builtins.py  (replace the SEND MAP test; keep imports)
"""Unit tests for SEND/RECEIVE MAP builtins — layout-driven, no BmsLoader."""
from __future__ import annotations

import queue
import struct

from interpreter.cics.builtins.screen import make_send_map_builtin
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm_types import VMState
from tests.covers import covers, NotLanguageFeature


class _FakeVM:
    """Minimal VMState stand-in exposing a WS region + flat data_layout."""

    def __init__(self, region: bytearray, layout: dict, addr: int = 1) -> None:
        self._region = region
        self.data_layout = layout
        self._addr = addr

    # _ws_region() calls _get_ws_region_addr(vm) + vm.region_get(addr).
    def region_get(self, addr):
        return self._region if addr == self._addr else None


def _tv(v):
    return TypedValue(value=v)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_send_map_reads_named_output_fields_from_ws(monkeypatch) -> None:
    # WS layout: USERIDO at 0 len 8, ERRMSGO at 8 len 78.
    layout = {
        "USERIDO": {"offset": 0, "length": 8},
        "ERRMSGO": {"offset": 8, "length": 78},
    }
    region = bytearray(b"\x40" * 86)
    region[0:8] = "USER0001".encode("cp037")
    vm = _FakeVM(region, layout)
    monkeypatch.setattr(
        "interpreter.cics.builtins.system._get_ws_region_addr", lambda _vm: 1
    )
    sq: queue.Queue = queue.Queue()
    builtin = make_send_map_builtin(sq)
    builtin([_tv("COSGN0A"), _tv(["USERID", "ERRMSG"])], vm)  # (map_name, base_names)
    item = sq.get_nowait()
    assert item["map"] == "COSGN0A"
    assert item["fields"]["USERID"] == "USER0001"
    assert item["fields"]["ERRMSG"] == ""  # spaces -> rstripped empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cics/test_screen_builtins.py::test_send_map_reads_named_output_fields_from_ws -v`
Expected: FAIL — `make_send_map_builtin` still requires a `loader` positional arg.

- [ ] **Step 3: Rewrite `make_send_map_builtin`** in `interpreter/cics/builtins/screen.py` (drop `loader`; read base names from args[1]; keep `_ws_region`/`_read_ws_field`)

```python
def make_send_map_builtin(screen_queue: "queue.Queue[Any]") -> object:
    def __cics_send_map(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        map_name = _map_name(args, 0)
        base_names = list(args[1].value) if len(args) > 1 and args[1].value else []
        _addr, ws = _ws_region(vm)
        symbolic: dict[str, str] = {}
        if ws is not None:
            for base in base_names:
                raw = _read_ws_field(vm, ws, base + "O")
                if raw is not None:
                    symbolic[base] = raw.decode("cp037", errors="replace").rstrip()
        screen_queue.put({"map": map_name, "fields": symbolic})
        return BuiltinResult(value=None)

    return __cics_send_map
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cics/test_screen_builtins.py::test_send_map_reads_named_output_fields_from_ws -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add interpreter/cics/builtins/screen.py tests/unit/cics/test_screen_builtins.py
git commit -m "feat(cics): SEND MAP reads named output fields from layout (no BmsLoader)"
```

---

### Task 5: Rewrite `RECEIVE MAP` builtin (drop loader; take field names)

**Files:**
- Modify: `interpreter/cics/builtins/screen.py`
- Test: `tests/unit/cics/test_screen_builtins.py` (add RECEIVE MAP test)

**Context:** New `__cics_receive_map` takes args `(map_name, base_names)` where `base_names` are the input **base** names (stripped `I` suffix from the input group's `<base>I` leaves). For each input value, write `<base>I` and set `<base>L` (length) in the WS region via `vm.data_layout` (those names resolve through the output map that the input redefines). EIBAID write-back unchanged.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/unit/cics/test_screen_builtins.py
import struct
from interpreter.cics.builtins.screen import make_receive_map_builtin


class _InputEvent:
    def __init__(self, fields, eibaid="\x7d"):
        self.fields = fields
        self.eibaid = eibaid


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_receive_map_writes_named_input_fields_to_ws(monkeypatch) -> None:
    # WS layout: USERIDI data at 0 len 8, USERIDL length halfword at 100.
    layout = {
        "USERIDI": {"offset": 0, "length": 8},
        "USERIDL": {"offset": 100, "length": 2},
        "EIBAID": {"offset": 200, "length": 1},
    }
    region = bytearray(b"\x40" * 210)
    vm = _FakeVM(region, layout)
    monkeypatch.setattr(
        "interpreter.cics.builtins.system._get_ws_region_addr", lambda _vm: 1
    )
    # region_set is called to write back; add it to the fake.
    vm.region_set = lambda addr, data: region.__setitem__(slice(0, len(data)), data)

    iq: queue.Queue = queue.Queue()
    iq.put(_InputEvent({"USERID": "USER0001"}))
    builtin = make_receive_map_builtin(iq, timeout=1.0)
    builtin([_tv("COSGN0A"), _tv(["USERID"])], vm)
    assert bytes(region[0:8]) == "USER0001".encode("cp037")
    assert struct.unpack(">h", bytes(region[100:102]))[0] == 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cics/test_screen_builtins.py::test_receive_map_writes_named_input_fields_to_ws -v`
Expected: FAIL — `make_receive_map_builtin` still requires `loader`.

- [ ] **Step 3: Rewrite `make_receive_map_builtin`** in `interpreter/cics/builtins/screen.py`

```python
def make_receive_map_builtin(
    input_queue: "queue.Queue[Any]", timeout: float = 30.0
) -> object:
    def __cics_receive_map(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        base_names = set(args[1].value) if len(args) > 1 and args[1].value else set()
        try:
            item: Any = input_queue.get(timeout=timeout)
        except queue.Empty:
            logger.warning("RECEIVE MAP: timeout waiting for input")
            return BuiltinResult(value=None)
        field_values: dict[str, bytes | str] = getattr(item, "fields", item)
        aid: str = getattr(item, "eibaid", _DFHENTER)
        _write_eibaid(vm, aid)

        addr, ws = _ws_region(vm)
        if ws is not None:
            cp037_space = " ".encode("cp037")  # 0x40
            for base, v in field_values.items():
                if base not in base_names:
                    continue
                raw = v if isinstance(v, bytes) else v.encode("cp037", errors="replace")
                if _write_ws_field(vm, ws, base + "I", raw, pad=cp037_space):
                    _write_ws_field(vm, ws, base + "L", struct.pack(">h", len(raw)))
            assert addr is not None
            vm.region_set(addr, ws)
        return BuiltinResult(value=None)

    return __cics_receive_map
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cics/test_screen_builtins.py::test_receive_map_writes_named_input_fields_to_ws -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add interpreter/cics/builtins/screen.py tests/unit/cics/test_screen_builtins.py
git commit -m "feat(cics): RECEIVE MAP writes named input fields to layout (no BmsLoader)"
```

---

### Task 6: Lowering — resolve `FROM`/`INTO` group → field names; drop loader from strategy

**Files:**
- Modify: `interpreter/cics/strategy.py`
- Test: `tests/unit/cics/test_strategy_screen.py` (assert the lowered CALL carries the field-name list)

**Context:** In the BMS verb block (~466-504), for `SEND MAP` resolve the `FROM` operand's group, for `RECEIVE MAP` the `INTO` operand's group, via `materialised.group_leaf_names(<group>)`. Strip the trailing `O` (send) / `I` (receive) to get base names; emit them as a `Const` list arg. The map name stays via `emit_operand_value`. Drop the `b""` region arg. Builtin registration drops the `bms_loader` argument; the `bms_loader` constructor param is removed.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cics/test_strategy_screen.py  (add)
"""SEND/RECEIVE MAP lowering resolves the FROM/INTO group's fields into the CALL."""
from __future__ import annotations

# Use the existing harness in this file for lowering a single EXEC CICS statement
# with a known layout group. (Mirror the file's existing fake EmitContext / layout
# construction — see the existing tests in this module for the exact helper.)
from interpreter.instructions import Const, CallFunction
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_send_map_lowers_from_group_field_names():
    # Layout has group COSGN0AO with leaves USERIDO, ERRMSGO.
    # Lower: EXEC CICS SEND MAP('COSGN0A') MAPSET('COSGN00') FROM(COSGN0AO) END-EXEC
    insts = _lower_exec_cics(  # helper provided by this test module's harness
        "EXEC CICS SEND MAP('COSGN0A') MAPSET('COSGN00') FROM(COSGN0AO) END-EXEC",
        group_leaf_names={"COSGN0AO": ["USERIDO", "ERRMSGO"]},
    )
    call = next(i for i in insts if isinstance(i, CallFunction) and str(i.func_name) == "__cics_send_map")
    # Second arg register is a Const holding the base-name list.
    names_reg = call.args[1]
    const = next(i for i in insts if isinstance(i, Const) and i.result_reg == names_reg)
    assert const.value == ["USERID", "ERRMSG"]
```

> Implementer note: this module already lowers EXEC CICS via the real `CicsLoweringStrategy.lower(...)` against a fake/real `EmitContext` + `MaterialisedSectionedLayout`. Reuse that harness; the `group_leaf_names` kwarg above is shorthand for "construct a layout whose `COSGN0AO` group has those leaves." If the existing harness builds a `MaterialisedSectionedLayout`, build one with a `DataLayout(groups={"COSGN0AO": DataLayout(fields={...})})` so `group_leaf_names` returns the leaves.

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cics/test_strategy_screen.py::test_send_map_lowers_from_group_field_names -v`
Expected: FAIL — the lowered CALL has no base-name list arg (today it emits `(r_map, r_set, r_region)`).

- [ ] **Step 3: Rewrite the BMS verb lowering block** in `interpreter/cics/strategy.py` (replace the MAP branch of the `if bms_builtin:` section)

```python
        # ── BMS screen verbs ──────────────────────────────────────────────
        bms_builtin = _BMS_VERBS.get(verb)
        if bms_builtin:
            if verb == "SEND TEXT":
                text_op = opts.get("TEXT")
                r_text = ctx.fresh_reg()
                ctx.emit_inst(
                    Const(result_reg=r_text, value=text_op.text if text_op is not None else "")
                )
                r_res = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(result_reg=r_res, func_name=FuncName(bms_builtin), args=(r_text,))
                )
                return
            # MAP name (may be a dynamic data-name) -> runtime value via the resolver.
            r_map = emit_operand_value(ctx, opts.get("MAP", opts.get("MAPNAME")), materialised)
            # The symbolic group is the STATIC FROM (SEND) / INTO (RECEIVE) operand.
            if verb == "RECEIVE MAP":
                group_op, suffix = opts.get("INTO"), "I"
            else:  # SEND MAP
                group_op, suffix = opts.get("FROM"), "O"
            group_name = group_op.text if group_op is not None else ""
            leaves = ctx.group_leaf_names(group_name, materialised) if group_name else []
            base_names = [n[: -len(suffix)] for n in leaves if n.endswith(suffix)]
            r_names = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=r_names, value=base_names))
            r_res = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=r_res,
                    func_name=FuncName(bms_builtin),
                    args=(r_map, r_names),
                )
            )
            return
```

Add a thin pass-through on `EmitContext` so the strategy can reach the layout helper (in `interpreter/cobol/emit_context.py`):

```python
    def group_leaf_names(self, group_name: str, materialised: MaterialisedSectionedLayout) -> list[str]:
        """Leaf field names of a symbolic-map group (for SEND/RECEIVE MAP lowering)."""
        return materialised.group_leaf_names(group_name)
```

Update builtin registration in `CicsLoweringStrategy.__init__` (drop `bms_loader`):

```python
        if screen_queue is not None and input_queue is not None:
            from interpreter.cics.builtins.screen import (  # noqa: PLC0415
                make_send_map_builtin,
                make_receive_map_builtin,
                make_send_text_builtin,
            )

            _register(Builtins.TABLE, "__cics_send_map", make_send_map_builtin(screen_queue))
            _register(Builtins.TABLE, "__cics_receive_map", make_receive_map_builtin(input_queue))
            _register(Builtins.TABLE, "__cics_send_text", make_send_text_builtin(screen_queue))
```

Remove the `bms_loader` parameter from `CicsLoweringStrategy.__init__` signature and its docstring.

- [ ] **Step 4: Run test to verify it passes** + the screen unit tests

Run: `poetry run python -m pytest tests/unit/cics/test_strategy_screen.py tests/unit/cics/test_screen_builtins.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add interpreter/cics/strategy.py interpreter/cobol/emit_context.py tests/unit/cics/test_strategy_screen.py
git commit -m "feat(cics): SEND/RECEIVE MAP lowering resolves FROM/INTO group field names; drop bms_loader param"
```

---

### Task 7: Delete `loader.py` + migrate all stub-based tests (single cohesive change)

**Files:**
- Delete: `interpreter/cics/bms/loader.py`, `tests/unit/cics/test_bms_loader.py`
- Modify: `tests/integration/cics/test_region_e2e.py`, `tests/integration/cics/test_sign_on_flow.py`, `interpreter/cics/builtins/screen.py` (remove now-dead helpers `extract_fields`/`write_fields` refs + `BmsLoader` import), any `from interpreter.cics.bms.loader import ...`
- Create: `tests/fixtures/bms/SignonMap.cpy` (small real symbolic copybook fixture)

**Context:** This removes the loader and everything depending on it in one commit so the tree never half-compiles. The synthetic integration tests (`test_region_e2e.py`, `test_sign_on_flow.py`) currently build programs that `SEND MAP('SGNMAP')` etc. with `register_stub`. Migrate them to `COPY` a committed fixture copybook that defines the symbolic group (e.g. `01 SGNMAPO. ... 01 SGNMAPI REDEFINES SGNMAPO.`), so the layout supplies the fields. Pure-unit tests already use `_FakeVM` (Tasks 4–5) and need no copybook.

- [ ] **Step 1: Write/define the fixture copybook**

```cobol
      * tests/fixtures/bms/SignonMap.cpy  — minimal symbolic map for SGNMAP
       01  SGNMAPO.
           02  MSGL    PIC S9(4) COMP.
           02  MSGA    PIC X.
           02  MSGO    PIC X(40).
       01  SGNMAPI REDEFINES SGNMAPO.
           02  FILLER  PIC S9(4) COMP.
           02  FILLER  PIC X.
           02  MSGI    PIC X(40).
```

- [ ] **Step 2: Grep to confirm every consumer is handled**

Run:
```bash
grep -rn "bms.loader\|BmsLoader\|BmsMap\|BmsField\|register_stub\|extract_fields\|write_fields" interpreter/ tests/
```
Expected after edits: only references inside files you are deleting/rewriting in this task. Resolve every hit (update imports, replace stub registration with fixture `COPY`, delete the loader-specific unit test).

- [ ] **Step 3: Make the edits**

- Delete `interpreter/cics/bms/loader.py` and `tests/unit/cics/test_bms_loader.py`.
- In `interpreter/cics/builtins/screen.py`, remove `from interpreter.cics.bms.loader import BmsLoader` and any remaining loader/`extract_fields`/`write_fields` references (the Task 4/5 rewrites already dropped their use).
- In `test_region_e2e.py` / `test_sign_on_flow.py`: drop `BmsLoader`/`register_stub`; pass the fixture dir on `copybook_dirs` and have the test program `COPY SIGNONMAP` (or inline the `01 SGNMAPO`/`SGNMAPI` records directly in the program's WORKING-STORAGE if the test builds source inline). Construct the strategy without `bms_loader=`.

- [ ] **Step 4: Run the full CICS suite (with `BMS_TOOLS_HOME` unset — gated tests skip)**

Run: `poetry run python -m pytest tests/unit/cics/ tests/integration/cics/ -q`
Expected: PASS (gated bms-generate + real-carddemo tests SKIP; everything else green). Then full suite: `poetry run python -m pytest -x -q`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(cics): delete BmsLoader; SEND/RECEIVE MAP driven by the COBOL layout (red-dragon-zvta)"
```

---

### Task 8: Wire generated copybook dir into the CICS compile path + migrate the durable CardDemo test

**Files:**
- Modify: `tests/integration/cics/test_carddemo_signon_real.py`
- Modify (if needed): `interpreter/cics/bootstrap.py` / `run_carddemo_region` to accept extra `copybook_dirs` (the parser is constructed by the caller, so the test wires it; only touch bootstrap if a caller needs it).

**Context:** The durable test currently builds the parser with `copybook_dirs=[cpy, cpy-bms, cics_copybooks]` and registers stub maps. Migrate it: gate additionally on `BMS_TOOLS_AVAILABLE`; in setup, run `generate_symbolic_copybooks(bms_dir=app/"bms", out_dir=tmp, ...)` and append `tmp` to `copybook_dirs`; drop `_map_loader()`/`bms_loader=`; the programs' `COPY` of the symbolic maps now resolves from the generated dir. Assertions on `screen_queue` field values (`TRNNAME`, `PGMNAME`, etc.) stay — now produced from real generated copybooks.

- [ ] **Step 1: Update the durable test**

```python
# tests/integration/cics/test_carddemo_signon_real.py  (key changes)
from tests.integration.cics.bms_tools_helpers import (
    BMS_TOOLS_AVAILABLE, HLASM_EXPORT_BIN, BMS_COPYBOOK_GEN_SRC,
)
from interpreter.cics.bms.generate import generate_symbolic_copybooks

pytestmark = pytest.mark.skipif(
    not _CARDDEMO_HOME or not JAR_AVAILABLE or not BMS_TOOLS_AVAILABLE,
    reason="manual: set CARDDEMO_HOME + BMS_TOOLS_HOME (built hlasm_export) + ProLeap JAR",
)

# in the test body, before constructing the parser:
sym_dir = tmp_path / "sym"            # use the pytest tmp_path fixture
generate_symbolic_copybooks(
    bms_dir=app / "bms", out_dir=sym_dir,
    hlasm_export_bin=HLASM_EXPORT_BIN, bms_copybook_gen_src=BMS_COPYBOOK_GEN_SRC,
)
parser = ProLeapCobolParser(
    RealSubprocessRunner(), JAR_PATH,
    copybook_dirs=[app / "cpy", app / "cpy-bms", _CICS_COPYBOOKS, sym_dir],
)
strategy = CicsLoweringStrategy(
    context_holder=context_holder, result_holder=result_holder,
    vsam_engine=_usrsec_engine(), screen_queue=screen_q, input_queue=input_q,
)   # no bms_loader=, no _map_loader()
```

Delete `_map_loader()`. Add `tmp_path` to the test signature.

> Note: CardDemo ships `cpy-bms/*.CPY` already. Appending `sym_dir` LAST and trusting the program's `COPY <mapcopybook>` to resolve from it requires the generated file name to match the program's `COPY` target. Verify the copybook member name the programs `COPY` for the map (e.g. `COPY COSGN00` vs the generated `COSGN00.cpy`) and name the generated files to match; if CardDemo's `COPY` target differs from the `.bms` stem, map the names in `generate_symbolic_copybooks` (out filename = the COPY member name). Capture the exact member name during implementation from the program source and the cpy-bms dir.

- [ ] **Step 2: Run the durable test (gated)**

Run:
```bash
BMS_TOOLS_HOME=~/code/bms-tools CARDDEMO_HOME=/Users/asgupta/code/aws-mainframe-carddemo/app \
  poetry run python -m pytest tests/integration/cics/test_carddemo_signon_real.py -v
```
Expected: PASS — the three-turn flow renders `COSGN0A`/`COMEN1A` from the **generated** copybooks (no stubs). If the generated copybook member names don't match the programs' `COPY` targets, fix the naming per the Step-1 note.

- [ ] **Step 3: Run full suite with the env UNSET (durable + generate tests skip)**

Run: `poetry run python -m pytest -x -q`
Expected: PASS; `lint-imports` 0 broken; `black` clean.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test(cics): durable CardDemo test loads real maps via bms-tools (no stubs)"
```

---

## Self-review

**Spec coverage:**
- (1) gating helper → Task 1 ✓
- (2) stage-0 generation subprocess → Task 2 ✓
- (3) wire dir into copybook_dirs → Task 8 ✓ (+ note on member-name matching)
- (4) rewrite SEND/RECEIVE MAP, descriptors resolved at lowering → Tasks 4,5,6 ✓ (field-name list, resolved from static FROM/INTO group, passed as Const arg)
- (5) delete loader.py + drop loader params → Tasks 6,7 ✓
- (6) migrate durable + CICS tests; real .cpy fixture for unit tests → Tasks 7,8 (fixture in Task 7; `_FakeVM` for pure-unit SEND/RECEIVE in Tasks 4–5) ✓
- (7) gated generation unit test → Task 2 ✓

**Open items deliberately deferred to implementation (not placeholders — facts to capture from the tree at build time):** the exact built `hlasm_export` path if `build.sh` is customised; the precise `COPY` member name the CardDemo programs use for each map (Task 8 note); the existing `test_strategy_screen.py` lowering harness shape (Task 6 note). Each is called out at its task with how to resolve it.

**Type consistency:** builtin signatures — `make_send_map_builtin(screen_queue)`, `make_receive_map_builtin(input_queue, timeout=...)`, `make_send_text_builtin(screen_queue)` (loader dropped consistently across Tasks 4–6). Call args: `__cics_send_map`/`__cics_receive_map` both `(map_name, base_names)`. `group_leaf_names(group_name)` on `MaterialisedSectionedLayout` (Task 3) and the `EmitContext.group_leaf_names(group_name, materialised)` pass-through (Task 6) match.

**Invariant check:** no fallback parser, no stub registry survives; unset env → skip; the field set always derives from the bms-tools-generated copybook via the layout.
