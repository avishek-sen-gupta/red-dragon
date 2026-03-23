"""Unit tests for class inheritance — parent chain in FunctionRegistry.

Covers:
  1. _convert_llm_class_refs extracts class refs from LLM-emitted strings.
  2. _expand_parent_chains transitively expands direct parents into full MRO.
  3. build_registry populates class_parents from class_symbol_table.
"""

from __future__ import annotations

from interpreter.refs.class_ref import ClassRef
from interpreter.ir import IRInstruction, Opcode, CodeLabel
from interpreter.llm.llm_frontend import _convert_llm_class_refs
from interpreter.registry import (
    _expand_parent_chains,
    build_registry,
)
from interpreter.cfg import build_cfg

# ── _convert_llm_class_refs ──────────────────────────────────────


class TestConvertLLMClassRefs:
    def test_class_ref_without_parents(self):
        inst = IRInstruction(opcode=Opcode.CONST, operands=["<class:Dog@class_Dog_0>"])
        table: dict[str, ClassRef] = {}
        _convert_llm_class_refs([inst], table)
        assert inst.operands[0] == "class_Dog_0"
        assert table["class_Dog_0"] == ClassRef(
            name="Dog", label=CodeLabel("class_Dog_0"), parents=()
        )

    def test_class_ref_with_single_parent(self):
        inst = IRInstruction(
            opcode=Opcode.CONST, operands=["<class:Dog@class_Dog_0:Animal>"]
        )
        table: dict[str, ClassRef] = {}
        _convert_llm_class_refs([inst], table)
        assert inst.operands[0] == "class_Dog_0"
        assert table["class_Dog_0"] == ClassRef(
            name="Dog", label=CodeLabel("class_Dog_0"), parents=("Animal",)
        )

    def test_class_ref_with_multiple_parents(self):
        inst = IRInstruction(opcode=Opcode.CONST, operands=["<class:C@class_C_0:A,B>"])
        table: dict[str, ClassRef] = {}
        _convert_llm_class_refs([inst], table)
        assert inst.operands[0] == "class_C_0"
        assert table["class_C_0"].parents == ("A", "B")

    def test_non_matching_operand_unchanged(self):
        inst = IRInstruction(opcode=Opcode.CONST, operands=["not a class ref"])
        table: dict[str, ClassRef] = {}
        _convert_llm_class_refs([inst], table)
        assert inst.operands[0] == "not a class ref"
        assert table == {}

    def test_non_const_opcode_skipped(self):
        inst = IRInstruction(
            opcode=Opcode.STORE_VAR,
            operands=["Dog", "<class:Dog@class_Dog_0>"],
        )
        table: dict[str, ClassRef] = {}
        _convert_llm_class_refs([inst], table)
        assert inst.operands[1] == "<class:Dog@class_Dog_0>"
        assert table == {}


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
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),
            IRInstruction(opcode=Opcode.BRANCH, label=CodeLabel("end_class_Animal_1")),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("class_Animal_0")),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("end_class_Animal_1")),
            IRInstruction(opcode=Opcode.STORE_VAR, operands=["Animal", "%0"]),
            IRInstruction(opcode=Opcode.BRANCH, label=CodeLabel("end_class_Dog_3")),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("class_Dog_2")),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("end_class_Dog_3")),
            IRInstruction(opcode=Opcode.STORE_VAR, operands=["Dog", "%1"]),
        ]
        class_st = {
            "class_Animal_0": ClassRef(
                name="Animal", label=CodeLabel("class_Animal_0"), parents=()
            ),
            "class_Dog_2": ClassRef(
                name="Dog", label=CodeLabel("class_Dog_2"), parents=("Animal",)
            ),
        }
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg, class_symbol_table=class_st)
        assert registry.class_parents.get("Dog") == ["Animal"]
        assert registry.class_parents.get("Animal", []) == []

    def test_multi_level_parents_expanded(self):
        """C extends B extends A — class_parents['C'] should be ['B', 'A']."""
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),
        ]
        class_st = {
            "class_A_0": ClassRef(name="A", label=CodeLabel("class_A_0"), parents=()),
            "class_B_1": ClassRef(
                name="B", label=CodeLabel("class_B_1"), parents=("A",)
            ),
            "class_C_2": ClassRef(
                name="C", label=CodeLabel("class_C_2"), parents=("B",)
            ),
        }
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg, class_symbol_table=class_st)
        assert registry.class_parents["C"] == ["B", "A"]
        assert registry.class_parents["B"] == ["A"]
