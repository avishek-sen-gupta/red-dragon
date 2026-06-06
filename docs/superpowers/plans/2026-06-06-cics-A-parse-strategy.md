# CICS Sub-project A — Parse Strategy

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make EXEC CICS blocks parse into structured `ExecCicsStatement` nodes, inject EIB copybooks via text pre-pass, and route those nodes to an injectable strategy inside the COBOL lowering pipeline.

**Architecture:** A lightweight text pre-pass (DFHEIBLK injection + DFHRESP substitution) runs before ProLeap. ProLeap emits `{"type": "EXEC_CICS", "exec_cics_text": "..."}` via an updated Java bridge. A Python parser turns the text into `(verb, options)`. An `ExecCicsStrategy` protocol — default `CatchAllLoweringStrategy`, CICS mode injects `CicsLoweringStrategy` — is stored on `EmitContext` and called by `dispatch_statement`.

**Tech Stack:** Python 3.12, Java (StatementSerializer.java), ProLeap bridge JAR, pytest, black

**Beads story:** `red-dragon-pz9g.3`

**Dependencies:** None (this is the foundation)

---

## Files Created / Modified

| Action | Path |
|---|---|
| **Modify** | `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java` |
| **Create** | `interpreter/cics/__init__.py` |
| **Create** | `interpreter/cics/preprocessor.py` |
| **Create** | `interpreter/cics/cics_parser.py` |
| **Create** | `interpreter/cics/strategy.py` |
| **Create** | `interpreter/cics/copybooks/DFHEIBLK.cpy` |
| **Create** | `interpreter/cics/copybooks/DFHAID.cpy` |
| **Create** | `interpreter/cics/copybooks/DFHBMSCA.cpy` |
| **Modify** | `interpreter/cobol/cobol_statements.py` |
| **Modify** | `interpreter/cobol/emit_context.py` |
| **Modify** | `interpreter/cobol/statement_dispatch.py` |
| **Modify** | `interpreter/cobol/cobol_frontend.py` |
| **Modify** | `interpreter/cobol/lower_procedure.py` |
| **Create** | `tests/unit/cics/__init__.py` |
| **Create** | `tests/unit/cics/test_preprocessor.py` |
| **Create** | `tests/unit/cics/test_cics_parser.py` |
| **Create** | `tests/integration/cics/__init__.py` |
| **Create** | `tests/integration/cics/test_parse_strategy.py` |

---

## Task A1: Bridge — Emit exec_cics_text in JSON

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java`

The bridge currently emits `{"type": "EXEC_CICS"}` (via `serializeUnknown`). We need `{"type": "EXEC_CICS", "exec_cics_text": "EXEC CICS RETURN END-EXEC"}`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/cics/test_bridge_exec_cics.py`:

```python
"""Verify the ProLeap bridge emits exec_cics_text for EXEC CICS statements."""
import json
import subprocess
from pathlib import Path

BRIDGE_JAR = "proleap-bridge/target/proleap-bridge.jar"
COPYBOOK_DIR = "interpreter/cics/copybooks"

COBOL_WITH_EXEC_CICS = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTCICS.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-DUMMY PIC X.
       PROCEDURE DIVISION.
           EXEC CICS RETURN END-EXEC.
           STOP RUN.
"""

def test_bridge_emits_exec_cics_text():
    result = subprocess.run(
        ["java", "-jar", BRIDGE_JAR],
        input=COBOL_WITH_EXEC_CICS.decode(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    asg = json.loads(result.stdout)
    stmts = asg.get("statements", [])
    exec_cics = next((s for s in stmts if s.get("type") == "EXEC_CICS"), None)
    assert exec_cics is not None, f"No EXEC_CICS in statements: {stmts}"
    assert "exec_cics_text" in exec_cics, f"Missing exec_cics_text: {exec_cics}"
    assert "RETURN" in exec_cics["exec_cics_text"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run python -m pytest tests/unit/cics/test_bridge_exec_cics.py -v
```

Expected: FAIL — `exec_cics_text` not present (or bridge may not exist yet).

- [ ] **Step 3: Add serializeExecCics to StatementSerializer.java**

In `StatementSerializer.java`, add the import and handler. Insert before the final `return serializeUnknown(stmtType)` line (around line 187):

```java
import io.proleap.cobol.asg.metamodel.procedure.execcics.ExecCicsStatement;
```

Then in the `serialize()` method, add before `return serializeUnknown(stmtType)`:

```java
if (stmtType == StatementTypeEnum.EXEC_CICS) return serializeExecCics((ExecCicsStatement) stmt);
```

Add the method anywhere in the class:

```java
private static JsonObject serializeExecCics(ExecCicsStatement stmt) {
    JsonObject obj = newStatement("EXEC_CICS");
    String text = stmt.getExecCicsText();
    if (text != null) {
        obj.addProperty("exec_cics_text", text);
    }
    return obj;
}
```

- [ ] **Step 4: Rebuild the bridge JAR**

```bash
cd proleap-bridge && mvn package -DskipTests -q && cd ..
```

Expected: `BUILD SUCCESS`

- [ ] **Step 5: Run test to verify it passes**

```bash
poetry run python -m pytest tests/unit/cics/test_bridge_exec_cics.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java \
        proleap-bridge/target/proleap-bridge.jar \
        tests/unit/cics/__init__.py \
        tests/unit/cics/test_bridge_exec_cics.py
git commit -m "$(cat <<'EOF'
feat(cics): bridge emits exec_cics_text for EXEC CICS statements (pz9g.3)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task A2: Pre-pass Text Transformer

**Files:**
- Create: `interpreter/cics/__init__.py`
- Create: `interpreter/cics/preprocessor.py`
- Create: `tests/unit/cics/test_preprocessor.py`

The pre-pass runs before ProLeap. Two responsibilities:
1. Inject `       COPY DFHEIBLK.` on the line immediately after `WORKING-STORAGE SECTION.`
2. Substitute `DFHRESP(NAME)` → numeric literal (per-line regex)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/cics/test_preprocessor.py`:

```python
"""Unit tests for CICS text pre-pass."""
from interpreter.cics.preprocessor import (
    inject_dfheiblk,
    substitute_dfhresp,
    apply_cics_prepass,
)


def test_inject_dfheiblk_inserts_after_ws_section():
    source = (
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-DUMMY PIC X.\n"
    )
    result = inject_dfheiblk(source)
    lines = result.splitlines()
    assert lines[0] == "       WORKING-STORAGE SECTION."
    assert "COPY DFHEIBLK." in lines[1]
    assert "WS-DUMMY" in lines[2]


def test_inject_dfheiblk_no_change_if_no_ws_section():
    source = "       PROCEDURE DIVISION.\n       STOP RUN.\n"
    assert inject_dfheiblk(source) == source


def test_inject_dfheiblk_case_insensitive():
    source = "       working-storage section.\n       01 X PIC X.\n"
    result = inject_dfheiblk(source)
    assert "COPY DFHEIBLK." in result


def test_substitute_dfhresp_normal():
    line = "           IF WS-RESP = DFHRESP(NORMAL)"
    assert substitute_dfhresp(line) == "           IF WS-RESP = 0"


def test_substitute_dfhresp_notfnd():
    line = "           IF WS-RESP = DFHRESP(NOTFND)"
    assert substitute_dfhresp(line) == "           IF WS-RESP = 13"


def test_substitute_dfhresp_endfile():
    line = "           IF WS-RESP = DFHRESP(ENDFILE)"
    assert substitute_dfhresp(line) == "           IF WS-RESP = 20"


def test_substitute_dfhresp_multiple_on_same_line():
    line = "           MOVE DFHRESP(NORMAL) TO A DFHRESP(NOTFND) TO B"
    result = substitute_dfhresp(line)
    assert "DFHRESP" not in result
    assert "0" in result
    assert "13" in result


def test_apply_cics_prepass_combines_both():
    source = (
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-X PIC X.\n"
        "       PROCEDURE DIVISION.\n"
        "           IF X = DFHRESP(NORMAL)\n"
        "               STOP RUN.\n"
    )
    result = apply_cics_prepass(source)
    assert "COPY DFHEIBLK." in result
    assert "DFHRESP" not in result
    assert "0" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/cics/test_preprocessor.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.cics'`

- [ ] **Step 3: Create the package and preprocessor**

Create `interpreter/cics/__init__.py` (empty).

Create `interpreter/cics/preprocessor.py`:

```python
"""CICS text pre-pass — runs before ProLeap parses COBOL source.

Two responsibilities:
1. Inject COPY DFHEIBLK. after WORKING-STORAGE SECTION. (faithful to IBM translator)
2. Substitute DFHRESP(name) with its numeric value
"""

from __future__ import annotations

import re

_DFHRESP_TABLE: dict[str, int] = {
    "NORMAL": 0,
    "NOTFND": 13,
    "ENDFILE": 20,
    "DUPREC": 14,
    "DISABLED": 84,
    "ILLOGIC": 21,
    "IOERR": 17,
    "LENOVF": 27,
    "LENGERR": 22,
    "NOSPACE": 18,
    "NOTOPEN": 19,
    "PGMIDERR": 27,
    "QIDERR": 44,
    "TRANSIDERR": 28,
    "INVREQ": 16,
    "MAPFAIL": 36,
    "UNEXPIN": 35,
    "TERMERR": 81,
    "SESSIONERR": 82,
    "SYSBUSY": 79,
    "SYSIDERR": 53,
    "ISCINVREQ": 54,
}

_WS_SECTION_RE = re.compile(r"^(\s*)WORKING-STORAGE\s+SECTION\s*\.", re.IGNORECASE)
_DFHRESP_RE = re.compile(r"DFHRESP\((\w+)\)", re.IGNORECASE)

_DFHEIBLK_COPY = "       COPY DFHEIBLK."


def inject_dfheiblk(source: str) -> str:
    """Insert COPY DFHEIBLK. on the line immediately after WORKING-STORAGE SECTION."""
    lines = source.splitlines(keepends=True)
    result: list[str] = []
    for line in lines:
        result.append(line)
        if _WS_SECTION_RE.match(line):
            ending = "\n" if not line.endswith("\r\n") else "\r\n"
            result.append(_DFHEIBLK_COPY + ending)
    return "".join(result)


def substitute_dfhresp(source: str) -> str:
    """Replace DFHRESP(name) with its numeric response code."""

    def _replace(m: re.Match) -> str:
        name = m.group(1).upper()
        code = _DFHRESP_TABLE.get(name, 0)
        return str(code)

    return _DFHRESP_RE.sub(_replace, source)


def apply_cics_prepass(source: str) -> str:
    """Apply all CICS pre-pass transformations to COBOL source."""
    source = inject_dfheiblk(source)
    source = substitute_dfhresp(source)
    return source
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/cics/test_preprocessor.py -v
```

Expected: all PASS

- [ ] **Step 5: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cics/__init__.py interpreter/cics/preprocessor.py \
        tests/unit/cics/test_preprocessor.py
git commit -m "$(cat <<'EOF'
feat(cics): CICS text pre-pass (DFHEIBLK injection + DFHRESP substitution) (pz9g.3)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task A3: IBM COBOL Copybooks

**Files:**
- Create: `interpreter/cics/copybooks/DFHEIBLK.cpy`
- Create: `interpreter/cics/copybooks/DFHAID.cpy`
- Create: `interpreter/cics/copybooks/DFHBMSCA.cpy`

These are authored canonical IBM copybooks. Not shipped by carddemo (expected to be pre-installed). The values are IBM-standardized.

- [ ] **Step 1: Create DFHEIBLK.cpy**

Create `interpreter/cics/copybooks/DFHEIBLK.cpy`:

```cobol
      * DFHEIBLK - Execute Interface Block
      * Injected by CICS pre-pass into WORKING-STORAGE SECTION.
       01 DFHEIBLK.
           02 EIBTRNID   PIC X(4).
           02 EIBCALEN   PIC S9(4) COMP.
           02 EIBAID     PIC X(1).
           02 EIBRESP    PIC S9(8) COMP.
           02 EIBRESP2   PIC S9(8) COMP.
           02 EIBDATE    PIC S9(7) COMP-3.
           02 EIBTIME    PIC S9(7) COMP-3.
           02 EIBFN      PIC X(2).
           02 EIBRCODE   PIC X(6).
           02 EIBDS      PIC X(8).
           02 EIBREQID   PIC X(8).
           02 EIBSIG     PIC X(1).
           02 EIBFREE    PIC X(1).
           02 EIBRECV    PIC X(1).
           02 EIBATT     PIC X(1).
           02 EIBEOC     PIC X(1).
           02 EIBFMH     PIC X(1).
           02 EIBCOMPL   PIC X(1).
           02 EIBSYNC    PIC X(1).
           02 EIBSYNCRB  PIC X(1).
           02 EIBNODAT   PIC X(1).
           02 EIBRSRCE   PIC X(8).
           02 EIBSYSID   PIC X(4).
           02 EIBUSER    PIC X(8).
           02 EIBTERM    PIC X(4).
           02 EIBLINK    PIC X(4).
```

- [ ] **Step 2: Create DFHAID.cpy**

Standard IBM EBCDIC AID values. Programs compare EIBAID against these.

Create `interpreter/cics/copybooks/DFHAID.cpy`:

```cobol
      * DFHAID - Attention Identifier Constants
       01 DFHAID.
           02 DFHNULL    PIC X VALUE X'00'.
           02 DFHENTER   PIC X VALUE X'7D'.
           02 DFHCLEAR   PIC X VALUE X'6D'.
           02 DFHPA1     PIC X VALUE X'6C'.
           02 DFHPA2     PIC X VALUE X'6E'.
           02 DFHPA3     PIC X VALUE X'6B'.
           02 DFHPF1     PIC X VALUE X'F1'.
           02 DFHPF2     PIC X VALUE X'F2'.
           02 DFHPF3     PIC X VALUE X'F3'.
           02 DFHPF4     PIC X VALUE X'F4'.
           02 DFHPF5     PIC X VALUE X'F5'.
           02 DFHPF6     PIC X VALUE X'F6'.
           02 DFHPF7     PIC X VALUE X'F7'.
           02 DFHPF8     PIC X VALUE X'F8'.
           02 DFHPF9     PIC X VALUE X'F9'.
           02 DFHPF10    PIC X VALUE X'7A'.
           02 DFHPF11    PIC X VALUE X'7B'.
           02 DFHPF12    PIC X VALUE X'7C'.
           02 DFHPF13    PIC X VALUE X'C1'.
           02 DFHPF14    PIC X VALUE X'C2'.
           02 DFHPF15    PIC X VALUE X'C3'.
           02 DFHPF16    PIC X VALUE X'C4'.
           02 DFHPF17    PIC X VALUE X'C5'.
           02 DFHPF18    PIC X VALUE X'C6'.
           02 DFHPF19    PIC X VALUE X'C7'.
           02 DFHPF20    PIC X VALUE X'C8'.
           02 DFHPF21    PIC X VALUE X'C9'.
           02 DFHPF22    PIC X VALUE X'4A'.
           02 DFHPF23    PIC X VALUE X'4B'.
           02 DFHPF24    PIC X VALUE X'4C'.
```

- [ ] **Step 3: Create DFHBMSCA.cpy**

Attribute byte and color constants used by carddemo programs.

Create `interpreter/cics/copybooks/DFHBMSCA.cpy`:

```cobol
      * DFHBMSCA - BMS Attribute and Color Constants
      * Field attribute bytes
       01 DFHBMSCA.
           02 DFHBMPEM   PIC X VALUE X'00'.
           02 DFHBMPRO   PIC X VALUE X'F0'.
           02 DFHBMPRF   PIC X VALUE X'F8'.
           02 DFHBMASB   PIC X VALUE X'C0'.
           02 DFHBMASK   PIC X VALUE X'04'.
           02 DFHBMFSE   PIC X VALUE X'C0'.
           02 DFHBMDAR   PIC X VALUE X'0C'.
           02 DFHBMBRY   PIC X VALUE X'08'.
      * Color values (for extended attributes)
           02 DFHDFCOL   PIC X VALUE X'00'.
           02 DFHBLUE    PIC X VALUE X'01'.
           02 DFHRED     PIC X VALUE X'02'.
           02 DFHPINK    PIC X VALUE X'03'.
           02 DFHGREEN   PIC X VALUE X'04'.
           02 DFHTURQ    PIC X VALUE X'05'.
           02 DFHYELLO   PIC X VALUE X'06'.
           02 DFHNEUTR   PIC X VALUE X'07'.
```

- [ ] **Step 4: Verify copybooks parse via integration**

Write a quick smoke test that parses a COBOL program using `COPY DFHAID`:

Create `tests/integration/cics/test_parse_strategy.py` (first test only for now):

```python
"""Integration tests for CICS parse strategy (Sub-project A)."""
import pytest
from pathlib import Path
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.subprocess_runner import SubprocessRunner

BRIDGE_JAR = "proleap-bridge/target/proleap-bridge.jar"
COPYBOOK_DIR = Path("interpreter/cics/copybooks")


@pytest.fixture
def parser():
    runner = SubprocessRunner()
    return ProLeapCobolParser(
        runner=runner,
        bridge_jar=BRIDGE_JAR,
        copybook_dirs=[COPYBOOK_DIR],
    )


COBOL_COPY_DFHAID = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTAID.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY DFHAID.
       PROCEDURE DIVISION.
           IF EIBAID = DFHENTER
               STOP RUN
           END-IF.
           STOP RUN.
"""


def test_dfhaid_copybook_resolves(parser):
    asg = parser.parse(COBOL_COPY_DFHAID)
    field_names = {f.name for f in asg.data_fields}
    assert "DFHENTER" in field_names
    assert "DFHPF3" in field_names
```

```bash
poetry run python -m pytest tests/integration/cics/test_parse_strategy.py::test_dfhaid_copybook_resolves -v
```

Expected: PASS (copybooks resolve via ProLeap)

- [ ] **Step 5: Commit**

```bash
git add interpreter/cics/copybooks/ tests/integration/cics/__init__.py \
        tests/integration/cics/test_parse_strategy.py
git commit -m "$(cat <<'EOF'
feat(cics): author DFHEIBLK.cpy, DFHAID.cpy, DFHBMSCA.cpy copybooks (pz9g.1)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task A4: ExecCicsStatement Python Type + CICS Verb Parser

**Files:**
- Create: `interpreter/cics/cics_parser.py`
- Modify: `interpreter/cobol/cobol_statements.py`
- Create: `tests/unit/cics/test_cics_parser.py`

The Python `ExecCicsStatement` type goes into `cobol_statements.py` alongside the other statement types. The CICS verb parser (text → verb + options) lives in `interpreter/cics/cics_parser.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/cics/test_cics_parser.py`:

```python
"""Unit tests for CICS verb/options text parser."""
from interpreter.cics.cics_parser import parse_exec_cics_text


def test_parse_return():
    verb, opts = parse_exec_cics_text("EXEC CICS RETURN END-EXEC")
    assert verb == "RETURN"
    assert opts == {}


def test_parse_return_transid():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS RETURN TRANSID(CC00) COMMAREA(WS-CA) LENGTH(16) END-EXEC"
    )
    assert verb == "RETURN"
    assert opts["TRANSID"] == "CC00"
    assert opts["COMMAREA"] == "WS-CA"
    assert opts["LENGTH"] == "16"


def test_parse_send_map():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS SEND MAP('COSGN0A') MAPSET('COSGN00') FROM(COSGN0AO) ERASE END-EXEC"
    )
    assert verb == "SEND MAP"
    assert opts["MAP"] == "COSGN0A"
    assert opts["MAPSET"] == "COSGN00"
    assert opts["FROM"] == "COSGN0AO"
    assert opts["ERASE"] is None


def test_parse_receive_map():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS RECEIVE MAP('COSGN0A') MAPSET('COSGN00') INTO(COSGN0AI) END-EXEC"
    )
    assert verb == "RECEIVE MAP"
    assert opts["MAP"] == "COSGN0A"
    assert opts["INTO"] == "COSGN0AI"


def test_parse_send_text():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS SEND TEXT FROM(WS-MSG) LENGTH(80) END-EXEC"
    )
    assert verb == "SEND TEXT"
    assert opts["FROM"] == "WS-MSG"
    assert opts["LENGTH"] == "80"


def test_parse_read_file():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS READ FILE('ACCTDAT') INTO(WS-REC) RIDFLD(WS-KEY) "
        "KEYLENGTH(16) RESP(WS-RESP) END-EXEC"
    )
    assert verb == "READ"
    assert opts["FILE"] == "ACCTDAT"
    assert opts["INTO"] == "WS-REC"
    assert opts["RIDFLD"] == "WS-KEY"
    assert opts["RESP"] == "WS-RESP"


def test_parse_xctl():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS XCTL PROGRAM(CDEMO-TO-PGM) COMMAREA(WS-CA) END-EXEC"
    )
    assert verb == "XCTL"
    assert opts["PROGRAM"] == "CDEMO-TO-PGM"


def test_parse_startbr():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS STARTBR FILE('CARDDAT') RIDFLD(WS-KEY) KEYLENGTH(16) RESP(WS-RESP) END-EXEC"
    )
    assert verb == "STARTBR"
    assert opts["FILE"] == "CARDDAT"


def test_parse_abend():
    verb, opts = parse_exec_cics_text("EXEC CICS ABEND ABCODE('CICS') END-EXEC")
    assert verb == "ABEND"
    assert opts["ABCODE"] == "CICS"


def test_parse_handle_abend():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS HANDLE ABEND LABEL(ABEND-HANDLER) END-EXEC"
    )
    assert verb == "HANDLE ABEND"
    assert opts["LABEL"] == "ABEND-HANDLER"


def test_parse_assign():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS ASSIGN APPLID(WS-APPL) SYSID(WS-SYS) END-EXEC"
    )
    assert verb == "ASSIGN"
    assert opts["APPLID"] == "WS-APPL"
    assert opts["SYSID"] == "WS-SYS"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/cics/test_cics_parser.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.cics.cics_parser'`

- [ ] **Step 3: Implement the CICS verb parser**

Create `interpreter/cics/cics_parser.py`:

```python
"""Parse EXEC CICS text into (verb, options) for ExecCicsStatement."""

from __future__ import annotations

import re

# Compound verbs: "SEND MAP", "SEND TEXT", "RECEIVE MAP", "HANDLE ABEND", "HANDLE CONDITION"
_COMPOUND_FIRST = {"SEND", "RECEIVE", "HANDLE"}
_COMPOUND_SECOND: dict[str, set[str]] = {
    "SEND": {"MAP", "TEXT"},
    "RECEIVE": {"MAP"},
    "HANDLE": {"ABEND", "CONDITION", "AID"},
}

_EXEC_CICS_PREFIX = re.compile(r"^\s*EXEC\s+CICS\s+", re.IGNORECASE)
_END_EXEC_SUFFIX = re.compile(r"\s*END-EXEC\s*$", re.IGNORECASE)
_OPTION_RE = re.compile(r"([A-Z][A-Z0-9-]*)(?:\(([^)]*)\))?", re.IGNORECASE)


def parse_exec_cics_text(text: str) -> tuple[str, dict[str, str | None]]:
    """Parse 'EXEC CICS VERB OPT1(val) FLAG END-EXEC' → (verb, {OPT1: val, FLAG: None})."""
    body = _EXEC_CICS_PREFIX.sub("", text.strip())
    body = _END_EXEC_SUFFIX.sub("", body).strip()

    if not body:
        return "", {}

    words = body.split()
    first = words[0].upper()

    # Check for compound verb (e.g. "SEND MAP", "HANDLE ABEND")
    if first in _COMPOUND_FIRST and len(words) >= 2:
        # Second word may be "MAP" or "MAP('name')" — extract prefix before '('
        second_prefix = words[1].split("(")[0].upper()
        if second_prefix in _COMPOUND_SECOND.get(first, set()):
            verb = f"{first} {second_prefix}"
            # Options start from where second word begins (includes its value if any)
            options_body = body[len(words[0]) :].strip()
            return verb, _parse_options(options_body)

    verb = first
    options_body = body[len(words[0]) :].strip()
    return verb, _parse_options(options_body)


def _parse_options(text: str) -> dict[str, str | None]:
    options: dict[str, str | None] = {}
    for m in _OPTION_RE.finditer(text):
        key = m.group(1).upper()
        val = m.group(2)
        if val is not None:
            val = val.strip().strip("'\"")
        options[key] = val
    return options
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/cics/test_cics_parser.py -v
```

Expected: all PASS

- [ ] **Step 5: Add ExecCicsStatement to cobol_statements.py**

In `interpreter/cobol/cobol_statements.py`, add the import at the top:

```python
from interpreter.cics.cics_parser import parse_exec_cics_text
```

Add to the `CobolStatementType` union (at the end, before the closing `]`):

```python
    "ExecCicsStatement",
```

Add the class after `DeleteStatement`:

```python
@dataclass(frozen=True)
class ExecCicsStatement:
    """EXEC CICS verb-with-options block."""

    verb: str
    options: dict[str, str | None]

    @classmethod
    def from_dict(cls, data: dict) -> "ExecCicsStatement":
        text = data.get("exec_cics_text", "")
        verb, options = parse_exec_cics_text(text)
        return cls(verb=verb, options=options)

    def to_dict(self) -> dict:
        return {"type": "EXEC_CICS", "verb": self.verb, "options": dict(self.options)}
```

Add to `_DISPATCH_TABLE`:

```python
    "EXEC_CICS": ExecCicsStatement,
```

- [ ] **Step 6: Run the full test suite to verify nothing broke**

```bash
poetry run python -m pytest tests/unit/cobol/ -v -x
```

Expected: all existing COBOL tests PASS (no regressions).

- [ ] **Step 7: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cics/cics_parser.py interpreter/cobol/cobol_statements.py \
        tests/unit/cics/test_cics_parser.py
git commit -m "$(cat <<'EOF'
feat(cics): ExecCicsStatement type + CICS verb parser (pz9g.3)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task A5: ExecCicsStrategy Protocol + EmitContext Injection + Dispatch Hook

**Files:**
- Create: `interpreter/cics/strategy.py`
- Modify: `interpreter/cobol/emit_context.py`
- Modify: `interpreter/cobol/statement_dispatch.py`
- Modify: `interpreter/cobol/cobol_frontend.py`
- Modify: `interpreter/cobol/lower_procedure.py`

This is the main wiring task. Three changes:
1. `ExecCicsStrategy` protocol with `CatchAllLoweringStrategy` null-object
2. `EmitContext` gets `exec_cics_strategy` field
3. `dispatch_statement` routes `ExecCicsStatement` → `ctx.exec_cics_strategy.lower()`
4. `lower_procedure_division` calls `ctx.exec_cics_strategy.on_procedure_entry()` at start
5. `CobolFrontend.__init__` accepts optional `exec_cics_strategy` (default: `CatchAllLoweringStrategy`)

- [ ] **Step 1: Write the failing integration test**

Add to `tests/integration/cics/test_parse_strategy.py`:

```python
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cics.strategy import CatchAllLoweringStrategy


COBOL_WITH_EXEC_CICS = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTCICS.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-DUMMY PIC X.
       PROCEDURE DIVISION.
           EXEC CICS RETURN END-EXEC.
           STOP RUN.
"""


def test_catchall_strategy_does_not_raise(parser):
    """COBOL with EXEC CICS compiles without error using CatchAllLoweringStrategy."""
    from interpreter.cics.preprocessor import apply_cics_prepass

    source = apply_cics_prepass(COBOL_WITH_EXEC_CICS.decode()).encode()
    frontend = CobolFrontend(
        cobol_parser=parser,
        exec_cics_strategy=CatchAllLoweringStrategy(),
    )
    instructions = frontend.lower(source)
    assert len(instructions) > 0  # produced some IR without raising
```

```bash
poetry run python -m pytest tests/integration/cics/test_parse_strategy.py::test_catchall_strategy_does_not_raise -v
```

Expected: FAIL — `CatchAllLoweringStrategy` doesn't exist yet / `CobolFrontend` doesn't accept `exec_cics_strategy`.

- [ ] **Step 2: Create strategy.py**

Create `interpreter/cics/strategy.py`:

```python
"""ExecCicsStrategy protocol and null-object implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from interpreter.cobol.emit_context import EmitContext
    from interpreter.cobol.cobol_statements import ExecCicsStatement
    from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout

logger = logging.getLogger(__name__)


class ExecCicsStrategy(Protocol):
    """Injectable strategy for lowering EXEC CICS statements to IR."""

    def on_procedure_entry(
        self,
        ctx: "EmitContext",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        """Called once at the start of the procedure division. Use to emit EIB init."""
        ...

    def lower(
        self,
        ctx: "EmitContext",
        stmt: "ExecCicsStatement",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        """Lower one EXEC CICS statement to IR."""
        ...


class CatchAllLoweringStrategy:
    """Default no-op strategy. Logs a warning for every EXEC CICS statement."""

    def on_procedure_entry(
        self,
        ctx: "EmitContext",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        pass

    def lower(
        self,
        ctx: "EmitContext",
        stmt: "ExecCicsStatement",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        logger.warning(
            "EXEC CICS %s ignored (no CICS strategy injected)", stmt.verb
        )
```

- [ ] **Step 3: Add exec_cics_strategy to EmitContext**

In `interpreter/cobol/emit_context.py`, add the import near the top:

```python
from interpreter.cics.strategy import ExecCicsStrategy, CatchAllLoweringStrategy
```

In `EmitContext.__init__`, add parameter and assignment:

```python
def __init__(
    self,
    dispatch_fn: DispatchFn,
    observer: FrontendObserver | None = None,
    condition_index: ConditionNameIndex = ConditionNameIndex({}),
    exec_cics_strategy: ExecCicsStrategy = CatchAllLoweringStrategy(),  # type: ignore[assignment]
) -> None:
    self._dispatch_fn = dispatch_fn
    self._observer = observer
    self._condition_index = condition_index
    self._exec_cics_strategy = exec_cics_strategy
    ...
```

Add a property:

```python
@property
def exec_cics_strategy(self) -> ExecCicsStrategy:
    return self._exec_cics_strategy
```

- [ ] **Step 4: Add ExecCicsStatement branch to dispatch_statement**

In `interpreter/cobol/statement_dispatch.py`, add import:

```python
from interpreter.cobol.cobol_statements import (
    ...
    ExecCicsStatement,
)
```

Add at the end of `dispatch_statement`, before the `else` fallthrough:

```python
    elif isinstance(stmt, ExecCicsStatement):
        ctx.exec_cics_strategy.lower(ctx, stmt, materialised)
```

- [ ] **Step 5: Add on_procedure_entry call to lower_procedure_division**

In `interpreter/cobol/lower_procedure.py`, at the start of `lower_procedure_division`, before the loop over `asg.statements`:

```python
def lower_procedure_division(
    ctx: EmitContext,
    asg: CobolASG,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Lower division-level bare statements, standalone paragraphs, and sections."""
    ctx.exec_cics_strategy.on_procedure_entry(ctx, materialised)  # CICS EIB init hook
    for stmt in asg.statements:
        ctx.lower_statement(stmt, materialised)
    ...
```

- [ ] **Step 6: Add exec_cics_strategy param to CobolFrontend**

In `interpreter/cobol/cobol_frontend.py`, update `__init__`:

```python
from interpreter.cics.strategy import ExecCicsStrategy, CatchAllLoweringStrategy

class CobolFrontend(Frontend):
    def __init__(
        self,
        cobol_parser: CobolParser,
        observer: FrontendObserver = NullFrontendObserver(),
        exec_cics_strategy: ExecCicsStrategy = CatchAllLoweringStrategy(),  # type: ignore[assignment]
    ):
        self._parser = cobol_parser
        self._observer = observer
        self._exec_cics_strategy = exec_cics_strategy
        self._layout = DataLayout()
        self._ctx = EmitContext(
            dispatch_fn=dispatch_statement,
            observer=observer,
            exec_cics_strategy=exec_cics_strategy,
        )
```

Also update the `lower()` method where `EmitContext` is recreated:

```python
self._ctx = EmitContext(
    dispatch_fn=dispatch_statement,
    observer=self._observer,
    condition_index=condition_index,
    exec_cics_strategy=self._exec_cics_strategy,
)
```

- [ ] **Step 7: Run the integration test**

```bash
poetry run python -m pytest tests/integration/cics/test_parse_strategy.py -v
```

Expected: all PASS

- [ ] **Step 8: Run the full suite to check for regressions**

```bash
poetry run python -m pytest -x -q
```

Expected: all existing tests PASS

- [ ] **Step 9: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cics/strategy.py \
        interpreter/cobol/emit_context.py \
        interpreter/cobol/statement_dispatch.py \
        interpreter/cobol/cobol_frontend.py \
        interpreter/cobol/lower_procedure.py \
        tests/integration/cics/test_parse_strategy.py
git commit -m "$(cat <<'EOF'
feat(cics): ExecCicsStrategy protocol + EmitContext injection + dispatch hook (pz9g.3)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Sub-project A Complete

At this point:
- The bridge emits `exec_cics_text` for every EXEC CICS block
- Pre-pass injects DFHEIBLK and substitutes DFHRESP before ProLeap sees the source
- IBM copybooks are authored and on the ProLeap search path
- `ExecCicsStatement(verb, options)` is a first-class statement type
- `dispatch_statement` routes EXEC CICS to the injected strategy
- `CatchAllLoweringStrategy` (default) logs a warning and produces no IR — no COBOL program crashes on EXEC CICS anymore
- `CobolFrontend` accepts `exec_cics_strategy=` for CICS mode

**Next:** [Sub-project B — CICS Runtime / EIB](2026-06-06-cics-B-runtime-eib.md)

Run the full story marker:

```bash
bd set-state red-dragon-pz9g.3 in_progress
```
