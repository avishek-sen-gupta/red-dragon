"""Tests for import stub dropping in the linker."""

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.ir import IRInstruction, Opcode
from interpreter.project.linker import link_modules
from interpreter.project.types import ExportTable, ImportRef, ModuleUnit


def _make_module(path, ir_instructions, exports=ExportTable(), imports=()):
    return ModuleUnit(
        path=Path(path),
        language=Language.PYTHON,
        ir=tuple(ir_instructions),
        exports=exports,
        imports=imports,
    )


class TestImportStubDropping:
    """Test that import stubs (CALL_FUNCTION 'import' + DECL_VAR) are dropped
    for names resolved by dependency modules."""

    def _link(self, dep_module, entry_module):
        modules = {dep_module.path: dep_module, entry_module.path: entry_module}
        import_graph = {
            entry_module.path: [dep_module.path],
            dep_module.path: [],
        }
        return link_modules(
            modules=modules,
            import_graph=import_graph,
            entry_module=entry_module.path,
            project_root=Path("/project"),
            topo_order=[dep_module.path, entry_module.path],
        )

    def test_adjacent_stub_is_dropped(self):
        """Standard case: CALL_FUNCTION 'import' immediately followed by DECL_VAR."""
        dep = _make_module(
            "/project/utils.py",
            [
                IRInstruction(opcode=Opcode.LABEL, label="entry"),
                IRInstruction(
                    opcode=Opcode.CONST, result_reg="%0", operands=["func_add_0"]
                ),
                IRInstruction(opcode=Opcode.DECL_VAR, operands=["add", "%0"]),
            ],
            exports=ExportTable(functions={"add": "func_add_0"}),
        )
        entry = _make_module(
            "/project/main.py",
            [
                IRInstruction(opcode=Opcode.LABEL, label="entry"),
                IRInstruction(
                    opcode=Opcode.CALL_FUNCTION,
                    result_reg="%0",
                    operands=["import", "from utils import add"],
                ),
                IRInstruction(opcode=Opcode.DECL_VAR, operands=["add", "%0"]),
                IRInstruction(
                    opcode=Opcode.CALL_FUNCTION,
                    result_reg="%1",
                    operands=["add", "42"],
                ),
            ],
        )
        linked = self._link(dep, entry)
        # The import stub should be dropped — no CALL_FUNCTION "import" in merged IR
        import_calls = [
            inst
            for inst in linked.merged_ir
            if inst.opcode == Opcode.CALL_FUNCTION
            and len(inst.operands) >= 1
            and str(inst.operands[0]) == "import"
        ]
        assert import_calls == []

    def test_intervening_instruction_does_not_corrupt(self):
        """If an instruction appears between CALL_FUNCTION 'import' and DECL_VAR,
        the stub dropper must not match a later unrelated DECL_VAR."""
        dep = _make_module(
            "/project/utils.py",
            [
                IRInstruction(opcode=Opcode.LABEL, label="entry"),
                IRInstruction(
                    opcode=Opcode.CONST, result_reg="%0", operands=["func_add_0"]
                ),
                IRInstruction(opcode=Opcode.DECL_VAR, operands=["add", "%0"]),
            ],
            exports=ExportTable(functions={"add": "func_add_0"}),
        )
        entry = _make_module(
            "/project/main.py",
            [
                IRInstruction(opcode=Opcode.LABEL, label="entry"),
                # Import CALL
                IRInstruction(
                    opcode=Opcode.CALL_FUNCTION,
                    result_reg="%0",
                    operands=["import", "from utils import add"],
                ),
                # Intervening instruction (e.g., a type annotation or symbolic)
                IRInstruction(
                    opcode=Opcode.SYMBOLIC,
                    result_reg="%99",
                    operands=["type_annotation"],
                ),
                # DECL_VAR for the import — not adjacent
                IRInstruction(opcode=Opcode.DECL_VAR, operands=["add", "%0"]),
                # Unrelated DECL_VAR that must NOT be dropped
                IRInstruction(opcode=Opcode.CONST, result_reg="%1", operands=["42"]),
                IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%1"]),
            ],
        )
        linked = self._link(dep, entry)
        # The unrelated DECL_VAR "x" must survive
        decl_x = [
            inst
            for inst in linked.merged_ir
            if inst.opcode == Opcode.DECL_VAR and str(inst.operands[0]) == "x"
        ]
        assert (
            len(decl_x) == 1
        ), f"DECL_VAR x was incorrectly dropped: {linked.merged_ir}"
