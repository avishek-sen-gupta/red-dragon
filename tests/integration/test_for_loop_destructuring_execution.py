"""Integration tests for for-loop destructuring — IR pipeline verification.

Verifies that destructuring in for-of/for-in loops produces correct IR
through the full lowering pipeline (parse → lower → IR) and that the
IR contains proper LOAD_INDEX decomposition for each destructured variable.

Languages tested:
  JavaScript — for (const [k, v] of arr)
  TypeScript — inherited from JS
  Kotlin     — for ((a, b) in pairs)
  C++        — for (auto [a, b] : pairs)
"""

from __future__ import annotations

import pytest

from interpreter.ir import Opcode
from tests.unit.rosetta.conftest import parse_for_language, find_all

# ---------------------------------------------------------------------------
# Programs: for-loop destructuring across 4 languages
# ---------------------------------------------------------------------------

ARRAY_DESTRUCTURE_PROGRAMS: dict[str, str] = {
    "javascript": """\
var arr = [[10, 1], [5, 2]];
var total = 0;
for (const [k, v] of arr) {
    total = total + k;
}
""",
    "typescript": """\
var arr: number[][] = [[10, 1], [5, 2]];
var total: number = 0;
for (const [k, v] of arr) {
    total = total + k;
}
""",
    "kotlin": """\
val pairs = arrayOf(arrayOf(10, 1), arrayOf(5, 2))
var total = 0
for ((k, v) in pairs) {
    total = total + k
}
""",
    "cpp": """\
int pairs[][2] = {{10, 1}, {5, 2}};
int total = 0;
for (auto [k, v] : pairs) {
    total = total + k;
}
""",
}

OBJECT_DESTRUCTURE_PROGRAMS: dict[str, str] = {
    "javascript": """\
var arr = [{x: 10, y: 1}];
for (const {x, y} of arr) {
    var z = x;
}
""",
    "typescript": """\
var arr = [{x: 10, y: 1}];
for (const {x, y} of arr) {
    var z = x;
}
""",
}


# ---------------------------------------------------------------------------
# Array destructuring tests
# ---------------------------------------------------------------------------


class TestForLoopArrayDestructuringIR:
    """Verify destructured for-loops emit LOAD_INDEX for each element."""

    @pytest.fixture(
        params=sorted(ARRAY_DESTRUCTURE_PROGRAMS.keys()),
        ids=lambda lang: lang,
    )
    def language_ir(self, request):
        lang = request.param
        ir = parse_for_language(lang, ARRAY_DESTRUCTURE_PROGRAMS[lang])
        return lang, ir

    def test_emits_load_index_for_destructuring(self, language_ir):
        """Each destructured variable should have its own LOAD_INDEX."""
        lang, ir = language_ir
        load_indices = find_all(ir, Opcode.LOAD_INDEX)
        # At least 3: one for iteration element, two for k and v
        assert len(load_indices) >= 3, (
            f"[{lang}] expected >= 3 LOAD_INDEX (1 iter + 2 destructure), "
            f"got {len(load_indices)}"
        )

    def test_destructured_vars_stored(self, language_ir):
        """Both k and v should appear as STORE_VAR operands."""
        lang, ir = language_ir
        store_names = [
            str(inst.operands[0])
            for inst in ir
            if inst.opcode == Opcode.DECL_VAR and inst.operands
        ]
        assert "k" in store_names, f"[{lang}] 'k' not in stored vars: {store_names}"
        assert "v" in store_names, f"[{lang}] 'v' not in stored vars: {store_names}"

    def test_body_uses_destructured_var(self, language_ir):
        """total = total + k should produce LOAD_VAR for 'k'."""
        lang, ir = language_ir
        load_names = [
            str(inst.operands[0])
            for inst in ir
            if inst.opcode == Opcode.LOAD_VAR and inst.operands
        ]
        assert "k" in load_names, f"[{lang}] 'k' not loaded in body: {load_names}"

    def test_no_unsupported_symbolics(self, language_ir):
        lang, ir = language_ir
        unsupported = [
            inst
            for inst in ir
            if inst.opcode == Opcode.SYMBOLIC
            and any("unsupported:" in str(op) for op in inst.operands)
        ]
        assert (
            len(unsupported) == 0
        ), f"[{lang}] found unsupported symbolics: {unsupported}"


# ---------------------------------------------------------------------------
# Object destructuring tests (JS/TS only)
# ---------------------------------------------------------------------------


class TestForLoopObjectDestructuringIR:
    """Verify object destructuring for-loops emit LOAD_FIELD for each property."""

    @pytest.fixture(
        params=sorted(OBJECT_DESTRUCTURE_PROGRAMS.keys()),
        ids=lambda lang: lang,
    )
    def language_ir(self, request):
        lang = request.param
        ir = parse_for_language(lang, OBJECT_DESTRUCTURE_PROGRAMS[lang])
        return lang, ir

    def test_emits_load_field_for_destructuring(self, language_ir):
        lang, ir = language_ir
        load_fields = find_all(ir, Opcode.LOAD_FIELD)
        assert len(load_fields) >= 2, (
            f"[{lang}] expected >= 2 LOAD_FIELD for object destructuring, "
            f"got {len(load_fields)}"
        )

    def test_destructured_vars_stored(self, language_ir):
        lang, ir = language_ir
        store_names = [
            str(inst.operands[0])
            for inst in ir
            if inst.opcode == Opcode.DECL_VAR and inst.operands
        ]
        assert "x" in store_names, f"[{lang}] 'x' not in stored vars"
        assert "y" in store_names, f"[{lang}] 'y' not in stored vars"
