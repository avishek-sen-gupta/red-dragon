"""Unit tests for destructuring assignment in for-of/for-in loops.

Verifies that for-loop destructuring patterns (array, object, multi-variable,
structured binding) are decomposed into individual LOAD_INDEX/LOAD_FIELD +
STORE_VAR instructions instead of treating the entire pattern as a single
variable name.

Languages tested:
  JavaScript — for (const [k, v] of arr) / for (const {x, y} of arr)
  TypeScript — inherited from JS
  Kotlin     — for ((a, b) in pairs)
  C++        — for (auto [a, b] : pairs)
"""

from __future__ import annotations

from interpreter.frontends.javascript import JavaScriptFrontend
from interpreter.frontends.typescript import TypeScriptFrontend
from interpreter.frontends.kotlin import KotlinFrontend
from interpreter.frontends.cpp import CppFrontend
from interpreter.ir import Opcode
from interpreter.instructions import InstructionBase
from interpreter.parser import TreeSitterParserFactory


def _lower(frontend_class, lang: str, source: str) -> list[InstructionBase]:
    frontend = frontend_class(TreeSitterParserFactory(), lang)
    return frontend.lower(source.encode("utf-8"))


def _store_var_names(instructions: list[InstructionBase]) -> list[str]:
    return [
        str(inst.operands[0])
        for inst in instructions
        if inst.opcode == Opcode.DECL_VAR and inst.operands
    ]


def _load_index_count(instructions: list[InstructionBase]) -> int:
    return sum(1 for inst in instructions if inst.opcode == Opcode.LOAD_INDEX)


def _load_field_names(instructions: list[InstructionBase]) -> list[str]:
    return [
        str(inst.operands[1])
        for inst in instructions
        if inst.opcode == Opcode.LOAD_FIELD and len(inst.operands) >= 2
    ]


# ---------------------------------------------------------------------------
# JavaScript for-of array destructuring
# ---------------------------------------------------------------------------


class TestJSForOfArrayDestructuring:
    """for (const [k, v] of arr) should decompose into LOAD_INDEX per element."""

    def test_array_destructure_emits_load_index(self):
        source = """
        function main() {
            let arr = [[1, 'a'], [2, 'b']];
            for (const [k, v] of arr) {
                let y = k;
            }
        }
        """
        ir = _lower(JavaScriptFrontend, "javascript", source)
        # Should have at least 2 LOAD_INDEX inside the loop body
        # (one for k, one for v, plus the iteration index)
        stores = _store_var_names(ir)
        assert "k" in stores, f"Expected 'k' in stores, got {stores}"
        assert "v" in stores, f"Expected 'v' in stores, got {stores}"

    def test_array_destructure_three_elements(self):
        """for (const [a, b, c] of arr) should emit LOAD_INDEX per element."""
        source = """
        function main() {
            let arr = [[1, 2, 3]];
            for (const [a, b, c] of arr) {
                let y = a;
            }
        }
        """
        ir = _lower(JavaScriptFrontend, "javascript", source)
        stores = _store_var_names(ir)
        assert "a" in stores
        assert "b" in stores
        assert "c" in stores

        # Should have at least 3 LOAD_INDEX for destructuring a, b, c
        load_idx = _load_index_count(ir)
        assert load_idx >= 3, f"Expected >= 3 LOAD_INDEX for 3 elements, got {load_idx}"


# ---------------------------------------------------------------------------
# JavaScript for-of object destructuring
# ---------------------------------------------------------------------------


class TestJSForOfObjectDestructuring:
    """for (const {x, y} of arr) should decompose into LOAD_FIELD per property."""

    def test_object_destructure_emits_load_field(self):
        source = """
        function main() {
            let arr = [{x: 1, y: 2}];
            for (const {x, y} of arr) {
                let z = x;
            }
        }
        """
        ir = _lower(JavaScriptFrontend, "javascript", source)
        stores = _store_var_names(ir)
        assert "x" in stores, f"Expected 'x' in stores, got {stores}"
        assert "y" in stores, f"Expected 'y' in stores, got {stores}"
        # Should emit LOAD_FIELD for each destructured property
        field_names = _load_field_names(ir)
        assert "x" in field_names
        assert "y" in field_names


# ---------------------------------------------------------------------------
# TypeScript for-of destructuring (inherits from JS)
# ---------------------------------------------------------------------------


class TestTSForOfArrayDestructuring:
    """TypeScript inherits JS for-of destructuring."""

    def test_array_destructure_emits_stores(self):
        source = """
        function main() {
            let arr: number[][] = [[1, 2], [3, 4]];
            for (const [k, v] of arr) {
                let y = k;
            }
        }
        """
        ir = _lower(TypeScriptFrontend, "typescript", source)
        stores = _store_var_names(ir)
        assert "k" in stores
        assert "v" in stores


class TestTSForOfObjectDestructuring:
    """TypeScript inherits JS for-of object destructuring."""

    def test_object_destructure_emits_stores(self):
        source = """
        function main() {
            let arr = [{x: 1, y: 2}];
            for (const {x, y} of arr) {
                let z = x;
            }
        }
        """
        ir = _lower(TypeScriptFrontend, "typescript", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        assert "y" in stores


# ---------------------------------------------------------------------------
# Kotlin for destructuring
# ---------------------------------------------------------------------------


class TestKotlinForDestructuring:
    """for ((a, b) in pairs) should decompose into LOAD_INDEX per element."""

    def test_multi_variable_emits_stores(self):
        source = """
        fun main() {
            val pairs = listOf(Pair(1, 2), Pair(3, 4))
            for ((a, b) in pairs) {
                val y = a
            }
        }
        """
        ir = _lower(KotlinFrontend, "kotlin", source)
        stores = _store_var_names(ir)
        assert "a" in stores, f"Expected 'a' in stores, got {stores}"
        assert "b" in stores, f"Expected 'b' in stores, got {stores}"

    def test_multi_variable_three_elements(self):
        source = """
        fun main() {
            val triples = listOf(Triple(1, 2, 3))
            for ((a, b, c) in triples) {
                val y = a
            }
        }
        """
        ir = _lower(KotlinFrontend, "kotlin", source)
        stores = _store_var_names(ir)
        assert "a" in stores
        assert "b" in stores
        assert "c" in stores

    def test_multi_variable_emits_load_index(self):
        source = """
        fun main() {
            val pairs = listOf(Pair(1, 2))
            for ((a, b) in pairs) {
                val y = a
            }
        }
        """
        ir = _lower(KotlinFrontend, "kotlin", source)
        # Should have LOAD_INDEX for positional access into pair elements
        load_idx = _load_index_count(ir)
        # At least 3: one for iteration element, two for destructuring
        assert load_idx >= 3, f"Expected >= 3 LOAD_INDEX, got {load_idx}"


# ---------------------------------------------------------------------------
# C++ structured binding in range-for
# ---------------------------------------------------------------------------


class TestCppStructuredBindingRangeFor:
    """for (auto [a, b] : pairs) should decompose into LOAD_INDEX per element."""

    def test_structured_binding_emits_stores(self):
        source = """
        int main() {
            std::vector<std::pair<int,int>> pairs = {{1,2},{3,4}};
            for (auto [a, b] : pairs) {
                int y = a;
            }
        }
        """
        ir = _lower(CppFrontend, "cpp", source)
        stores = _store_var_names(ir)
        assert "a" in stores, f"Expected 'a' in stores, got {stores}"
        assert "b" in stores, f"Expected 'b' in stores, got {stores}"

    def test_structured_binding_three_elements(self):
        source = """
        int main() {
            int arr[][3] = {{1,2,3}};
            for (auto [a, b, c] : arr) {
                int y = a;
            }
        }
        """
        ir = _lower(CppFrontend, "cpp", source)
        stores = _store_var_names(ir)
        assert "a" in stores
        assert "b" in stores
        assert "c" in stores

    def test_structured_binding_emits_load_index(self):
        source = """
        int main() {
            std::vector<std::pair<int,int>> pairs = {{1,2}};
            for (auto [a, b] : pairs) {
                int y = a;
            }
        }
        """
        ir = _lower(CppFrontend, "cpp", source)
        load_idx = _load_index_count(ir)
        # At least 3: one for iteration element, two for destructuring
        assert load_idx >= 3, f"Expected >= 3 LOAD_INDEX, got {load_idx}"


class TestCppStructuredBindingDeclaration:
    """auto [a, b] = expr; should decompose into LOAD_INDEX + DECL_VAR."""

    def test_structured_binding_declaration_emits_decl_vars(self):
        source = """
        int main() {
            int arr[2] = {10, 20};
            auto [a, b] = arr;
        }
        """
        ir = _lower(CppFrontend, "cpp", source)
        decl_names = _store_var_names(ir)
        assert "a" in decl_names, f"Expected 'a' in decls, got {decl_names}"
        assert "b" in decl_names, f"Expected 'b' in decls, got {decl_names}"

    def test_structured_binding_declaration_emits_load_index(self):
        source = """
        int main() {
            int arr[2] = {10, 20};
            auto [x, y] = arr;
        }
        """
        ir = _lower(CppFrontend, "cpp", source)
        load_idx = _load_index_count(ir)
        assert load_idx >= 2, f"Expected >= 2 LOAD_INDEX, got {load_idx}"

    def test_structured_binding_three_vars(self):
        source = """
        int main() {
            int arr[3] = {1, 2, 3};
            auto [a, b, c] = arr;
        }
        """
        ir = _lower(CppFrontend, "cpp", source)
        decl_names = _store_var_names(ir)
        assert "a" in decl_names
        assert "b" in decl_names
        assert "c" in decl_names
