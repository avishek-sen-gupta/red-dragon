# USE AFTER ERROR/EXCEPTION Declaratives — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fire a `USE AFTER STANDARD ERROR/EXCEPTION` declarative procedure when an I/O statement on a matching file completes with an error/exception status and the statement has no applicable `AT END`/`INVALID KEY` clause, then continue after the failed I/O.

**Architecture:** Approach A (lowering-time injection), entirely in the COBOL frontend (no core-VM change). The bridge serializes each declarative's `USE` clause; `lower_procedure` builds a USE registry; a shared `emit_use_trigger` helper injects a conditional PERFORM of the matching USE section after each I/O verb. Precedence is automatic — injection only happens when there is no explicit clause.

**Tech Stack:** Python 3.13 + pytest; the ProLeap Java bridge (Maven); COBOL-on-IR lowering.

**Spec:** `docs/superpowers/specs/2026-06-18-use-declaratives-design.md`.

## Global Constraints
- Set `export PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"` before every test run and before each commit.
- Use `poetry run python -m pytest` / `poetry run python -m black` (with the `-m`).
- Commit through the **real** pre-commit hooks (NO `--no-verify`); the hook runs the full suite — export `PROLEAP_BRIDGE_JAR` in the same command and verify the commit landed (`git log --oneline -1`).
- After any Java change, rebuild: `cd proleap-bridge && mvn -DskipTests package -q` (the gitignored JAR is the build product; do not commit it).
- `@covers(...)` on every new test method. Stage specific files in commits — never `git add -A` (a pre-existing untracked plan doc must stay untracked).
- ERROR and EXCEPTION are synonyms (ProLeap does not distinguish them). `USE FOR DEBUGGING` is OUT OF SCOPE (skip it).

---

### Task 1: Bridge — serialize the USE clause

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/AsgSerializer.java` (`serializeDeclaratives`, ~line 267)

**Interfaces:**
- Produces: each declarative section JSON object gains an optional `"use"` object:
  `{"global": bool, "target": "FILE"|"INPUT"|"OUTPUT"|"I-O"|"EXTEND", "files": ["NAME", ...]}` (`files` present only when `target == "FILE"`). Absent when the declarative is `USE FOR DEBUGGING` or has no USE-AFTER clause.

- [ ] **Step 1: Add imports** at the top of `AsgSerializer.java` (near the other declaratives imports):
```java
import io.proleap.cobol.asg.metamodel.procedure.use.AfterOn;
import io.proleap.cobol.asg.metamodel.procedure.use.UseAfterStatement;
import io.proleap.cobol.asg.metamodel.valuestmt.Call;
```
(If `Call` is already imported, skip it.)

- [ ] **Step 2: Emit the `use` object** in `serializeDeclaratives`, right after `secObj.addProperty("name", name);`:
```java
io.proleap.cobol.asg.metamodel.procedure.use.UseStatement us = d.getUseStament();
if (us != null && us.getUseAfterStatement() != null) {
    UseAfterStatement ua = us.getUseAfterStatement();
    AfterOn afterOn = ua.getAfterOn();
    if (afterOn != null && afterOn.getAfterOnType() != null) {
        JsonObject useObj = new JsonObject();
        useObj.addProperty("global", ua.isGlobal());
        AfterOn.AfterOnType t = afterOn.getAfterOnType();
        String target = switch (t) {
            case FILE -> "FILE";
            case INPUT -> "INPUT";
            case OUTPUT -> "OUTPUT";
            case INPUT_OUTPUT -> "I-O";
            case EXTEND -> "EXTEND";
        };
        useObj.addProperty("target", target);
        if (t == AfterOn.AfterOnType.FILE && afterOn.getFileCalls() != null) {
            JsonArray files = new JsonArray();
            for (Call fc : afterOn.getFileCalls()) {
                files.add(extractCallName(fc));   // existing helper used elsewhere in this file
            }
            useObj.add("files", files);
        }
        secObj.add("use", useObj);
    }
}
```
(Confirm `extractCallName(Call)` exists in this file — it is used by other serializers; if the helper name differs, use the existing call-name extractor.)

- [ ] **Step 3: Rebuild + sanity-check the JSON** (no pytest yet — this is verified via the ASG dict in Task 2):
```bash
cd proleap-bridge && mvn -DskipTests package -q && cd ..
export PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
poetry run python -c "
from interpreter.constants import Language, FRONTEND_COBOL
from interpreter.frontend import get_frontend
src=open('proleap-bridge/proleap-cobol-parser/target/test-classes/gov/nist/SQ103A.CBL').read()
fe=get_frontend(Language.COBOL, frontend_type=FRONTEND_COBOL); fe.lower(src.encode())
# Access the raw ASG dict the frontend parsed (find the attribute holding it) and print declaratives' use objects
"
```
Expected: at least one declarative in a USE-using program now carries a `use` object. (If the raw ASG dict isn't easily reachable from the frontend, defer this check to Task 2's test, which asserts the parsed `UseClause`.)

- [ ] **Step 4: Commit**
```bash
export PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
git add proleap-bridge/src/main/java/org/reddragon/bridge/AsgSerializer.java
git commit -m "feat(bridge): serialize USE AFTER ERROR/EXCEPTION clause on declarative sections (red-dragon-m0oa.4)"
```

---

### Task 2: ASG — parse the `use` clause into a `UseClause`

**Files:**
- Modify: `interpreter/cobol/asg_types.py` (`CobolSection`, ~line 178)
- Test: `tests/unit/test_cobol_asg_types.py` (create if absent)

**Interfaces:**
- Produces: `UseClause` frozen dataclass `{is_global: bool, target: str, files: tuple[str, ...]}`; `CobolSection.use: UseClause | None = None`, populated by `CobolSection.from_dict` from the `"use"` key.

- [ ] **Step 1: Write the failing test** (`tests/unit/test_cobol_asg_types.py`):
```python
from interpreter.cobol.asg_types import CobolSection, UseClause
from tests.covers import NotLanguageFeature, covers


class TestUseClauseParsing:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_named_file_use_clause(self):
        sec = CobolSection.from_dict(
            {"name": "RL-FS2-01", "use": {"global": False, "target": "FILE", "files": ["RL-FS2"]}}
        )
        assert sec.use == UseClause(is_global=False, target="FILE", files=("RL-FS2",))

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_no_use_clause_is_none(self):
        assert CobolSection.from_dict({"name": "X"}).use is None

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_open_mode_use_clause(self):
        sec = CobolSection.from_dict({"name": "S", "use": {"global": True, "target": "OUTPUT"}})
        assert sec.use == UseClause(is_global=True, target="OUTPUT", files=())
```

- [ ] **Step 2: Run → fail** (`ImportError: UseClause`):
`poetry run python -m pytest tests/unit/test_cobol_asg_types.py -v`

- [ ] **Step 3: Implement** in `asg_types.py`. Add the dataclass (near `CobolSection`):
```python
@dataclass(frozen=True)
class UseClause:
    """A declarative's USE AFTER ERROR/EXCEPTION targeting."""
    is_global: bool
    target: str  # "FILE" | "INPUT" | "OUTPUT" | "I-O" | "EXTEND"
    files: tuple[str, ...] = ()
```
Add the field + parse to `CobolSection` (the `use` field after `statements`, and in `from_dict`):
```python
    use: UseClause | None = None
```
```python
        use_d = data.get("use")
        return cls(
            name=data["name"],
            paragraphs=[CobolParagraph.from_dict(p) for p in data.get("paragraphs", [])],
            statements=[parse_statement(s) for s in data.get("statements", [])],
            use=(
                UseClause(
                    is_global=bool(use_d.get("global", False)),
                    target=use_d.get("target", "FILE"),
                    files=tuple(f.upper() for f in use_d.get("files", [])),
                )
                if use_d
                else None
            ),
        )
```
(Also round-trip `use` in `to_dict` for completeness: when `self.use`, add `{"global","target","files"}`.)

- [ ] **Step 4: Run → pass.** `poetry run python -m pytest tests/unit/test_cobol_asg_types.py -v`

- [ ] **Step 5: Commit**
```bash
export PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
poetry run python -m black interpreter/cobol/asg_types.py tests/unit/test_cobol_asg_types.py
git add interpreter/cobol/asg_types.py tests/unit/test_cobol_asg_types.py
git commit -m "feat(cobol): parse USE clause into UseClause on declarative sections (red-dragon-m0oa.4)"
```

---

### Task 3: Registry + named-file trigger (the core)

**Files:**
- Modify: `interpreter/cobol/lower_procedure.py` (`lower_procedure_division`, ~line 29)
- Modify: `interpreter/cobol/emit_context.py` (add registry attributes to `EmitContext`)
- Modify: `interpreter/cobol/lower_io.py` (add `emit_use_trigger`; wire into `lower_read`/`lower_write`/`lower_rewrite`/`lower_delete`/`lower_start`/`lower_open`/`lower_close`)
- Test: `tests/integration/test_cobol_use_declaratives.py` (create)

**Interfaces:**
- Consumes: `CobolSection.use` (Task 2); `emit_perform_branch` pattern (`SetContinuation`+`Branch`+return `Label_`); `emit_file_status_update` already called per verb.
- Produces: `EmitContext.use_by_file: dict[str,str]`, `use_by_mode: dict[str,str]`, `use_global: str | None` (values are declarative SECTION NAMES). `emit_use_trigger(ctx, file_name: str, status_reg: Register, has_explicit_clause: bool, materialised) -> None`.

- [ ] **Step 1: Write the failing tests** (`tests/integration/test_cobol_use_declaratives.py`). Use the shared COBOL helpers; observe a WS flag the USE section sets. A WRITE to an INPUT-opened file returns status `48` (red-dragon-m0oa.1) — a clean, deterministic I/O error to trigger the USE.
```python
import pytest
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar, decode_zoned_unsigned as _decode, first_region as _first_region, run_cobol,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce PROLEAP_BRIDGE_JAR."""


def _named_file_program() -> list[str]:
    # USE ON the file; an INPUT-mode WRITE -> status 48 -> USE fires -> sets FLAG=1.
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. USET.",
        "ENVIRONMENT DIVISION.",
        "INPUT-OUTPUT SECTION.",
        "FILE-CONTROL.",
        "    SELECT F1 ASSIGN TO XXXXX001.",
        "DATA DIVISION.",
        "FILE SECTION.",
        "FD  F1.",
        "01  F1-REC PIC X(10).",
        "WORKING-STORAGE SECTION.",
        "01  FLAG PIC 9(1) VALUE 0.",
        "PROCEDURE DIVISION.",
        "DECLARATIVES.",
        "D1 SECTION.",
        "    USE AFTER STANDARD ERROR PROCEDURE ON F1.",
        "D1-P.",
        "    MOVE 1 TO FLAG.",
        "END DECLARATIVES.",
        "MAIN SECTION.",
        "MAIN-P.",
        "    OPEN INPUT F1.",
        '    MOVE "ABC" TO F1-REC.',
        "    WRITE F1-REC.",
        "    CLOSE F1.",
        "    STOP RUN.",
    ]


def _flag(lines, offset=0):
    # FLAG is the only WS field here -> offset 0, length 1.
    vm = run_cobol(lines, max_steps=4000)
    return _decode(_first_region(vm), offset, 1)


class TestUseDeclaratives:
    @covers(CobolFeature.DECLARATIVES)
    def test_named_file_use_fires_on_error(self):
        # NOTE: the INPUT file must exist for OPEN INPUT to succeed; run_cobol's
        # default provider auto-creates SELECT targets, but OPEN INPUT on a
        # missing file is itself an error that should also trigger the USE.
        assert _flag(_named_file_program()) == 1

    @covers(CobolFeature.DECLARATIVES)
    def test_global_use_fires_when_no_named_match(self):
        # USE GLOBAL ... ON F1 still registers under use_global; an I/O error on F1
        # resolves via the global fallback. (Uses the GLOBAL keyword form.)
        lines = _named_file_program()
        i = lines.index("    USE AFTER STANDARD ERROR PROCEDURE ON F1.")
        lines[i] = "    USE GLOBAL AFTER STANDARD ERROR PROCEDURE ON F1."
        assert _flag(lines) == 1

    @covers(CobolFeature.DECLARATIVES)
    def test_no_use_no_change(self):
        # Same program without DECLARATIVES: the I/O error must not crash; FLAG stays 0.
        lines = [l for l in _named_file_program()
                 if l not in ("DECLARATIVES.", "D1 SECTION.",
                              "    USE AFTER STANDARD ERROR PROCEDURE ON F1.",
                              "D1-P.", "    MOVE 1 TO FLAG.", "END DECLARATIVES.")]
        assert _flag(lines) == 0
```
(If `run_cobol`'s provider makes OPEN INPUT on a non-existent file succeed, switch the trigger to a guaranteed error — e.g. `DELETE`/`REWRITE` without a prior successful READ, or assert via the file-status field. Adjust the program so the WRITE/OPEN deterministically returns a non-`0x` status; confirm by reading the file-status field if FLAG doesn't set.)

- [ ] **Step 2: Run → fail** (FLAG stays 0 — USE never fires):
`poetry run python -m pytest tests/integration/test_cobol_use_declaratives.py::TestUseDeclaratives::test_named_file_use_fires_on_error -v`

- [ ] **Step 3: Add registry fields to `EmitContext`** (`emit_context.py`): initialise in `__init__`
```python
        self.use_by_file: dict[str, str] = {}
        self.use_by_mode: dict[str, str] = {}
        self.use_global: str | None = None
```

- [ ] **Step 4: Build the registry** in `lower_procedure_division` (`lower_procedure.py`), after the `section_paragraphs` for declaratives is set:
```python
    for section in asg.declaratives:
        if section.use is None:
            continue
        if section.use.is_global:
            ctx.use_global = section.name
        elif section.use.target == "FILE":
            for fname in section.use.files:
                ctx.use_by_file[fname.upper()] = section.name
        else:  # INPUT / OUTPUT / I-O / EXTEND
            ctx.use_by_mode[section.use.target] = section.name
```

- [ ] **Step 5: Add `emit_use_trigger`** in `lower_io.py` (named-file + GLOBAL resolution; open-mode added in Task 5). Imports needed: `BranchIf`, `Binop`, `Branch`, `Label_`, `SetContinuation`, `ContinuationName`, `resolve_binop`, `CodeLabel`, `Register` (most already imported).
```python
def emit_use_trigger(
    ctx: EmitContext,
    file_name: str,
    status_reg: Register,
    has_explicit_clause: bool,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Inject a conditional PERFORM of the matching USE declarative when an I/O
    verb returns an error/exception status and the statement has no explicit
    AT END / INVALID KEY clause (COBOL precedence)."""
    if has_explicit_clause:
        return
    section = ctx.use_by_file.get(file_name.upper()) or ctx.use_global
    if section is None:
        return
    # err = status first char != "0" (status classes 1..9: AT END/INVALID KEY/
    # permanent/implementor — i.e. anything not 0x successful/info).
    first_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=first_reg,
            func_name=FuncName(BuiltinName.STRING_SLICE),
            args=(Register(str(status_reg)), Register(str(ctx.const_to_reg(0))),
                  Register(str(ctx.const_to_reg(1)))),
        )
    )
    zero_reg = ctx.const_to_reg("0")
    err_reg = ctx.fresh_reg()
    ctx.emit_inst(Binop(result_reg=err_reg, operator=resolve_binop("!="),
                        left=first_reg, right=Register(str(zero_reg))))
    use_lbl = ctx.fresh_label("use_proc")
    skip_lbl = ctx.fresh_label("use_skip")
    ctx.emit_inst(BranchIf(cond_reg=err_reg, branch_targets=(use_lbl, skip_lbl)))
    ctx.emit_inst(Label_(label=use_lbl))
    ret_lbl = ctx.fresh_label("use_return")
    ctx.emit_inst(SetContinuation(
        name=ContinuationName(f"section_{section}_end"), target_label=ret_lbl))
    ctx.emit_inst(Branch(label=CodeLabel(f"section_{section}")))
    ctx.emit_inst(Label_(label=ret_lbl))
    ctx.emit_inst(Branch(label=skip_lbl))
    ctx.emit_inst(Label_(label=skip_lbl))
```
(Confirm `BuiltinName.STRING_SLICE` is the slice builtin used elsewhere in lower_io; if status is stored differently, compare the whole status against the success set instead — but first-char-not-"0" is the rule. If `ctx.const_to_reg` returns a Register, drop the `Register(str(...))` wrappers to match the file's prevailing style.)

- [ ] **Step 6: Wire it into the verbs.** After each verb's `emit_file_status_update(...)`, call `emit_use_trigger`. For READ/WRITE/REWRITE/DELETE/START pass
  `has_explicit_clause = bool(stmt.at_end or stmt.not_at_end or stmt.invalid_key or stmt.not_invalid_key)`;
  for OPEN/CLOSE pass `False`. For `lower_open` (per-file loop) call it inside the loop with that file's name and `status_reg`. Example for `lower_read` (after line 183 / the existing AT END block — place the trigger so it runs when no clause handled the error; simplest: call `emit_use_trigger(ctx, stmt.file_name, status_reg, has_at_end or has_inv_key, materialised)` right after `emit_file_status_update`).

- [ ] **Step 7: Run → pass** the two tests. Then the COBOL regression sweep:
```bash
poetry run python -m pytest tests/integration/test_cobol_use_declaratives.py tests/integration/test_cobol_declaratives.py tests/integration/test_cobol_programs.py tests/integration/test_cobol_read_at_end.py tests/unit/test_condition_lowering.py -q
```
Expected: all pass. If any existing declaratives test changes behavior, reconcile (the trigger must not fire when no USE is registered — `use_by_file`/`use_global` empty → no-op).

- [ ] **Step 8: Commit**
```bash
export PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
poetry run python -m black interpreter/cobol/lower_io.py interpreter/cobol/lower_procedure.py interpreter/cobol/emit_context.py tests/integration/test_cobol_use_declaratives.py
git add interpreter/cobol/lower_io.py interpreter/cobol/lower_procedure.py interpreter/cobol/emit_context.py tests/integration/test_cobol_use_declaratives.py
git commit -m "feat(cobol): fire named-file/GLOBAL USE declaratives on I/O error (red-dragon-m0oa.4)"
```

---

### Task 4: Precedence — explicit AT END/INVALID KEY suppresses USE

**Files:**
- Test: `tests/integration/test_cobol_use_declaratives.py` (add)

**Interfaces:** Consumes Task 3's `emit_use_trigger` (already guards on `has_explicit_clause`).

- [ ] **Step 1: Write the test** (should PASS already if Task 3's `has_explicit_clause` plumbing is correct — this is the guard test):
```python
    @covers(CobolFeature.DECLARATIVES)
    def test_explicit_at_end_suppresses_use(self):
        # READ past EOF with an explicit AT END clause AND a USE on the file:
        # the AT END branch runs (sets FLAG=2), the USE does NOT (would set FLAG=1).
        lines = [
            "IDENTIFICATION DIVISION.","PROGRAM-ID. USEP.","ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.","FILE-CONTROL.","    SELECT F1 ASSIGN TO XXXXX001.",
            "DATA DIVISION.","FILE SECTION.","FD  F1.","01  F1-REC PIC X(10).",
            "WORKING-STORAGE SECTION.","01  FLAG PIC 9(1) VALUE 0.",
            "PROCEDURE DIVISION.","DECLARATIVES.","D1 SECTION.",
            "    USE AFTER STANDARD ERROR PROCEDURE ON F1.","D1-P.","    MOVE 1 TO FLAG.",
            "END DECLARATIVES.","MAIN SECTION.","MAIN-P.",
            "    OPEN OUTPUT F1.","    CLOSE F1.","    OPEN INPUT F1.",
            "    READ F1 AT END MOVE 2 TO FLAG END-READ.","    CLOSE F1.","    STOP RUN.",
        ]
        assert _flag(lines) == 2
```

- [ ] **Step 2: Run.** If it PASSES, the precedence guard works — proceed to commit. If it FAILS (FLAG=1, USE fired despite AT END), fix `emit_use_trigger` wiring so READ passes `has_explicit_clause=True` when `stmt.at_end`/`not_at_end` present.
`poetry run python -m pytest tests/integration/test_cobol_use_declaratives.py::TestUseDeclaratives::test_explicit_at_end_suppresses_use -v`

- [ ] **Step 3: Commit**
```bash
export PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
git add tests/integration/test_cobol_use_declaratives.py
git commit -m "test(cobol): explicit AT END suppresses USE declarative (red-dragon-m0oa.4)"
```

---

### Task 5: Open-mode scoping (`USE … PROCEDURE OUTPUT/INPUT/I-O/EXTEND`)

**Files:**
- Modify: `interpreter/cobol/io_provider.py` (dispatch table + base `_open_mode`; track mode in `RealFileIOProvider`)
- Modify: `interpreter/cobol/real_file_provider.py` (record open mode per file)
- Modify: `interpreter/cobol/lower_io.py` (`emit_use_trigger` open-mode branch)
- Test: `tests/integration/test_cobol_use_declaratives.py` (add)

**Interfaces:**
- Produces: builtin `__cobol_file_open_mode(file) -> str` (`"INPUT"/"OUTPUT"/"I-O"/"EXTEND"` or `""` if closed).

- [ ] **Step 1: Write the failing test:**
```python
    @covers(CobolFeature.DECLARATIVES)
    def test_open_mode_use_fires(self):
        lines = [
            "IDENTIFICATION DIVISION.","PROGRAM-ID. USEM.","ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.","FILE-CONTROL.","    SELECT F1 ASSIGN TO XXXXX001.",
            "DATA DIVISION.","FILE SECTION.","FD  F1.","01  F1-REC PIC X(10).",
            "WORKING-STORAGE SECTION.","01  FLAG PIC 9(1) VALUE 0.",
            "PROCEDURE DIVISION.","DECLARATIVES.","D1 SECTION.",
            "    USE AFTER STANDARD ERROR PROCEDURE INPUT.","D1-P.","    MOVE 1 TO FLAG.",
            "END DECLARATIVES.","MAIN SECTION.","MAIN-P.",
            "    OPEN INPUT F1.","    MOVE \"ABC\" TO F1-REC.","    WRITE F1-REC.",
            "    CLOSE F1.","    STOP RUN.",
        ]
        assert _flag(lines) == 1
```

- [ ] **Step 2: Run → fail** (open-mode USE not yet resolved).

- [ ] **Step 3: Add the builtin + mode tracking.** In `io_provider.py` add to `_COBOL_IO_DISPATCH`:
`FuncName("__cobol_file_open_mode"): "_open_mode",` and a base method:
```python
    def _open_mode(self, filename: Any) -> Any:
        return ""
```
In `RealFileIOProvider` (`real_file_provider.py`): store the mode in `_open_file` (e.g. `self._open_modes[filename.upper()] = mode.upper()`; clear on `_close_file`) and override:
```python
    def _open_mode(self, filename):
        return self._open_modes.get(str(filename).upper(), "")
```
(Read the provider to use its existing per-file state dict / init `self._open_modes = {}` in `__init__`. Normalise "I-O" consistently with how OPEN mode strings arrive.)

- [ ] **Step 4: Extend `emit_use_trigger` with the open-mode branch.** This requires the error-check+PERFORM emission to be a reusable helper. If Task 3 inlined it, first extract it now as `_emit_conditional_use_perform(ctx, status_reg, section)` (the body is exactly the err-slice → `!=` "0" → `BranchIf` → `SetContinuation`/`Branch section_<section>`/return → skip block from Task 3 Step 5). Then make `emit_use_trigger`:
```python
def emit_use_trigger(ctx, file_name, status_reg, has_explicit_clause, materialised):
    if has_explicit_clause:
        return
    section = ctx.use_by_file.get(file_name.upper()) or ctx.use_global
    if section is not None:
        _emit_conditional_use_perform(ctx, status_reg, section)
        return
    if not ctx.use_by_mode:
        return
    # Open-mode scoped: pick the USE section matching this file's CURRENT open mode.
    mode_reg = ctx.fresh_reg()
    ctx.emit_inst(CallFunction(
        result_reg=mode_reg,
        func_name=FuncName("__cobol_file_open_mode"),
        args=(Register(str(ctx.const_to_reg(file_name))),),
    ))
    for mode_key, sec in ctx.use_by_mode.items():
        match_reg = ctx.fresh_reg()
        ctx.emit_inst(Binop(result_reg=match_reg, operator=resolve_binop("=="),
                            left=mode_reg, right=Register(str(ctx.const_to_reg(mode_key)))))
        do_lbl = ctx.fresh_label("use_mode_do")
        next_lbl = ctx.fresh_label("use_mode_next")
        ctx.emit_inst(BranchIf(cond_reg=match_reg, branch_targets=(do_lbl, next_lbl)))
        ctx.emit_inst(Label_(label=do_lbl))
        _emit_conditional_use_perform(ctx, status_reg, sec)
        ctx.emit_inst(Branch(label=next_lbl))
        ctx.emit_inst(Label_(label=next_lbl))
```

- [ ] **Step 5: Run → pass** the open-mode test + the full use-declaratives file + COBOL sweep (Task 3 step 7 command).

- [ ] **Step 6: Commit**
```bash
export PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
poetry run python -m black interpreter/cobol/io_provider.py interpreter/cobol/real_file_provider.py interpreter/cobol/lower_io.py tests/integration/test_cobol_use_declaratives.py
git add interpreter/cobol/io_provider.py interpreter/cobol/real_file_provider.py interpreter/cobol/lower_io.py tests/integration/test_cobol_use_declaratives.py
git commit -m "feat(cobol): open-mode-scoped USE declaratives via __cobol_file_open_mode (red-dragon-m0oa.4)"
```

---

### Task 6: Multi-file USE + verification

**Files:**
- Test: `tests/integration/test_cobol_use_declaratives.py` (add)

**Interfaces:** Consumes Task 3 registry (already loops `section.use.files`).

- [ ] **Step 1: Write the test** (a USE `ON F1 F2` fires for an error on F2 — should pass already since Task 3 registers every file in `files`; this locks it in):
```python
    @covers(CobolFeature.DECLARATIVES)
    def test_multi_file_use_fires_for_second_file(self):
        lines = [
            "IDENTIFICATION DIVISION.","PROGRAM-ID. USEMF.","ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.","FILE-CONTROL.",
            "    SELECT F1 ASSIGN TO XXXXX001.","    SELECT F2 ASSIGN TO XXXXX002.",
            "DATA DIVISION.","FILE SECTION.",
            "FD  F1.","01  F1-REC PIC X(10).","FD  F2.","01  F2-REC PIC X(10).",
            "WORKING-STORAGE SECTION.","01  FLAG PIC 9(1) VALUE 0.",
            "PROCEDURE DIVISION.","DECLARATIVES.","D1 SECTION.",
            "    USE AFTER STANDARD ERROR PROCEDURE ON F1 F2.","D1-P.","    MOVE 1 TO FLAG.",
            "END DECLARATIVES.","MAIN SECTION.","MAIN-P.",
            "    OPEN INPUT F2.","    MOVE \"ABC\" TO F2-REC.","    WRITE F2-REC.",
            "    CLOSE F2.","    STOP RUN.",
        ]
        assert _flag(lines) == 1
```

- [ ] **Step 2: Run → pass** (if it fails, ensure Task 3 registers all `section.use.files`, not just the first).

- [ ] **Step 3: Commit**
```bash
export PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
git add tests/integration/test_cobol_use_declaratives.py
git commit -m "test(cobol): multi-file USE declarative fires for each named file (red-dragon-m0oa.4)"
```

---

### Task 7: Full-suite + NIST verification

- [ ] **Step 1: Full suite** — `export PROLEAP_BRIDGE_JAR=...; poetry run python -m pytest -q -m 'not external and not nist'` → green.
- [ ] **Step 2: NIST re-measure** — `poetry run python -m pytest -m nist -p no:randomly -q | tail -2` and the tracer: `poetry run python scripts/nist_ccvs_tracer.py SQ103A` — confirm SQ103A's `SEQ-TEST-GF-10` "DECLARATIVE NOT EXECUTED" is gone and the "DECLARATIVE NOT EXECUTED" cluster shrinks. Record the new pass count.
- [ ] **Step 3:** Update `red-dragon-m0oa.4` (close) and `red-dragon-m0oa.7` with the conformance delta. File `USE FOR DEBUGGING` as a separate follow-up ticket.
- [ ] **Step 4: Merge** to main via finishing-a-development-branch; push.
