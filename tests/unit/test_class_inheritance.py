"""Unit tests for class inheritance — parent chain in FunctionRegistry.

Covers:
  1. _convert_llm_class_refs extracts class refs from LLM-emitted strings.
  2. _expand_parent_chains transitively expands direct parents into full MRO.
  3. build_registry populates class_parents from class_symbol_table.
"""

from __future__ import annotations

from interpreter.refs.class_ref import ClassRef
from interpreter.ir import IRInstruction, Opcode, CodeLabel
from interpreter.class_name import ClassName
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
        instructions = [inst]
        table: dict[str, ClassRef] = {}
        _convert_llm_class_refs(instructions, table)
        assert instructions[0].operands[0] == "class_Dog_0"
        assert table["class_Dog_0"] == ClassRef(
            name=ClassName("Dog"), label=CodeLabel("class_Dog_0"), parents=()
        )

    def test_class_ref_with_single_parent(self):
        inst = IRInstruction(
            opcode=Opcode.CONST, operands=["<class:Dog@class_Dog_0:Animal>"]
        )
        instructions = [inst]
        table: dict[str, ClassRef] = {}
        _convert_llm_class_refs(instructions, table)
        assert instructions[0].operands[0] == "class_Dog_0"
        assert table["class_Dog_0"] == ClassRef(
            name=ClassName("Dog"),
            label=CodeLabel("class_Dog_0"),
            parents=(ClassName("Animal"),),
        )

    def test_class_ref_with_multiple_parents(self):
        inst = IRInstruction(opcode=Opcode.CONST, operands=["<class:C@class_C_0:A,B>"])
        instructions = [inst]
        table: dict[str, ClassRef] = {}
        _convert_llm_class_refs(instructions, table)
        assert instructions[0].operands[0] == "class_C_0"
        assert table["class_C_0"].parents == (ClassName("A"), ClassName("B"))

    def test_non_matching_operand_unchanged(self):
        inst = IRInstruction(opcode=Opcode.CONST, operands=["not a class ref"])
        instructions = [inst]
        table: dict[str, ClassRef] = {}
        _convert_llm_class_refs(instructions, table)
        assert instructions[0].operands[0] == "not a class ref"
        assert table == {}

    def test_non_const_opcode_skipped(self):
        inst = IRInstruction(
            opcode=Opcode.STORE_VAR,
            operands=["Dog", "<class:Dog@class_Dog_0>"],
        )
        instructions = [inst]
        table: dict[str, ClassRef] = {}
        _convert_llm_class_refs(instructions, table)
        assert instructions[0].operands[1] == "<class:Dog@class_Dog_0>"
        assert table == {}


# ── _expand_parent_chains ────────────────────────────────────────


class TestExpandParentChains:
    def test_single_level(self):
        direct = {ClassName("Dog"): [ClassName("Animal")]}
        expanded = _expand_parent_chains(direct)
        assert expanded[ClassName("Dog")] == [ClassName("Animal")]

    def test_multi_level(self):
        direct = {ClassName("C"): [ClassName("B")], ClassName("B"): [ClassName("A")]}
        expanded = _expand_parent_chains(direct)
        assert expanded[ClassName("C")] == [ClassName("B"), ClassName("A")]
        assert expanded[ClassName("B")] == [ClassName("A")]

    def test_diamond(self):
        """Diamond: D extends B, C; B extends A; C extends A.

        BFS traversal: B first (direct parent), then C (direct parent),
        then A (shared grandparent, deduplicated).
        """
        direct = {
            ClassName("D"): [ClassName("B"), ClassName("C")],
            ClassName("B"): [ClassName("A")],
            ClassName("C"): [ClassName("A")],
        }
        expanded = _expand_parent_chains(direct)
        assert expanded[ClassName("D")] == [
            ClassName("B"),
            ClassName("C"),
            ClassName("A"),
        ]

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
                name=ClassName("Animal"), label=CodeLabel("class_Animal_0"), parents=()
            ),
            "class_Dog_2": ClassRef(
                name=ClassName("Dog"),
                label=CodeLabel("class_Dog_2"),
                parents=(ClassName("Animal"),),
            ),
        }
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg, class_symbol_table=class_st)
        assert registry.class_parents.get(ClassName("Dog")) == [ClassName("Animal")]
        assert registry.class_parents.get(ClassName("Animal"), []) == []

    def test_multi_level_parents_expanded(self):
        """C extends B extends A — class_parents['C'] should be ['B', 'A']."""
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),
        ]
        class_st = {
            "class_A_0": ClassRef(
                name=ClassName("A"), label=CodeLabel("class_A_0"), parents=()
            ),
            "class_B_1": ClassRef(
                name=ClassName("B"),
                label=CodeLabel("class_B_1"),
                parents=(ClassName("A"),),
            ),
            "class_C_2": ClassRef(
                name=ClassName("C"),
                label=CodeLabel("class_C_2"),
                parents=(ClassName("B"),),
            ),
        }
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg, class_symbol_table=class_st)
        assert registry.class_parents[ClassName("C")] == [
            ClassName("B"),
            ClassName("A"),
        ]
        assert registry.class_parents[ClassName("B")] == [ClassName("A")]
