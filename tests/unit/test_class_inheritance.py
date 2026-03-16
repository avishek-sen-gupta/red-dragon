"""Unit tests for class inheritance — parent chain in FunctionRegistry.

Covers:
  1. _parse_class_ref extracts parent names from extended class ref format.
  2. _scan_classes populates class_parents from IR metadata.
  3. _expand_parent_chains transitively expands direct parents into full MRO.
  4. Method resolution walks the parent chain on miss.
"""

from __future__ import annotations

from interpreter.class_ref import ClassRef
from interpreter.ir import IRInstruction, Opcode
from interpreter.registry import (
    _parse_class_ref,
    _expand_parent_chains,
    build_registry,
)
from interpreter.cfg import build_cfg

# ── _parse_class_ref ─────────────────────────────────────────────


class TestParseClassRef:
    def test_class_ref_without_parents(self):
        result = _parse_class_ref("<class:Dog@class_Dog_0>")
        assert result.matched
        assert result.name == "Dog"
        assert result.label == "class_Dog_0"
        assert result.parents == []

    def test_class_ref_with_single_parent(self):
        result = _parse_class_ref("<class:Dog@class_Dog_0:Animal>")
        assert result.matched
        assert result.name == "Dog"
        assert result.label == "class_Dog_0"
        assert result.parents == ["Animal"]

    def test_class_ref_with_multiple_parents(self):
        result = _parse_class_ref("<class:C@class_C_0:A,B>")
        assert result.matched
        assert result.name == "C"
        assert result.parents == ["A", "B"]

    def test_class_ref_non_matching(self):
        result = _parse_class_ref("not a class ref")
        assert not result.matched
        assert result.parents == []


# ── _expand_parent_chains ────────────────────────────────────────


class TestExpandParentChains:
    def test_single_level(self):
        direct = {"Dog": ["Animal"]}
        expanded = _expand_parent_chains(direct)
        assert expanded["Dog"] == ["Animal"]

    def test_multi_level(self):
        direct = {"C": ["B"], "B": ["A"]}
        expanded = _expand_parent_chains(direct)
        assert expanded["C"] == ["B", "A"]
        assert expanded["B"] == ["A"]

    def test_diamond(self):
        """Diamond: D extends B, C; B extends A; C extends A.

        BFS traversal: B first (direct parent), then C (direct parent),
        then A (shared grandparent, deduplicated).
        """
        direct = {"D": ["B", "C"], "B": ["A"], "C": ["A"]}
        expanded = _expand_parent_chains(direct)
        assert expanded["D"] == ["B", "C", "A"]

    def test_no_parents(self):
        expanded = _expand_parent_chains({})
        assert expanded == {}


# ── Registry: class_parents populated from IR ────────────────────


class TestRegistryClassParents:
    def test_class_parents_populated_from_ir(self):
        """build_registry should populate class_parents from class_symbol_table."""
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="entry"),
            IRInstruction(opcode=Opcode.BRANCH, label="end_class_Animal_1"),
            IRInstruction(opcode=Opcode.LABEL, label="class_Animal_0"),
            IRInstruction(opcode=Opcode.LABEL, label="end_class_Animal_1"),
            IRInstruction(opcode=Opcode.STORE_VAR, operands=["Animal", "%0"]),
            IRInstruction(opcode=Opcode.BRANCH, label="end_class_Dog_3"),
            IRInstruction(opcode=Opcode.LABEL, label="class_Dog_2"),
            IRInstruction(opcode=Opcode.LABEL, label="end_class_Dog_3"),
            IRInstruction(opcode=Opcode.STORE_VAR, operands=["Dog", "%1"]),
        ]
        class_st = {
            "class_Animal_0": ClassRef(
                name="Animal", label="class_Animal_0", parents=()
            ),
            "class_Dog_2": ClassRef(
                name="Dog", label="class_Dog_2", parents=("Animal",)
            ),
        }
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg, class_symbol_table=class_st)
        assert registry.class_parents.get("Dog") == ["Animal"]
        assert registry.class_parents.get("Animal", []) == []

    def test_multi_level_parents_expanded(self):
        """C extends B extends A — class_parents['C'] should be ['B', 'A']."""
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="entry"),
        ]
        class_st = {
            "class_A_0": ClassRef(name="A", label="class_A_0", parents=()),
            "class_B_1": ClassRef(name="B", label="class_B_1", parents=("A",)),
            "class_C_2": ClassRef(name="C", label="class_C_2", parents=("B",)),
        }
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg, class_symbol_table=class_st)
        assert registry.class_parents["C"] == ["B", "A"]
        assert registry.class_parents["B"] == ["A"]
