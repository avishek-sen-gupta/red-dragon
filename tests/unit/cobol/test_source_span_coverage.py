"""Every COBOL instruction must be traceable to the source line it came from.

The silent failure mode this guards: a lowering path that emits without a
span does not error — it produces an instruction the TUI cannot highlight,
a diagnostic that cannot name a line, and a memory effect recorded against
``<unknown>``. That is invisible until someone goes looking, which is
exactly how COBOL IR ended up with 0 of 313 instructions located.
"""

import ast
from pathlib import Path

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend
from tests.covers import NotLanguageFeature, covers

REPO_ROOT = Path(__file__).resolve().parents[3]
LOWERING_DIR = REPO_ROOT / "interpreter" / "cobol"

EMITTERS = {"emit_inst", "const_to_reg", "resolve_field_ref"}

# An explicit list, not a lower_*.py glob. condition_lowering.py holds 69
# emitting calls and does not match that glob, so a glob would silently
# exempt an entire threaded module -- the same class of silent hole this
# whole invariant exists to close.
#
# cobol_frontend.py is deliberately absent: its emitting calls assemble the
# program itself rather than lower any COBOL construct, and _lower_asg is
# already named in SPANLESS_FUNCTIONS.
THREADED_MODULES = (
    "lower_arithmetic.py",
    "lower_io.py",
    "lower_string_inspect.py",
    "condition_lowering.py",
    "lower_perform.py",
    "lower_search.py",
    "lower_call.py",
    "lower_procedure.py",
    "lower_data_division.py",
    "lower_program_init.py",
    "emit_context.py",
)

# Functions that emit the program prologue and singleton plumbing. These
# correspond to no COBOL line, so they pass no span and their instructions
# stay <unknown>. That is the correct answer, not a gap.
SPANLESS_FUNCTIONS = {
    "lower_program_init",
    "lower_ws_from_singleton",
    "_lower_asg",
    # Region binding plumbing: LoadVar of __ws_region / __params_region / the
    # program singleton. Describes whole regions, not any source declaration.
    "lower_sectioned_data_division",
}


def _unthreaded_calls() -> list[str]:
    offenders: list[str] = []
    for name in THREADED_MODULES:
        path = LOWERING_DIR / name
        tree = ast.parse(path.read_text())
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef):
                continue
            if func.name in SPANLESS_FUNCTIONS:
                continue
            for node in ast.walk(func):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in EMITTERS
                    and not any(k.arg == "span" for k in node.keywords)
                ):
                    offenders.append(
                        f"{path.name}:{node.lineno} in {func.name}(): "
                        f".{node.func.attr}() has no span="
                    )
    return offenders


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_lowering_emit_passes_a_span():
    offenders = _unthreaded_calls()
    assert offenders == [], (
        "Emitting calls with no span= produce IR that cannot be traced to "
        "COBOL source:\n  " + "\n  ".join(offenders)
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_lint_can_actually_see_emitting_calls():
    """Guards against the invariant passing vacuously.

    If EMITTERS or the glob ever stops matching reality, the lint above
    passes by finding nothing at all. This asserts it is still looking at
    a real, populated set of call sites.
    """
    total = 0
    for name in THREADED_MODULES:
        path = LOWERING_DIR / name
        assert path.exists(), f"THREADED_MODULES names a missing file: {name}"
        tree = ast.parse(path.read_text())
        total += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in EMITTERS
        )
    assert total > 200, f"expected the lowering modules to emit; saw {total}"


def _span_accepting_functions() -> set[str]:
    """Names of every function in the threaded modules that takes `span`."""
    names: set[str] = set()
    for name in THREADED_MODULES:
        tree = ast.parse((LOWERING_DIR / name).read_text())
        for func in ast.walk(tree):
            if isinstance(func, ast.FunctionDef) and any(
                a.arg == "span" for a in func.args.args + func.args.kwonlyargs
            ):
                names.add(func.name)
    return names


def _callee_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    """Map every ``from ... import x as y`` alias to the real name ``x``.

    ``_span_accepting_functions()`` indexes by the name a function is
    *defined* with. A call site written through an aliased import uses a
    different name, e.g. ``emit_context.py`` does::

        from interpreter.cobol.condition_lowering import (
            lower_condition as _lower_condition,
        )
        return _lower_condition(..., span=span)

    ``_lower_condition`` never matches the accepting set's ``lower_condition``
    entry, so the call is invisible to the lint below -- it could drop
    ``span=`` and nothing would notice. Imports in this codebase are
    frequently function-local (to dodge circular imports), so this walks the
    whole tree rather than only module-level statements.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
    return aliases


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_call_to_a_span_accepting_function_passes_a_span():
    accepting = _span_accepting_functions()
    offenders: list[str] = []
    for name in THREADED_MODULES:
        path = LOWERING_DIR / name
        tree = ast.parse(path.read_text())
        aliases = _import_aliases(tree)
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef) or func.name in SPANLESS_FUNCTIONS:
                continue
            for node in ast.walk(func):
                if not isinstance(node, ast.Call):
                    continue
                callee = _callee_name(node)
                resolved = aliases.get(callee, callee) if callee else callee
                if resolved in accepting and not any(
                    k.arg == "span" for k in node.keywords
                ):
                    offenders.append(
                        f"{path.name}:{node.lineno} in {func.name}(): "
                        f"{callee}() accepts span but is called without it"
                    )
    assert offenders == [], "Span dropped across a call:\n  " + "\n  ".join(offenders)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_import_alias_resolution_maps_aliased_calls_to_their_real_name():
    """Guards the alias resolver itself.

    emit_context.py's EmitContext.lower_condition imports the real
    lower_condition under the local alias _lower_condition and calls it
    under that alias. If _import_aliases ever stopped mapping
    _lower_condition -> lower_condition, the lint above would silently stop
    checking that call site again -- exactly the hole this fix closes.
    """
    path = LOWERING_DIR / "emit_context.py"
    tree = ast.parse(path.read_text())
    aliases = _import_aliases(tree)
    assert aliases.get("_lower_condition") == "lower_condition"
    accepting = _span_accepting_functions()
    assert aliases["_lower_condition"] in accepting


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_span_accepting_function_set_is_populated():
    """Guards the lint above against passing vacuously."""
    accepting = _span_accepting_functions()
    assert {
        "emit_inst",
        "const_to_reg",
        "resolve_field_ref",
        "lower_expr_node",
    } <= accepting


# Distinct from test_source_span.py's PROBE_SOURCE: this one declares
# WS-A as well, so the MOVE lands on line 8 rather than line 7.
ARITH_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(4) VALUE 5.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           MOVE 7 TO WS-B.
           ADD WS-A TO WS-B.
           DISPLAY WS-B.
           STOP RUN.
"""


def _probe_ir():
    parser = make_cobol_parser()
    return CobolFrontend(parser).lower(ARITH_SOURCE)


# The exact opcode sequence lower_ws_from_singleton + lower_sectioned_data_division
# emit before any PROCEDURE DIVISION statement, for a program with no LINKAGE,
# LOCAL-STORAGE, FILE, or INDEXED-BY items (both ARITH_SOURCE and
# SUBSCRIPT_SOURCE qualify: SUBSCRIPT_SOURCE's OCCURS table has no INDEXED BY,
# so it allocates no INDEXES region and produces the identical shape):
#   lower_ws_from_singleton:        LoadVar(singleton), LoadField(ws_handle),
#                                    StoreVar(__ws_region)
#   lower_sectioned_data_division:  LoadVar(__ws_region)
#     -> lower_data_division(SPECIAL_REGISTERS_LAYOUT): Const(size), AllocRegion
#        (both span=None -- region-level, no single declaration)
#   lower_sectioned_data_division:  LoadVar(singleton), StoreField(RETURN_CODE_HANDLE)
_DATA_DIVISION_SETUP_OPCODES = (
    "LOAD_VAR",
    "LOAD_FIELD",
    "STORE_VAR",
    "LOAD_VAR",
    "CONST",
    "ALLOC_REGION",
    "LOAD_VAR",
    "STORE_FIELD",
)


def _skip_data_division_setup(raw):
    """Drop the leading data-division setup block that always precedes the
    first PROCEDURE DIVISION statement inside a `func_<pid>_0` body.

    `lower_ws_from_singleton` (LoadVar the singleton, LoadField ws_handle,
    StoreVar __ws_region) and `lower_sectioned_data_division` (LoadVar
    __ws_region; the region-level Const size + AllocRegion that
    `lower_data_division` emits with an explicit ``span=None`` for
    SPECIAL-REGISTERS; LoadVar the singleton + StoreField RETURN_CODE_HANDLE)
    are both named in SPANLESS_FUNCTIONS -- they describe whole-region
    plumbing, not any source declaration, so their instructions are
    deliberately <unknown>. They always run first, in that fixed order,
    before any statement lowering. The boundary is found structurally (the
    first instruction that carries a location), but the skipped prefix is
    then pinned to the exact known setup shape. A looser boundary ("skip up
    to the first located instruction" with no further check) would silently
    absorb a regression that dropped the span on the first statement's
    leading instructions -- the very gap this invariant exists to catch.
    """
    setup_end = next(
        (i for i, inst in enumerate(raw) if not inst.source_location.is_unknown()),
        0,
    )
    skipped = tuple(inst.opcode.name for inst in raw[:setup_end])
    assert skipped == _DATA_DIVISION_SETUP_OPCODES, (
        f"Unexpected unlocated instructions before the first located one: "
        f"{skipped}. Expected exactly the data-division setup block "
        f"{_DATA_DIVISION_SETUP_OPCODES}. Either a statement's leading "
        f"instructions lost their span (a real regression), or data-division "
        f"setup changed shape (update this constant)."
    )
    return raw[setup_end:]


def _procedure_body(ir):
    """Instructions between the program's entry label and its exit label,
    with the leading spanless data-division setup block removed.

    The prologue before the entry label is the singleton/init plumbing,
    which is also deliberately spanless (see SPANLESS_FUNCTIONS).
    """
    start = next(
        i
        for i, inst in enumerate(ir)
        if inst.opcode.name == "LABEL" and str(inst.label) == "func_probe_0"
    )
    end = next(
        i
        for i, inst in enumerate(ir)
        if inst.opcode.name == "LABEL" and str(inst.label) == "__after_probe_0"
    )
    return _skip_data_division_setup(ir[start + 1 : end])


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_procedure_division_instruction_is_located():
    body = _procedure_body(_probe_ir())
    assert body, "probe produced no procedure body"
    unlocated = [
        f"{i.opcode.name} at index {n}"
        for n, i in enumerate(body)
        if i.source_location.is_unknown()
    ]
    assert unlocated == [], (
        f"{len(unlocated)} of {len(body)} procedure-division instructions "
        f"have no source location:\n  " + "\n  ".join(unlocated[:20])
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_instructions_report_the_exact_declaring_position():
    """Pins the exact span, not merely 'something non-zero'.

    MOVE 7 TO WS-B is on line 8 of ARITH_SOURCE, starting at column 11.
    col_end is 21 — the START column of WS-B, the statement's last token,
    which is what ANTLR's getStop() reports. A non-zero check would let an
    off-by-one in the conversion through silently.
    """
    body = _procedure_body(_probe_ir())
    line_8 = [i for i in body if i.source_location.start_line == 8]
    assert line_8, "no instruction attributed to the MOVE on line 8"
    for inst in line_8:
        assert inst.source_location.start_col == 11
        assert inst.source_location.end_line == 8
        assert inst.source_location.end_col == 21


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inlined_encoder_bodies_inherit_the_triggering_statement():
    """A MOVE expands into a whole inlined encode body; all of it belongs
    to the MOVE's line, which is what makes the memory-effect sidecar
    useful instead of <unknown>."""
    body = _procedure_body(_probe_ir())
    line_8 = [i for i in body if i.source_location.start_line == 8]
    assert len(line_8) > 5, (
        "expected the MOVE's inlined encoder body to be attributed to it; "
        f"only {len(line_8)} instructions carry line 8"
    )


NESTED_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. NESTED.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(4) VALUE 5.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           IF WS-A > 0
               MOVE 7 TO WS-B
           END-IF.
           STOP RUN.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_nested_statements_report_their_own_lines():
    """The IF is on line 8 and its body MOVE on line 9. Both must appear.

    This is where a span=stmt.span pasted into the wrong frame shows up:
    if lower_if passes its own span down to the body, line 9 vanishes; if
    it passes the body's span to its branch scaffolding, line 8 vanishes.
    This is the coarse "does the line appear anywhere" check; it cannot
    catch a *partial* swap where both lines are still present but attached
    to the wrong instructions. See test_if_and_move_own_disjoint_instruction_ranges
    for that.
    """
    parser = make_cobol_parser()
    ir = CobolFrontend(parser).lower(NESTED_SOURCE)
    lines = {
        i.source_location.start_line for i in ir if not i.source_location.is_unknown()
    }
    assert 8 in lines, "the IF's own scaffolding is not attributed to line 8"
    assert 9 in lines, "the body MOVE is not attributed to line 9"


def _nested_procedure_body():
    """NESTED_SOURCE's procedure body, setup block skipped.

    Same shape as _procedure_body but for func_nested_0 / __after_nested_0.
    """
    parser = make_cobol_parser()
    ir = CobolFrontend(parser).lower(NESTED_SOURCE)
    start = next(
        i
        for i, inst in enumerate(ir)
        if inst.opcode.name == "LABEL" and str(inst.label) == "func_nested_0"
    )
    end = next(
        i
        for i, inst in enumerate(ir)
        if inst.opcode.name == "LABEL" and str(inst.label) == "__after_nested_0"
    )
    return _skip_data_division_setup(ir[start + 1 : end])


def _if_and_move_ranges(body):
    """Split NESTED_SOURCE's procedure body into three structurally-found
    ranges, using only opcode shape (never a hard-coded index):

    - ``if_head``: the IF's condition evaluation, its BRANCH_IF, and the
      ``if_true`` label it branches to on success -- all IF-owned, line 8.
    - ``move_body``: everything between the if_true label and the next
      unconditional BRANCH -- the MOVE's own lowered instructions, line 9.
      A BRANCH_IF is a different opcode and does not end this range, so a
      nested conditional inside the MOVE body (not present here) would not
      falsely terminate it.
    - ``if_tail``: the contiguous run of BRANCH/LABEL instructions
      immediately after move_body -- the jump past the else branch, the
      else label, its own jump, and the end-of-if label. All IF-owned,
      line 8. The run stops at the first non-BRANCH/LABEL instruction
      (STOP RUN's HALT), which is a sibling statement, not the IF's own.

    There is exactly one BRANCH_IF in this probe (a single, unnested IF),
    so this boundary-finding is unambiguous for NESTED_SOURCE.
    """
    branch_if_idx = next(
        i for i, inst in enumerate(body) if inst.opcode.name == "BRANCH_IF"
    )
    if_true_label_idx = branch_if_idx + 1
    assert body[if_true_label_idx].opcode.name == "LABEL", (
        "expected the label lower_if branches to on success immediately "
        "after BRANCH_IF"
    )

    tail_start_idx = next(
        i
        for i in range(if_true_label_idx + 1, len(body))
        if body[i].opcode.name == "BRANCH"
    )

    if_tail_end_idx = tail_start_idx
    while if_tail_end_idx < len(body) and body[if_tail_end_idx].opcode.name in (
        "BRANCH",
        "LABEL",
    ):
        if_tail_end_idx += 1

    if_head = body[: if_true_label_idx + 1]
    move_body = body[if_true_label_idx + 1 : tail_start_idx]
    if_tail = body[tail_start_idx:if_tail_end_idx]
    return if_head, move_body, if_tail


def _assert_if_and_move_own_their_lines(if_head, move_body, if_tail):
    for inst in if_head:
        assert inst.source_location.start_line == 8, (
            f"IF-owned {inst.opcode.name} does not carry line 8: "
            f"{inst.source_location}"
        )
    for inst in if_tail:
        assert inst.source_location.start_line == 8, (
            f"IF-owned {inst.opcode.name} does not carry line 8: "
            f"{inst.source_location}"
        )
    assert move_body, "expected the MOVE to lower into at least one instruction"
    for inst in move_body:
        assert inst.source_location.start_line == 9, (
            f"MOVE-owned {inst.opcode.name} does not carry line 9: "
            f"{inst.source_location}"
        )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_if_and_move_own_disjoint_instruction_ranges():
    """Strengthens test_nested_statements_report_their_own_lines against a
    *partial* cross-attribution: e.g. the IF's branch-past-else jump
    carrying line 9 while the condition evaluation stays on line 8. Both
    lines would still be present somewhere in the IR, so the coarse
    "does 8 appear, does 9 appear" check above would not catch it. Here
    every IF-owned instruction (condition eval, BRANCH_IF, if_true label,
    and the branch-past-else / else-label / end-of-if scaffolding) must be
    exactly line 8, and every MOVE-owned instruction must be exactly line 9
    -- no leakage either way.
    """
    body = _nested_procedure_body()
    if_head, move_body, if_tail = _if_and_move_ranges(body)
    _assert_if_and_move_own_their_lines(if_head, move_body, if_tail)


SUBSCRIPT_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SUBSCR.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-TABLE.
          05 WS-ROW PIC 9(4) OCCURS 3 TIMES.
       01 WS-I PIC 9(4) VALUE 2.
       PROCEDURE DIVISION.
           MOVE 7 TO WS-ROW(WS-I).
           STOP RUN.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_subscripted_access_instructions_are_located():
    """Subscript lowering goes through lower_expr_node, a plain function the
    static lint cannot inspect. The MOVE on line 9 must own every instruction
    it produces, including the subscript arithmetic."""
    parser = make_cobol_parser()
    ir = CobolFrontend(parser).lower(SUBSCRIPT_SOURCE)
    start = next(
        i
        for i, inst in enumerate(ir)
        if inst.opcode.name == "LABEL" and str(inst.label) == "func_subscr_0"
    )
    end = next(
        i
        for i, inst in enumerate(ir)
        if inst.opcode.name == "LABEL" and str(inst.label) == "__after_subscr_0"
    )
    body = _skip_data_division_setup(ir[start + 1 : end])
    assert any(i.opcode.name == "BINOP" for i in body), (
        "expected subscript offset arithmetic in the body; the probe is not "
        "exercising subscript lowering"
    )
    unlocated = [
        f"{i.opcode.name} at {n}"
        for n, i in enumerate(body)
        if i.source_location.is_unknown()
    ]
    assert unlocated == [], f"unlocated subscript instructions: {unlocated}"


SIMPLE_GOTO_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. GOTOLOC.
       PROCEDURE DIVISION.
       PARA-A.
           GO TO PARA-B.
       PARA-B.
           STOP RUN.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_simple_goto_branch_is_located():
    """GO TO PARA-B on line 5 lowers to a BRANCH to para_PARA-B that must
    carry line 5."""
    parser = make_cobol_parser()
    ir = CobolFrontend(parser).lower(SIMPLE_GOTO_SOURCE)
    (goto_branch,) = [
        i for i in ir if i.opcode.name == "BRANCH" and str(i.label) == "para_PARA-B"
    ]
    assert (
        goto_branch.source_location.start_line == 5
    ), f"GO TO's BRANCH is not attributed to line 5: {goto_branch.source_location}"


# A broad, end-to-end probe. The small probes above only exercise MOVE, ADD,
# DISPLAY, STOP RUN, one IF and one subscripted MOVE, and the lints above only
# see Python-side threading -- neither can notice the bridge or the ASG
# dropping a span. Two such gaps (GO TO's span lost in GotoStatement.from_dict;
# DECLARATIVES sections serialized with no position) passed every other test.
# This program lowers without any external file or subprogram: lowering never
# executes the OPEN/READ or the CALL.
E2E_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. E2EPGM.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-FILE ASSIGN TO 'IN.DAT'
               ORGANIZATION IS SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD IN-FILE.
       01 IN-REC PIC X(10).
       WORKING-STORAGE SECTION.
       01 WS-I PIC 9(4) VALUE 1.
       01 WS-TOTAL PIC 9(6) VALUE 0.
       01 WS-EOF PIC X VALUE 'N'.
       01 WS-NAME PIC X(20) VALUE 'ALPHA'.
       01 WS-COUNT PIC 9(4) VALUE 0.
       01 WS-TABLE.
          05 WS-ROW PIC 9(4) OCCURS 5 TIMES INDEXED BY IX.
       PROCEDURE DIVISION.
       DECLARATIVES.
       IO-ERR SECTION.
           USE AFTER ERROR PROCEDURE ON IN-FILE.
       IO-ERR-PARA.
           DISPLAY 'IO ERROR'.
       END DECLARATIVES.
       MAIN-SECTION SECTION.
       MAIN-PARA.
           PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 5
               IF WS-I > 2
                   MOVE WS-I TO WS-ROW(WS-I)
               ELSE
                   MOVE 0 TO WS-ROW(WS-I)
               END-IF
           END-PERFORM.
           EVALUATE WS-I
               WHEN 6
                   DISPLAY 'SIX'
               WHEN OTHER
                   DISPLAY 'OTHER'
           END-EVALUATE.
           COMPUTE WS-TOTAL = WS-ROW(3) + WS-I * 2.
           INSPECT WS-NAME TALLYING WS-COUNT FOR ALL 'A'.
           SET IX TO 1.
           SEARCH WS-ROW
               AT END DISPLAY 'NOT FOUND'
               WHEN WS-ROW(IX) = 4
                   DISPLAY 'FOUND'
           END-SEARCH.
           CALL 'X' USING WS-TOTAL.
           OPEN INPUT IN-FILE.
           READ IN-FILE
               AT END MOVE 'Y' TO WS-EOF
           END-READ.
           CLOSE IN-FILE.
           GO TO DONE-PARA.
       DONE-PARA.
           STOP RUN.
"""

# This program's exact leading run of unlocated instructions inside
# func_e2epgm_0. Same shape as _DATA_DIVISION_SETUP_OPCODES, plus two more
# region-level Const(size) + AllocRegion pairs that
# lower_sectioned_data_division emits because the program has a FILE SECTION
# and an INDEXED BY item:
#   lower_ws_from_singleton:        LoadVar, LoadField, StoreVar(__ws_region)
#   lower_sectioned_data_division:  LoadVar(__ws_region)
#     FILE, INDEXES, SPECIAL-REGISTERS: 3 x (Const(size), AllocRegion)
#     LoadVar(singleton), StoreField(RETURN_CODE_HANDLE)
# WORKING-STORAGE VALUE initialisation is located and runs in the prologue,
# before func_e2epgm_0, so it never interleaves with this run.
#
# Pinned exactly rather than by opcode set: a set of setup opcodes
# (LOAD_VAR, CONST, STORE_FIELD, ...) also describes the leading instructions
# of most statements -- a MOVE's CONST, a PERFORM VARYING's CONST + STORE --
# so a set check would silently absorb the first statement losing its span.
# The program is fixed, so its setup shape is fixed; if data-division setup
# legitimately changes shape, this tuple is the one place to update.
_E2E_SETUP_OPCODES = (
    "LOAD_VAR",
    "LOAD_FIELD",
    "STORE_VAR",
    "LOAD_VAR",
    "CONST",
    "ALLOC_REGION",
    "CONST",
    "ALLOC_REGION",
    "CONST",
    "ALLOC_REGION",
    "LOAD_VAR",
    "STORE_FIELD",
)


def _label_index(ir, name: str) -> int:
    return next(
        i
        for i, inst in enumerate(ir)
        if inst.opcode.name == "LABEL" and str(inst.label) == name
    )


def _describe_unlocated(body) -> list[str]:
    """Each unlocated instruction with its index, opcode, and the nearest
    preceding located line, so a failure names where it happened."""
    described: list[str] = []
    last_line = None
    for n, inst in enumerate(body):
        if inst.source_location.is_unknown():
            label = f" {inst.label}" if inst.opcode.name in ("LABEL", "BRANCH") else ""
            described.append(
                f"[{n}] {inst.opcode.name}{label} "
                f"(nearest preceding located line: {last_line})"
            )
        else:
            last_line = inst.source_location.start_line
    return described


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_instruction_of_a_broad_program_is_located():
    ir = CobolFrontend(make_cobol_parser()).lower(E2E_SOURCE)
    body = ir[
        _label_index(ir, "func_e2epgm_0") + 1 : _label_index(ir, "__after_e2epgm_0")
    ]
    setup = tuple(inst.opcode.name for inst in body[: len(_E2E_SETUP_OPCODES)])
    assert setup == _E2E_SETUP_OPCODES, (
        f"Leading instructions {setup} are not this program's data-division "
        f"setup block {_E2E_SETUP_OPCODES}."
    )
    assert all(
        inst.source_location.is_unknown() for inst in body[: len(_E2E_SETUP_OPCODES)]
    ), "the data-division setup block is expected to be deliberately spanless"
    procedure = body[len(_E2E_SETUP_OPCODES) :]
    opcodes = {inst.opcode.name for inst in procedure}
    assert {
        "BRANCH_IF",
        "CALL_WITH_MEMORY",
        "HALT",
    } <= opcodes, "the probe is no longer exercising the statements it was built for"
    unlocated = _describe_unlocated(procedure)
    assert unlocated == [], (
        f"{len(unlocated)} of {len(procedure)} instructions after the "
        f"data-division setup block have no source location "
        f"(indices relative to the end of that block):\n  " + "\n  ".join(unlocated)
    )
