# COBOL FILE SECTION in SectionedLayout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make COBOL FILE SECTION record fields (FD entries) flow from the ProLeap bridge into `CobolASG.file_fields` and into a new `SectionedLayout.file` DataLayout — **no runtime wiring** (no `MaterialisedSectionedLayout` change, no `resolve()`/`has_field()` change, no region allocation, no I/O).

**Architecture:** Mirror exactly how WORKING-STORAGE / LINKAGE / LOCAL-STORAGE are already handled, with one structural difference: ProLeap's `FileSection` exposes `getFileDescriptionEntries()` (a list of `FD`s) rather than a flat root-entry list, and each `FileDescriptionEntry` is a `DataDescriptionEntryContainer` with `getRootDataDescriptionEntries()`. So the bridge collects every FD's root entries into one list and serializes it like the other sections. The Python side adds a `file_fields` list to the ASG and a `file: DataLayout` to `SectionedLayout`, built via the existing `build_data_layout`. Nothing consumes `SectionedLayout.file` yet — that (resolution, region binding, I/O) is the deferred "wiring."

**Tech Stack:** Java 17 / Maven (ProLeap bridge), Python 3.13 (poetry, pytest). Integration tests need `PROLEAP_BRIDGE_JAR`; this plan assumes it's available so the FILE-SECTION parse path actually runs.

**Context for the implementer:**
- Section serialization to mirror: `proleap-bridge/src/main/java/org/reddragon/bridge/AsgSerializer.java` lines ~90-118 (WORKING-STORAGE / LINKAGE / LOCAL-STORAGE). Each uses `section.getRootDataDescriptionEntries()` → `DataFieldSerializer.serializeEntries(rootEntries)` → `asg.add("<name>_fields", fields)`.
- ProLeap APIs (verified present): `DataDivision.getFileSection()` → `FileSection`; `FileSection.getFileDescriptionEntries()` → `List<FileDescriptionEntry>`; `FileDescriptionEntry extends DataDescriptionEntryContainer` which has `getRootDataDescriptionEntries()`.
- Python ASG: `interpreter/cobol/asg_types.py` — `CobolASG` has `data_fields` / `linkage_fields` / `local_storage_fields` (list[CobolField]) with matching `from_dict`/`to_dict` blocks.
- Layout: `interpreter/cobol/sectioned_layout.py` — `SectionedLayout` (frozen dataclass: `working_storage`, `linkage`, `local_storage`: DataLayout) and `build_sectioned_layout(asg)`. `DataLayout()` is constructible with no args (defaults to empty).
- Conventions: `poetry run python -m pytest` (NOT `poetry run pytest`); `poetry run python -m black`; the covers-guard hook requires `@covers(...)` on every test function; the pre-commit hook runs the full suite.

---

## File Structure

- **`proleap-bridge/src/main/java/org/reddragon/bridge/AsgSerializer.java`** (modify) — serialize FILE SECTION FD record fields → `"file_fields"`.
- **`interpreter/cobol/asg_types.py`** (modify) — add `CobolASG.file_fields` with `from_dict`/`to_dict` handling.
- **`interpreter/cobol/sectioned_layout.py`** (modify) — add `SectionedLayout.file: DataLayout`; `build_sectioned_layout` builds it from `asg.file_fields`.
- **`tests/unit/cobol/test_file_section_layout.py`** (create) — unit test (hand-built `CobolASG`) that FD fields land in `SectionedLayout.file` and are accessible.
- **`tests/integration/test_cobol_file_section.py`** (create) — integration test (real ProLeap parse) that a FILE SECTION program populates `asg.file_fields` and `build_sectioned_layout(asg).file`. Tagged `@covers(NotLanguageFeature.INFRASTRUCTURE)` — NOT `SECTION_FILE` (the feature isn't runtime-functional yet).

---

## Task 1: Bridge serializes FILE SECTION FD record fields

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/AsgSerializer.java`

This is verified end-to-end by Task 4's integration test; here it's a manual JAR smoke check.

- [ ] **Step 1: Add imports**

In `AsgSerializer.java`, alongside the existing `import io.proleap.cobol.asg.metamodel.data.linkage.LinkageSection;` etc., add:

```java
import io.proleap.cobol.asg.metamodel.data.file.FileSection;
import io.proleap.cobol.asg.metamodel.data.file.FileDescriptionEntry;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntry;
import java.util.ArrayList;
import java.util.List;
```

(If `DataDescriptionEntry` / `List` / `ArrayList` are already imported, do not duplicate — check the existing import block first. The exact package for `FileSection`/`FileDescriptionEntry` is `io.proleap.cobol.asg.metamodel.data.file`; verify by checking the metamodel source path `proleap-bridge/proleap-cobol-parser/src/main/java/io/proleap/cobol/asg/metamodel/data/file/`.)

- [ ] **Step 2: Serialize the FILE SECTION**

Find the block that serializes LINKAGE and LOCAL-STORAGE (ends around line 118, just before the closing brace of the method). Immediately after the LOCAL-STORAGE block, add:

```java
        FileSection fileSection = dataDivision.getFileSection();
        if (fileSection != null) {
            List<DataDescriptionEntry> rootEntries = new ArrayList<>();
            for (FileDescriptionEntry fd : fileSection.getFileDescriptionEntries()) {
                rootEntries.addAll(fd.getRootDataDescriptionEntries());
            }
            if (!rootEntries.isEmpty()) {
                JsonArray fields = DataFieldSerializer.serializeEntries(rootEntries);
                asg.add("file_fields", fields);
                LOG.info("Serialized " + fields.size() + " file-section fields");
            }
        }
```

Note: all FDs' root entries are flattened into one `serializeEntries` call. For a single FD (the common case) the byte offsets are correct. Multiple FDs would get sequential offsets rather than each starting at 0 — acceptable for this layout-only slice (no file buffering yet); leave a one-line code comment noting it.

- [ ] **Step 3: Rebuild the JAR**

Run: `cd proleap-bridge && mvn package -q -DskipTests 2>&1 | grep -E "BUILD FAILURE|ERROR" | head -5`
Expected: no `ERROR` / `BUILD FAILURE` lines. Fix imports/types until it compiles. (Build WARNING lines about Unsafe/restricted methods are harmless.)

- [ ] **Step 4: Manual smoke check**

Run from repo root:

```bash
JAR=proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
printf '       IDENTIFICATION DIVISION.\n       PROGRAM-ID. T.\n       ENVIRONMENT DIVISION.\n       INPUT-OUTPUT SECTION.\n       FILE-CONTROL.\n           SELECT CUST-FILE ASSIGN TO CUSTDAT.\n       DATA DIVISION.\n       FILE SECTION.\n       FD  CUST-FILE.\n       01  CUSTOMER-RECORD.\n           05  CUST-ID    PIC 9(5).\n           05  CUST-NAME  PIC X(20).\n       WORKING-STORAGE SECTION.\n       01  WS-EOF PIC X VALUE "N".\n       PROCEDURE DIVISION.\n           STOP RUN.\n' | java -jar "$JAR" 2>&1 | grep -c "file_fields"
```

Expected: prints `1` (the emitted ASG JSON contains a `file_fields` key). If `0`, the FILE SECTION wasn't serialized — re-check `getFileSection()`/`getFileDescriptionEntries()` and that the JAR was rebuilt.

- [ ] **Step 5: Commit**

```bash
git add proleap-bridge/src/main/java/org/reddragon/bridge/AsgSerializer.java
git commit -m "feat(bridge): serialize COBOL FILE SECTION FD record fields as file_fields"
```

(The rebuilt JAR under `proleap-bridge/target/` is a build artifact — do not git-add it.)

---

## Task 2: `CobolASG.file_fields`

**Files:**
- Modify: `interpreter/cobol/asg_types.py`
- Test: `tests/unit/cobol/test_file_section_layout.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/cobol/test_file_section_layout.py`:

```python
"""COBOL FILE SECTION fields flow into the ASG and SectionedLayout (layout only,
no runtime wiring) — red-dragon-4q25.32."""

from __future__ import annotations

from interpreter.cobol.asg_types import CobolASG, CobolField
from tests.covers import covers, NotLanguageFeature


def _file_record_fields() -> list[CobolField]:
    # 01 CUSTOMER-RECORD / 05 CUST-ID PIC 9(5) / 05 CUST-NAME PIC X(20)
    return [
        CobolField(
            name="CUSTOMER-RECORD",
            level=1,
            pic="",
            usage="DISPLAY",
            offset=0,
            children=[
                CobolField(name="CUST-ID", level=5, pic="9(5)", usage="DISPLAY", offset=0),
                CobolField(name="CUST-NAME", level=5, pic="X(20)", usage="DISPLAY", offset=5),
            ],
        )
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cobol_asg_round_trips_file_fields():
    asg = CobolASG(program_id="T", file_fields=_file_record_fields())
    assert len(asg.file_fields) == 1
    assert asg.file_fields[0].name == "CUSTOMER-RECORD"
    # to_dict/from_dict round-trip preserves file_fields
    restored = CobolASG.from_dict(asg.to_dict())
    assert [f.name for f in restored.file_fields] == ["CUSTOMER-RECORD"]
```

(Verify `CobolField`'s constructor kwargs against `interpreter/cobol/asg_types.py` — use the same fields the WORKING-STORAGE tests use; `children` is the nested-field list. If `CobolField` requires different kwargs, match the existing definition exactly.)

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cobol/test_file_section_layout.py::test_cobol_asg_round_trips_file_fields -x -q`
Expected: FAIL — `CobolASG.__init__() got an unexpected keyword argument 'file_fields'`.

- [ ] **Step 3: Add `file_fields` to `CobolASG`**

In `interpreter/cobol/asg_types.py`:

1. Add the field (after `local_storage_fields`):

```python
    local_storage_fields: list[CobolField] = field(default_factory=list)
    file_fields: list[CobolField] = field(default_factory=list)
```

2. In `from_dict`, after the `local_storage_fields=[...]` entry, add:

```python
            file_fields=[CobolField.from_dict(f) for f in data.get("file_fields", [])],
```

3. In `to_dict`, after the `local_storage_fields` block, add:

```python
        if self.file_fields:
            result["file_fields"] = [f.to_dict() for f in self.file_fields]
```

4. Update the class docstring's Attributes list to mention `file_fields: File Section (FD) record fields.`

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cobol/test_file_section_layout.py::test_cobol_asg_round_trips_file_fields -x -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add interpreter/cobol/asg_types.py tests/unit/cobol/test_file_section_layout.py
git commit -m "feat(cobol): CobolASG.file_fields for FILE SECTION records"
```

---

## Task 3: `SectionedLayout.file`

**Files:**
- Modify: `interpreter/cobol/sectioned_layout.py`
- Test: `tests/unit/cobol/test_file_section_layout.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/cobol/test_file_section_layout.py`:

```python
def test_build_sectioned_layout_includes_file_section():
    from interpreter.cobol.sectioned_layout import build_sectioned_layout

    asg = CobolASG(program_id="T", file_fields=_file_record_fields())
    layout = build_sectioned_layout(asg)
    # FILE SECTION fields are present in the dedicated `file` layout...
    assert layout.file.lookup_as_storage("CUST-ID") is not None
    assert layout.file.lookup_as_storage("CUST-NAME") is not None
    # ...and NOT leaked into working-storage (no wiring/merging).
    assert layout.working_storage.lookup_as_storage("CUST-ID") is None
```

(Add `@covers(NotLanguageFeature.INFRASTRUCTURE)` to this function too — the covers-guard hook requires it. Confirm `DataLayout.lookup_as_storage` is the correct accessor by checking how `MaterialisedSectionedLayout.resolve` calls it in `sectioned_layout.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cobol/test_file_section_layout.py::test_build_sectioned_layout_includes_file_section -x -q`
Expected: FAIL — `AttributeError: 'SectionedLayout' object has no attribute 'file'`.

- [ ] **Step 3: Add `file` to `SectionedLayout` and build it**

In `interpreter/cobol/sectioned_layout.py`:

1. Add `field`/`DataLayout` import if needed (`DataLayout` is already imported; add `from dataclasses import dataclass, field` if `field` isn't imported — check the existing import line).

2. Add the attribute to `SectionedLayout` (give it a default so existing constructors don't break):

```python
@dataclass(frozen=True)
class SectionedLayout:
    """DataLayouts for all DATA DIVISION sections — pure data, no registers."""

    working_storage: DataLayout
    linkage: DataLayout
    local_storage: DataLayout
    file: DataLayout = field(default_factory=DataLayout)
```

3. In `build_sectioned_layout`, add the `file` argument:

```python
def build_sectioned_layout(asg: CobolASG) -> SectionedLayout:
    """Build SectionedLayout from a CobolASG — one DataLayout per section."""
    return SectionedLayout(
        working_storage=build_data_layout(asg.data_fields),
        linkage=build_data_layout(asg.linkage_fields),
        local_storage=build_data_layout(asg.local_storage_fields),
        file=build_data_layout(asg.file_fields),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cobol/test_file_section_layout.py -q`
Expected: PASS (both unit tests).

- [ ] **Step 5: Verify no other `SectionedLayout` constructor broke**

Run: `poetry run python -m pytest tests/unit/ -q -k "cobol or sectioned or layout" 2>&1 | tail -6`
Expected: PASS. (The `file` default makes the new field optional, so existing positional/keyword constructions of `SectionedLayout` and `MaterialisedSectionedLayout` are unaffected. `MaterialisedSectionedLayout` is a separate dataclass and is intentionally NOT changed in this slice.)

- [ ] **Step 6: Commit**

```bash
git add interpreter/cobol/sectioned_layout.py tests/unit/cobol/test_file_section_layout.py
git commit -m "feat(cobol): SectionedLayout.file from FILE SECTION fields (layout only)"
```

---

## Task 4: Integration test (real ProLeap parse) — layout only

**SECTION_FILE stays UNCOVERED.** This slice only puts FD fields in the layout; the
`SECTION_FILE` language feature is not "done" until `READ`/`WRITE` actually populate
and flush the FD record at runtime. Marking it covered now would game the coverage
number. So the test below claims `NotLanguageFeature.INFRASTRUCTURE` (it verifies the
layout plumbing), `red-dragon-4q25.32` stays OPEN, and the `@covers(SECTION_FILE)`
tag waits for the future READ/WRITE wiring slice.

**Files:**
- Create: `tests/integration/test_cobol_file_section.py`

- [ ] **Step 1: Write the test**

Create `tests/integration/test_cobol_file_section.py`:

```python
"""Integration: a COBOL FILE SECTION parses through the ProLeap bridge and its FD
record fields land in CobolASG.file_fields and SectionedLayout.file.

LAYOUT ONLY — no runtime wiring (READ/WRITE do not yet populate the FD record), so
this asserts the layout plumbing and is tagged INFRASTRUCTURE, NOT
@covers(SECTION_FILE). SECTION_FILE coverage waits for the READ/WRITE wiring slice
(red-dragon-4q25.32)."""

from __future__ import annotations

import pytest

from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from tests.covers import covers, NotLanguageFeature
from tests.integration.cobol_helpers import JAR_PATH, JAR_AVAILABLE, to_fixed

pytestmark = pytest.mark.skipif(
    not JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_file_section_fields_in_sectioned_layout():
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. FILEPROG.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            "    SELECT CUST-FILE ASSIGN TO CUSTDAT.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD  CUST-FILE.",
            "01  CUSTOMER-RECORD.",
            "    05  CUST-ID    PIC 9(5).",
            "    05  CUST-NAME  PIC X(20).",
            "WORKING-STORAGE SECTION.",
            '01  WS-EOF PIC X VALUE "N".',
            "PROCEDURE DIVISION.",
            "    STOP RUN.",
        ]
    )
    parser = ProLeapCobolParser(RealSubprocessRunner(), JAR_PATH)
    asg = parser.parse(source.encode("utf-8"))

    # FD record fields reached the ASG
    assert [f.name for f in asg.file_fields] == ["CUSTOMER-RECORD"]

    # ...and the SectionedLayout exposes them in its `file` layout
    layout = build_sectioned_layout(asg)
    assert layout.file.lookup_as_storage("CUST-ID") is not None
    assert layout.file.lookup_as_storage("CUST-NAME") is not None
    # WORKING-STORAGE still works and FILE fields didn't leak into it
    assert layout.working_storage.lookup_as_storage("WS-EOF") is not None
    assert layout.working_storage.lookup_as_storage("CUST-ID") is None
```

(Confirm `ProLeapCobolParser`/`RealSubprocessRunner` import paths against `interpreter/cobol/cobol_parser.py` and `interpreter/cobol/subprocess_runner.py`. `JAR_PATH`/`JAR_AVAILABLE`/`to_fixed` come from `tests/integration/cobol_helpers.py`.)

- [ ] **Step 2: Run the integration test**

Run: `poetry run python -m pytest tests/integration/test_cobol_file_section.py -v --no-header 2>&1 | tail -8`
Expected: PASS (1 passed). If `asg.file_fields` is empty, the Task-1 JAR change didn't take — confirm the rebuilt JAR and re-run.

- [ ] **Step 3: Confirm SECTION_FILE is still UNCOVERED (not gamed)**

Run: `poetry run python scripts/feature_coverage_audit.py --language cobol 2>&1 | grep -E "covered_count|uncovered_count|SECTION_FILE"`
Expected: `covered_count` **108** (unchanged), `uncovered_count` **6** (unchanged), and `SECTION_FILE` still listed in `uncovered`. This is intentional — the layout plumbing exists but the feature isn't runtime-functional until READ/WRITE wiring. The new test is tagged INFRASTRUCTURE, so coverage is correctly unaffected.

- [ ] **Step 4: Run the full COBOL suite for regressions**

Run: `poetry run python -m pytest tests/unit/cobol/ tests/integration/test_cobol_programs.py tests/integration/test_cobol_file_section.py -q 2>&1 | tail -5`
Expected: PASS.

- [ ] **Step 5: Format and commit (do NOT close red-dragon-4q25.32)**

```bash
poetry run python -m black tests/integration/test_cobol_file_section.py
git add tests/integration/test_cobol_file_section.py
git commit -m "test(cobol): FILE SECTION fields reach SectionedLayout end-to-end (layout only)"
```

- [ ] **Step 6: Record progress on the issue (keep it OPEN)**

`red-dragon-4q25.32` stays open — the layout half is done but the feature is not. Leave a progress note so the remaining work (READ/WRITE wiring) is explicit:

```bash
bd comment red-dragon-4q25.32 "Layout half done: FD record fields now flow ProLeap -> CobolASG.file_fields -> SectionedLayout.file (build_sectioned_layout). NOT closed: SECTION_FILE remains uncovered because there is no runtime wiring yet — READ must populate the FD record region and WRITE must flush it, and the record fields must be resolvable in PROCEDURE DIVISION (MaterialisedSectionedLayout + resolve() + region binding + I/O verb integration). @covers(SECTION_FILE) attaches when a READ-populates-record test passes."
git add issues/issues.jsonl 2>/dev/null && git commit -m "chore(beads): note FILE SECTION layout progress on 4q25.32" || true
```

---

## Self-Review

**Spec coverage (against the user's boundary — "up to FILE SECTION in SectionedLayout, no wiring"):**
- Bridge serializes FD fields → Task 1. ✓
- ASG carries `file_fields` → Task 2. ✓
- `SectionedLayout.file` built from them → Task 3. ✓
- Verified end-to-end via real parse → Task 4. ✓
- **No wiring:** `MaterialisedSectionedLayout`, `resolve()`/`has_field()`, region allocation in `lower_sectioned_data_division`, and the I/O verbs are all untouched — confirmed by the absence of any task touching them, and Task 3 Step 5 verifies the unchanged constructors still work. The unit/integration tests assert FILE fields do NOT leak into working-storage. ✓
- **Does NOT mark `SECTION_FILE` covered and does NOT close `red-dragon-4q25.32`.** The feature isn't runtime-functional until READ/WRITE wiring, so claiming coverage now would game the number. The slice tags its test INFRASTRUCTURE, leaves the issue open with a progress note, and reserves `@covers(SECTION_FILE)` for the wiring slice (`4q25.32`'s acceptance is correspondingly tightened — layout alone is not "done"). ✓

**Placeholder scan:** No TBDs. Each Java/Python edit shows complete code; the few "verify the import path / kwargs against the existing file" notes are precise verification steps, not hand-waving, because exact ProLeap package names and `CobolField` kwargs must be confirmed against source (paths given).

**Type consistency:** `file_fields: list[CobolField]` (ASG) feeds `build_data_layout(asg.file_fields)` → `SectionedLayout.file: DataLayout`, consumed in tests via `DataLayout.lookup_as_storage(...)` (the same accessor `MaterialisedSectionedLayout.resolve` uses). `build_data_layout` is the existing builder used for all three current sections. Names are consistent across all four tasks (`file_fields`, `file`).

**Boundary risk note:** If, during Task 3, an existing `SectionedLayout` construction breaks despite the default, STOP — it means a positional constructor exists that the default doesn't cover; reassess rather than forcing.
