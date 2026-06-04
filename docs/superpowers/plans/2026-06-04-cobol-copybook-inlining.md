# COBOL COPY Copybook Inlining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make COBOL `COPY` copybook inlining work by threading an explicit copybook search path from the Python frontend to the ProLeap bridge.

**Architecture:** The Python parser holds a list of copybook directories (injected at frontend construction) and passes them to the Java bridge as repeatable `-copybook-dir` args; the bridge configures ProLeap's `CobolParserParams.setCopyBookDirectories(...)`. Source still flows via stdin. `compile_directory` defaults the dirs to the recursive project tree; `run()` defaults to empty (no behavior change for COPY-free programs). A missing copybook becomes a clean Python-side `CobolParseError`.

**Tech Stack:** Python 3.13 (poetry, pytest, pytest-xdist), Java 17 (Maven) for the ProLeap bridge, the existing `PROLEAP_BRIDGE_JAR` subprocess integration.

**Spec:** `docs/superpowers/specs/2026-06-04-cobol-copybook-inlining-design.md`

---

## File Structure

- **`proleap-bridge/src/main/java/org/reddragon/bridge/Main.java`** (modify) — parse `-copybook-dir` args; build `CobolParserParams` with copybook dirs + extensions; switch to the params overload of `analyzeFile`.
- **`interpreter/cobol/cobol_parser.py`** (modify) — `ProLeapCobolParser` stores `copybook_dirs`; `parse()` appends `-copybook-dir` args and enriches copybook-not-found errors.
- **`interpreter/frontend.py`** (modify) — `get_frontend(...)` gains a `copybook_dirs` param, passed to `ProLeapCobolParser`.
- **`interpreter/run.py`** (modify) — `run(...)` gains a `copybook_dirs` param, threaded to `get_frontend`.
- **`interpreter/project/compiler.py`** (modify) — `compile_module` and `compile_directory` gain `copybook_dirs`; `compile_directory` defaults it to the recursive project tree.
- **`tests/unit/cobol/test_cobol_parser_copybook.py`** (create) — unit tests for the parser command-building and error enrichment.
- **`tests/integration/test_cobol_copybook_inlining.py`** (create) — end-to-end COPY inlining + missing-copybook error against the real rebuilt JAR.

---

## Task 1: Parser stores copybook dirs and builds `-copybook-dir` args

**Files:**
- Modify: `interpreter/cobol/cobol_parser.py`
- Test: `tests/unit/cobol/test_cobol_parser_copybook.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/cobol/test_cobol_parser_copybook.py`:

```python
"""Unit tests for ProLeapCobolParser copybook-dir handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.cobol_parser import ProLeapCobolParser, CobolParseError
from interpreter.cobol.subprocess_runner import SubprocessRunner


class _RecordingRunner(SubprocessRunner):
    """Captures the command; returns a fixed minimal ASG JSON."""

    def __init__(self, stdout: str = '{"program_id": "T"}', raise_exc: Exception | None = None):
        self.command: list[str] | None = None
        self.input_data: str | None = None
        self._stdout = stdout
        self._raise = raise_exc

    def run(self, command: list[str], input_data: str) -> str:
        self.command = command
        self.input_data = input_data
        if self._raise is not None:
            raise self._raise
        return self._stdout


def test_parse_appends_copybook_dir_args():
    runner = _RecordingRunner()
    parser = ProLeapCobolParser(
        runner, "bridge.jar", copybook_dirs=[Path("/a/cpy"), Path("/b/cpy-bms")]
    )
    parser.parse(b"       PROGRAM-ID. T.\n")
    assert runner.command is not None
    assert "-copybook-dir" in runner.command
    # one -copybook-dir per directory, each followed by the path
    idxs = [i for i, a in enumerate(runner.command) if a == "-copybook-dir"]
    assert len(idxs) == 2
    assert runner.command[idxs[0] + 1] == "/a/cpy"
    assert runner.command[idxs[1] + 1] == "/b/cpy-bms"


def test_parse_no_dirs_emits_no_copybook_dir_args():
    runner = _RecordingRunner()
    parser = ProLeapCobolParser(runner, "bridge.jar")
    parser.parse(b"       PROGRAM-ID. T.\n")
    assert runner.command is not None
    assert "-copybook-dir" not in runner.command
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cobol/test_cobol_parser_copybook.py -x -q`
Expected: FAIL — `ProLeapCobolParser.__init__()` got an unexpected keyword argument `copybook_dirs` (and `CobolParseError` import may already resolve).

- [ ] **Step 3: Modify `ProLeapCobolParser`**

In `interpreter/cobol/cobol_parser.py`, update the imports and class. Replace lines 9-16 (imports block) to add `Path`:

```python
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path

from interpreter.cobol.asg_types import CobolASG
from interpreter.cobol.subprocess_runner import SubprocessRunner, CobolParseError
```

Replace the `ProLeapCobolParser` class body (the `__init__` and `parse`) with:

```python
class ProLeapCobolParser(CobolParser):
    """COBOL parser that delegates to the ProLeap bridge via subprocess."""

    def __init__(
        self,
        runner: SubprocessRunner,
        bridge_jar: str,
        copybook_dirs: list[Path] | None = None,
    ):
        self._runner = runner
        self._bridge_jar = bridge_jar
        self._copybook_dirs: list[Path] = list(copybook_dirs or [])

    def parse(self, source: bytes) -> CobolASG:
        logger.info("Parsing COBOL source (%d bytes) via ProLeap bridge", len(source))
        command = ["java", "-jar", self._bridge_jar]
        for d in self._copybook_dirs:
            command += ["-copybook-dir", str(d)]
        try:
            json_str = self._runner.run(command, source.decode("utf-8"))
        except CobolParseError as e:
            raise self._enrich_copybook_error(e)
        data = json.loads(json_str)
        asg = CobolASG.from_dict(data)
        logger.info(
            "Parsed ASG: %d data fields, %d sections, %d paragraphs",
            len(asg.data_fields),
            len(asg.sections),
            len(asg.paragraphs),
        )
        return asg

    def _enrich_copybook_error(self, error: CobolParseError) -> CobolParseError:
        """Turn ProLeap's raw 'Could not find copy book X' into a clean message."""
        msg = str(error)
        if "Could not find copy book" not in msg:
            return error
        match = re.search(r"Could not find copy book (\S+)", msg)
        name = match.group(1) if match else "<unknown>"
        searched = [str(d) for d in self._copybook_dirs] or ["(none configured)"]
        return CobolParseError(
            f"Copybook {name!r} not found. Searched directories: {searched}"
        )
```

Note: `CobolParseError` is defined in `interpreter/cobol/subprocess_runner.py` (confirmed at that module). Import it from there as shown.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cobol/test_cobol_parser_copybook.py -x -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add interpreter/cobol/cobol_parser.py tests/unit/cobol/test_cobol_parser_copybook.py
git commit -m "feat(cobol): ProLeapCobolParser threads copybook dirs to bridge args"
```

---

## Task 2: Parser enriches copybook-not-found errors

**Files:**
- Test: `tests/unit/cobol/test_cobol_parser_copybook.py` (extend)

The implementation already landed in Task 1 (`_enrich_copybook_error`). This task adds the test that proves it.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/cobol/test_cobol_parser_copybook.py`:

```python
def test_missing_copybook_raises_clean_error():
    raw = CobolParseError(
        "ProLeap bridge failed (exit 1): "
        "io.proleap.cobol.preprocessor.exception.CobolPreprocessorException: "
        "Could not find copy book MYBOOK in directory of COBOL input file"
    )
    runner = _RecordingRunner(raise_exc=raw)
    parser = ProLeapCobolParser(runner, "bridge.jar", copybook_dirs=[Path("/x/cpy")])
    with pytest.raises(CobolParseError) as excinfo:
        parser.parse(b"       COPY MYBOOK.\n")
    text = str(excinfo.value)
    assert "MYBOOK" in text
    assert "/x/cpy" in text
    assert "Could not find copy book" not in text  # raw Java message not leaked


def test_non_copybook_error_passes_through():
    raw = CobolParseError("ProLeap bridge failed (exit 1): some other syntax error")
    runner = _RecordingRunner(raise_exc=raw)
    parser = ProLeapCobolParser(runner, "bridge.jar")
    with pytest.raises(CobolParseError) as excinfo:
        parser.parse(b"       PROGRAM-ID. T.\n")
    assert "some other syntax error" in str(excinfo.value)
```

- [ ] **Step 2: Run test to verify it passes (implementation already exists)**

Run: `poetry run python -m pytest tests/unit/cobol/test_cobol_parser_copybook.py -x -q`
Expected: PASS (4 passed total). If the two new tests fail, fix `_enrich_copybook_error` in `cobol_parser.py` until they pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/cobol/test_cobol_parser_copybook.py
git commit -m "test(cobol): copybook-not-found error enrichment"
```

---

## Task 3: Bridge accepts `-copybook-dir` and configures ProLeap params (Java)

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/Main.java`

This is the one change not unit-testable via pytest; it is verified end-to-end by the integration test in Task 6 against the rebuilt JAR.

- [ ] **Step 1: Update imports**

In `Main.java`, the import block currently ends at `java.util.logging.Logger`. Add these imports (alphabetical placement is fine):

```java
import io.proleap.cobol.asg.params.CobolParserParams;
import io.proleap.cobol.asg.params.impl.CobolParserParamsImpl;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
```

- [ ] **Step 2: Collect `-copybook-dir` args in the parse loop**

Find this block in `main`:

```java
        CobolSourceFormatEnum format = CobolSourceFormatEnum.FIXED;
        String filePath = "";

        for (int i = 0; i < args.length; i++) {
            if ("-format".equals(args[i]) && i + 1 < args.length) {
                format = parseFormat(args[i + 1]);
                i++;
            } else {
                filePath = args[i];
            }
        }
```

Replace it with:

```java
        CobolSourceFormatEnum format = CobolSourceFormatEnum.FIXED;
        String filePath = "";
        List<File> copyBookDirs = new ArrayList<>();

        for (int i = 0; i < args.length; i++) {
            if ("-format".equals(args[i]) && i + 1 < args.length) {
                format = parseFormat(args[i + 1]);
                i++;
            } else if ("-copybook-dir".equals(args[i]) && i + 1 < args.length) {
                copyBookDirs.add(new File(args[i + 1]));
                i++;
            } else {
                filePath = args[i];
            }
        }
```

- [ ] **Step 3: Build params and use the params overload**

Find this line in `main`:

```java
            program = new CobolParserRunnerImpl().analyzeFile(cobolFile, format);
```

Replace it with:

```java
            CobolParserParams params = new CobolParserParamsImpl();
            params.setFormat(format);
            params.setCopyBookExtensions(
                Arrays.asList("", "cpy", "CPY", "cob", "cbl", "copy", "COPY"));
            if (!copyBookDirs.isEmpty()) {
                params.setCopyBookDirectories(copyBookDirs);
            }
            program = new CobolParserRunnerImpl().analyzeFile(cobolFile, params);
```

- [ ] **Step 4: Rebuild the JAR**

Run: `cd proleap-bridge && mvn package -q -DskipTests 2>&1 | grep -E "BUILD|ERROR" | head -5`
Expected: no `ERROR` / `BUILD FAILURE` lines (silent or `BUILD SUCCESS`).

- [ ] **Step 5: Manual smoke check**

Run (from repo root):

```bash
JAR=proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
TMP=$(mktemp -d)
printf '       01 WS-X PIC 9(4) VALUE 1234.\n' > "$TMP/MYBOOK.cpy"
printf '       IDENTIFICATION DIVISION.\n       PROGRAM-ID. T.\n       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n       COPY MYBOOK.\n       PROCEDURE DIVISION.\n           STOP RUN.\n' | java -jar "$JAR" -copybook-dir "$TMP" 2>&1 | grep -c WS-X
rm -rf "$TMP"
```

Expected: prints `1` (the copybook field `WS-X` appears in the emitted ASG JSON). Without `-copybook-dir "$TMP"` it would throw `CobolPreprocessorException`.

- [ ] **Step 6: Commit**

```bash
git add proleap-bridge/src/main/java/org/reddragon/bridge/Main.java
git commit -m "feat(bridge): accept -copybook-dir, configure ProLeap copybook resolution"
```

---

## Task 4: `get_frontend` threads `copybook_dirs` to the parser

**Files:**
- Modify: `interpreter/frontend.py`
- Test: `tests/unit/cobol/test_cobol_parser_copybook.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/cobol/test_cobol_parser_copybook.py`:

```python
def test_get_frontend_passes_copybook_dirs(monkeypatch):
    import interpreter.frontend as frontend_mod
    from interpreter.constants import Language

    captured = {}

    class _SpyParser:
        def __init__(self, runner, bridge_jar, copybook_dirs=None):
            captured["copybook_dirs"] = copybook_dirs

    # get_frontend imports ProLeapCobolParser locally at call time, so patching
    # the module attribute is picked up.
    import interpreter.cobol.cobol_parser as cp
    monkeypatch.setattr(cp, "ProLeapCobolParser", _SpyParser)

    frontend_mod.get_frontend(
        Language.COBOL, copybook_dirs=[Path("/proj/cpy")]
    )
    assert captured["copybook_dirs"] == [Path("/proj/cpy")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cobol/test_cobol_parser_copybook.py::test_get_frontend_passes_copybook_dirs -x -q`
Expected: FAIL — `get_frontend()` got an unexpected keyword argument `copybook_dirs`.

- [ ] **Step 3: Add the param to `get_frontend`**

In `interpreter/frontend.py`, change the `get_frontend` signature (currently lines 71-78) to add `copybook_dirs`:

```python
def get_frontend(
    language: Language,
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    llm_provider: str = LLMProvider.CLAUDE,
    llm_client: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    repair_client: Any = _NO_REPAIR_CLIENT,
    copybook_dirs: list[Path] | None = None,
) -> Frontend:
```

Add `from pathlib import Path` to the imports at the top of `interpreter/frontend.py` if not already present (check the existing import block; add it if missing).

In the COBOL branch (currently lines 94-102), change the parser construction:

```python
    if frontend_type == constants.FRONTEND_COBOL:
        import os

        from interpreter.cobol.cobol_frontend import CobolFrontend
        from interpreter.cobol.cobol_parser import ProLeapCobolParser
        from interpreter.cobol.subprocess_runner import RealSubprocessRunner

        bridge_jar = os.environ.get("PROLEAP_BRIDGE_JAR", "proleap-bridge.jar")
        parser = ProLeapCobolParser(
            RealSubprocessRunner(), bridge_jar, copybook_dirs=copybook_dirs
        )
        return CobolFrontend(parser, observer=observer)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cobol/test_cobol_parser_copybook.py::test_get_frontend_passes_copybook_dirs -x -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontend.py tests/unit/cobol/test_cobol_parser_copybook.py
git commit -m "feat(frontend): get_frontend accepts copybook_dirs for COBOL parser"
```

---

## Task 5: Thread `copybook_dirs` through `run()` and `compile_directory`

**Files:**
- Modify: `interpreter/run.py`
- Modify: `interpreter/project/compiler.py`
- Test: `tests/unit/cobol/test_cobol_parser_copybook.py` (extend)

- [ ] **Step 1: Write the failing test for the project-tree default**

Append to `tests/unit/cobol/test_cobol_parser_copybook.py`:

```python
def test_collect_project_copybook_dirs(tmp_path):
    from interpreter.project.compiler import _collect_copybook_dirs

    (tmp_path / "cbl").mkdir()
    (tmp_path / "cpy").mkdir()
    (tmp_path / "cpy-bms").mkdir()
    dirs = _collect_copybook_dirs(tmp_path)
    assert tmp_path in dirs
    assert tmp_path / "cpy" in dirs
    assert tmp_path / "cpy-bms" in dirs
    assert tmp_path / "cbl" in dirs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cobol/test_cobol_parser_copybook.py::test_collect_project_copybook_dirs -x -q`
Expected: FAIL — `cannot import name '_collect_copybook_dirs'`.

- [ ] **Step 3: Add `_collect_copybook_dirs` and thread through the compiler**

In `interpreter/project/compiler.py`, add `from pathlib import Path` if not already imported (it uses `Path` already, so it is). Add this helper near the top-level functions (e.g. just above `compile_module`):

```python
def _collect_copybook_dirs(directory: Path) -> list[Path]:
    """Project root plus every subdirectory, for copybook resolution."""
    directory = directory.resolve()
    subdirs = [p for p in directory.rglob("*") if p.is_dir()]
    return [directory, *subdirs]
```

Update `compile_module` signature (lines 156-161) to accept `copybook_dirs`:

```python
def compile_module(
    file_path: Path,
    language: Language,
    source: bytes | None = None,
    namespace_resolver: NamespaceResolver = NamespaceResolver(),
    copybook_dirs: list[Path] | None = None,
) -> ModuleUnit:
```

Update the `get_frontend` call inside `compile_module` (line 176) to pass it:

```python
    frontend = get_frontend(
        language,
        frontend_type=resolved_frontend_type,
        copybook_dirs=copybook_dirs,
    )
```

In `compile_directory` (starts line 219), after `directory = directory.resolve()` and the `is_dir()` check, compute the dirs once:

```python
    copybook_dirs = _collect_copybook_dirs(directory)
```

Then update the `compile_module(...)` call inside `compile_directory` (the dict comprehension around line 266) to pass them:

```python
    modules = {
        path: compile_module(
            path,
            language,
            namespace_resolver=namespace_resolver,
            copybook_dirs=copybook_dirs,
        )
        for path in source_files
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cobol/test_cobol_parser_copybook.py::test_collect_project_copybook_dirs -x -q`
Expected: PASS

- [ ] **Step 5: Add `copybook_dirs` to `run()`**

In `interpreter/run.py`, add `from pathlib import Path` to imports if missing. Add the param to `run()` (after `io_provider`, lines ~895-905):

```python
def run(
    source: str,
    language: str | Language = Language.PYTHON,
    entry_point: EntryPoint = EntryPoint.top_level(),
    backend: str = LLMProvider.CLAUDE,
    max_steps: int = 100,
    verbose: bool = False,
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    llm_client: Any = None,
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
    io_provider: Any = None,
    copybook_dirs: list[Path] | None = None,
) -> VMState:
```

Update the `get_frontend(...)` call inside `run()` (line 950) to pass it:

```python
    frontend = get_frontend(
        lang,
        frontend_type=resolved_frontend_type,
        llm_provider=backend,
        llm_client=llm_client,
        observer=observer,
        copybook_dirs=copybook_dirs,
    )
```

- [ ] **Step 6: Run the COBOL unit + project tests to confirm no regression**

Run: `poetry run python -m pytest tests/unit/cobol/ tests/unit/project/ -q`
Expected: PASS (existing tests green; default-None `copybook_dirs` changes nothing for them).

- [ ] **Step 7: Commit**

```bash
git add interpreter/run.py interpreter/project/compiler.py tests/unit/cobol/test_cobol_parser_copybook.py
git commit -m "feat(cobol): thread copybook_dirs through run() and compile_directory"
```

---

## Task 6: End-to-end integration — COPY inlining executes; missing copybook errors cleanly

**Files:**
- Create: `tests/integration/test_cobol_copybook_inlining.py`

Requires the rebuilt JAR from Task 3 and `PROLEAP_BRIDGE_JAR` set.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_cobol_copybook_inlining.py`:

```python
"""Integration: COBOL COPY copybook inlining end-to-end via the ProLeap bridge."""

from __future__ import annotations

import os

import pytest

from interpreter.address import Address
from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.project.compiler import compile_directory
from interpreter.project.entry_point import EntryPoint
from interpreter.run import run_linked
from interpreter.var_name import VarName
from interpreter.vm.vm_types import Pointer

_JAR_PATH = os.environ.get(
    "PROLEAP_BRIDGE_JAR",
    os.path.expanduser(
        "~/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
    ),
)
_JAR_AVAILABLE = os.path.isfile(_JAR_PATH)

pytestmark = pytest.mark.skipif(
    not _JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)


def _to_fixed(lines: list[str]) -> str:
    return "\n".join("       " + ln for ln in lines) + "\n"


def _decode_zoned_unsigned(region: bytearray, offset: int, length: int) -> int:
    digits = [region[offset + i] & 0x0F for i in range(length)]
    return sum(d * (10 ** (length - 1 - i)) for i, d in enumerate(digits))


@pytest.fixture(autouse=True)
def _bridge_jar_env():
    old = os.environ.get("PROLEAP_BRIDGE_JAR")
    os.environ["PROLEAP_BRIDGE_JAR"] = _JAR_PATH
    yield
    if old is None:
        os.environ.pop("PROLEAP_BRIDGE_JAR", None)
    else:
        os.environ["PROLEAP_BRIDGE_JAR"] = old


def test_copy_inlined_field_executes(tmp_path):
    """A field declared in a copybook is inlined and usable in PROCEDURE DIVISION."""
    (tmp_path / "VALBOOK.cpy").write_text(
        _to_fixed(["01 WS-FROM-COPY PIC 9(4) VALUE 0."])
    )
    (tmp_path / "MAIN.cbl").write_text(
        _to_fixed(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MAIN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "COPY VALBOOK.",
                "PROCEDURE DIVISION.",
                "    MOVE 4242 TO WS-FROM-COPY.",
                "    STOP RUN.",
            ]
        )
    )

    linked = compile_directory(tmp_path, Language.COBOL)
    vm = run_linked(
        linked,
        entry_point=EntryPoint.function(
            lambda ref: str(ref.label).endswith("func_main_0")
            and "init_params" not in str(ref.label)
        ),
        max_steps=500,
    )

    ptr = None
    for frame in reversed(vm.call_stack):
        if VarName("__prog_MAIN") in frame.local_vars:
            ptr = frame.local_vars[VarName("__prog_MAIN")].value
            break
    assert ptr is not None and isinstance(ptr, Pointer)
    region = vm.region_get(
        Address(vm.heap_get(ptr.base).fields[FieldName("ws_handle")].value)
    )
    assert region is not None
    # WS-FROM-COPY at offset 0 — the MOVE executed against the inlined field
    assert _decode_zoned_unsigned(region, 0, 4) == 4242


def test_missing_copybook_raises_clean_error(tmp_path):
    """An unresolvable COPY surfaces a clean error naming the copybook."""
    from interpreter.cobol.subprocess_runner import CobolParseError

    (tmp_path / "MAIN.cbl").write_text(
        _to_fixed(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MAIN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "COPY NOSUCHBOOK.",
                "PROCEDURE DIVISION.",
                "    STOP RUN.",
            ]
        )
    )

    with pytest.raises(CobolParseError) as excinfo:
        compile_directory(tmp_path, Language.COBOL)
    assert "NOSUCHBOOK" in str(excinfo.value)


def test_multiple_copybooks_inlined(tmp_path):
    """Two separate copybooks both inline; fields from each are usable."""
    (tmp_path / "BOOKA.cpy").write_text(_to_fixed(["01 WS-A PIC 9(4) VALUE 0."]))
    (tmp_path / "BOOKB.cpy").write_text(_to_fixed(["01 WS-B PIC 9(4) VALUE 0."]))
    (tmp_path / "MAIN.cbl").write_text(
        _to_fixed(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MAIN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "COPY BOOKA.",
                "COPY BOOKB.",
                "PROCEDURE DIVISION.",
                "    MOVE 11 TO WS-A.",
                "    MOVE 22 TO WS-B.",
                "    STOP RUN.",
            ]
        )
    )

    linked = compile_directory(tmp_path, Language.COBOL)
    vm = run_linked(
        linked,
        entry_point=EntryPoint.function(
            lambda ref: str(ref.label).endswith("func_main_0")
            and "init_params" not in str(ref.label)
        ),
        max_steps=500,
    )
    ptr = None
    for frame in reversed(vm.call_stack):
        if VarName("__prog_MAIN") in frame.local_vars:
            ptr = frame.local_vars[VarName("__prog_MAIN")].value
            break
    assert ptr is not None and isinstance(ptr, Pointer)
    region = vm.region_get(
        Address(vm.heap_get(ptr.base).fields[FieldName("ws_handle")].value)
    )
    assert region is not None
    # WS-A at offset 0, WS-B at offset 4 (BOOKA then BOOKB, 4 bytes each)
    assert _decode_zoned_unsigned(region, 0, 4) == 11
    assert _decode_zoned_unsigned(region, 4, 4) == 22
```

- [ ] **Step 2: Run test to verify the happy path passes and missing-copybook errors**

Run: `poetry run python -m pytest tests/integration/test_cobol_copybook_inlining.py -x -q`
Expected: PASS (3 passed). If `test_copy_inlined_field_executes` fails with a copybook-not-found error, confirm the JAR was rebuilt (Task 3) and `compile_directory` passes `copybook_dirs`.

- [ ] **Step 3: Verify `COPY … OF library` form (acceptance criterion #2)**

Manually check whether the `COPY name OF library` form resolves with directory-based config. Create a tmp dir with `LIBBOOK.cpy` containing `01 WS-L PIC 9(4) VALUE 0.`, a `MAIN.cbl` using `COPY LIBBOOK OF MYLIB.`, and run `compile_directory` on it:

```bash
poetry run python3 - <<'PY'
import os, tempfile, pathlib
os.environ.setdefault("PROLEAP_BRIDGE_JAR", os.path.expanduser("~/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"))
from interpreter.constants import Language
from interpreter.project.compiler import compile_directory
def fx(l): return "\n".join("       "+x for x in l)+"\n"
with tempfile.TemporaryDirectory() as td:
    p = pathlib.Path(td)
    (p/"LIBBOOK.cpy").write_text(fx(["01 WS-L PIC 9(4) VALUE 0."]))
    (p/"MAIN.cbl").write_text(fx(["IDENTIFICATION DIVISION.","PROGRAM-ID. MAIN.","DATA DIVISION.","WORKING-STORAGE SECTION.","COPY LIBBOOK OF MYLIB.","PROCEDURE DIVISION.","    STOP RUN."]))
    try:
        compile_directory(p, Language.COBOL)
        print("COPY OF library: RESOLVED")
    except Exception as e:
        print("COPY OF library: FAILED ->", type(e).__name__, str(e)[:120])
PY
```

- If it prints `RESOLVED`: add a `test_copy_of_library_inlined` test to the integration file mirroring `test_copy_inlined_field_executes` (using `COPY LIBBOOK OF MYLIB.`), confirm it passes, and include it in the commit.
- If it prints `FAILED`: ProLeap needs a library→directory mapping that directory-config alone doesn't provide. Do **not** expand this task — file a follow-up Beads issue (`bd create "COBOL: COPY ... OF library resolution" -p 2 --labels cobol` referencing red-dragon-9w64) and note the limitation. The plain-`COPY` mechanism (the actual blocker) is unaffected.

- [ ] **Step 4: Run the full COBOL suite for regressions**

Run: `poetry run python -m pytest tests/unit/cobol/ tests/integration/test_cobol_programs.py tests/integration/test_cobol_copybook_inlining.py -q`
Expected: PASS (all green).

- [ ] **Step 5: Format and commit**

```bash
poetry run python -m black tests/integration/test_cobol_copybook_inlining.py
git add tests/integration/test_cobol_copybook_inlining.py
git commit -m "test(cobol): integration — COPY inlining executes; missing copybook errors cleanly"
```

---

## Task 7: Close the issue and run the full suite

- [ ] **Step 1: Full suite**

Run: `poetry run python -m pytest tests/ -q 2>&1 | tail -3`
Expected: all pass, no regressions.

- [ ] **Step 2: Close the Beads issue**

```bash
bd update red-dragon-9w64 --status closed
```

- [ ] **Step 3: Final commit (if the beads export changed)**

```bash
git add -A
git commit -m "chore: close red-dragon-9w64 (COBOL copybook inlining)" || true
```
