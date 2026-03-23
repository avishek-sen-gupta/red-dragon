"""Tests for interpreter.project.types — data model for multi-file projects."""

from pathlib import Path

import pytest

from interpreter.project.types import (
    ImportRef,
    ExportTable,
    ModuleUnit,
    LinkedProgram,
    CyclicImportError,
)
from interpreter.constants import Language
from interpreter.ir import IRInstruction, Opcode

# ── ImportRef ────────────────────────────────────────────────────


class TestImportRef:
    def test_minimal_construction(self):
        ref = ImportRef(source_file=Path("main.py"), module_path="utils")
        assert ref.source_file == Path("main.py")
        assert ref.module_path == "utils"
        assert ref.names == ()
        assert ref.is_relative is False
        assert ref.relative_level == 0
        assert ref.is_system is False
        assert ref.kind == "import"
        assert ref.alias is None

    def test_python_from_import(self):
        ref = ImportRef(
            source_file=Path("main.py"),
            module_path="os.path",
            names=("join", "exists"),
            kind="import",
        )
        assert ref.names == ("join", "exists")
        assert ref.module_path == "os.path"

    def test_relative_import(self):
        ref = ImportRef(
            source_file=Path("pkg/main.py"),
            module_path="utils",
            names=("helper",),
            is_relative=True,
            relative_level=1,
        )
        assert ref.is_relative is True
        assert ref.relative_level == 1

    def test_system_import(self):
        ref = ImportRef(
            source_file=Path("main.py"),
            module_path="os",
            is_system=True,
        )
        assert ref.is_system is True

    def test_wildcard_import(self):
        ref = ImportRef(
            source_file=Path("main.py"),
            module_path="utils",
            names=("*",),
        )
        assert ref.names == ("*",)

    def test_aliased_import(self):
        ref = ImportRef(
            source_file=Path("main.py"),
            module_path="numpy",
            alias="np",
        )
        assert ref.alias == "np"

    def test_c_include(self):
        ref = ImportRef(
            source_file=Path("main.c"),
            module_path="header.h",
            kind="include",
            is_system=False,
        )
        assert ref.kind == "include"

    def test_system_c_include(self):
        ref = ImportRef(
            source_file=Path("main.c"),
            module_path="stdio.h",
            kind="include",
            is_system=True,
        )
        assert ref.is_system is True

    def test_rust_use(self):
        ref = ImportRef(
            source_file=Path("main.rs"),
            module_path="crate::utils",
            names=("helper",),
            kind="use",
            is_relative=True,
        )
        assert ref.kind == "use"

    def test_frozen(self):
        ref = ImportRef(source_file=Path("main.py"), module_path="utils")
        with pytest.raises(AttributeError):
            ref.module_path = "other"  # type: ignore[misc]


# ── ExportTable ──────────────────────────────────────────────────


class TestExportTable:
    def test_empty(self):
        et = ExportTable()
        assert et.functions == {}
        assert et.classes == {}
        assert et.variables == {}
        assert et.all_names() == set()

    def test_lookup_function(self):
        et = ExportTable(functions={"helper": "func_helper_0"})
        assert et.lookup("helper") == "func_helper_0"

    def test_lookup_class(self):
        et = ExportTable(classes={"User": "class_User_4"})
        assert et.lookup("User") == "class_User_4"

    def test_lookup_variable(self):
        et = ExportTable(variables={"PI": "%3"})
        assert et.lookup("PI") == "%3"

    def test_lookup_missing(self):
        et = ExportTable(functions={"helper": "func_helper_0"})
        assert et.lookup("missing") is None

    def test_lookup_priority_function_over_variable(self):
        """Functions take precedence over variables with the same name."""
        et = ExportTable(
            functions={"x": "func_x_0"},
            variables={"x": "%5"},
        )
        assert et.lookup("x") == "func_x_0"

    def test_all_names(self):
        et = ExportTable(
            functions={"f1": "func_f1_0", "f2": "func_f2_1"},
            classes={"C1": "class_C1_2"},
            variables={"v1": "%0"},
        )
        assert et.all_names() == {"f1", "f2", "C1", "v1"}

    def test_all_names_deduplicates(self):
        """If a name appears in multiple categories, all_names returns it once."""
        et = ExportTable(
            functions={"x": "func_x_0"},
            variables={"x": "%5"},
        )
        assert et.all_names() == {"x"}


# ── ModuleUnit ───────────────────────────────────────────────────


class TestModuleUnit:
    def _make_ir(self):
        return (
            IRInstruction(opcode=Opcode.LABEL, label="entry"),
            IRInstruction(opcode=Opcode.CONST, result_reg="%0", operands=["42"]),
        )

    def test_construction(self):
        ir = self._make_ir()
        mu = ModuleUnit(
            path=Path("utils.py"),
            language=Language.PYTHON,
            ir=ir,
            exports=ExportTable(functions={"helper": "func_helper_0"}),
            imports=(),
        )
        assert mu.path == Path("utils.py")
        assert mu.language == Language.PYTHON
        assert len(mu.ir) == 2
        assert mu.exports.lookup("helper") == "func_helper_0"

    def test_ir_is_tuple(self):
        ir = self._make_ir()
        mu = ModuleUnit(
            path=Path("utils.py"),
            language=Language.PYTHON,
            ir=ir,
            exports=ExportTable(),
            imports=(),
        )
        assert isinstance(mu.ir, tuple)

    def test_frozen(self):
        ir = self._make_ir()
        mu = ModuleUnit(
            path=Path("utils.py"),
            language=Language.PYTHON,
            ir=ir,
            exports=ExportTable(),
            imports=(),
        )
        with pytest.raises(AttributeError):
            mu.path = Path("other.py")  # type: ignore[misc]

    def test_with_imports(self):
        ref = ImportRef(source_file=Path("main.py"), module_path="utils")
        mu = ModuleUnit(
            path=Path("main.py"),
            language=Language.PYTHON,
            ir=self._make_ir(),
            exports=ExportTable(),
            imports=(ref,),
        )
        assert len(mu.imports) == 1
        assert mu.imports[0].module_path == "utils"


# ── LinkedProgram ────────────────────────────────────────────────


class TestLinkedProgram:
    def _make_module(self, path: str) -> ModuleUnit:
        return ModuleUnit(
            path=Path(path),
            language=Language.PYTHON,
            ir=(IRInstruction(opcode=Opcode.LABEL, label="entry"),),
            exports=ExportTable(),
            imports=(),
        )

    def test_construction(self):
        from interpreter.cfg_types import CFG
        from interpreter.registry import FunctionRegistry

        m1 = self._make_module("main.py")
        m2 = self._make_module("utils.py")
        lp = LinkedProgram(
            modules={Path("main.py"): m1, Path("utils.py"): m2},
            merged_ir=[IRInstruction(opcode=Opcode.LABEL, label="entry")],
            merged_cfg=CFG(),
            merged_registry=FunctionRegistry(),
            entry_module=Path("main.py"),
            import_graph={Path("main.py"): [Path("utils.py")], Path("utils.py"): []},
        )
        assert len(lp.modules) == 2
        assert lp.entry_module == Path("main.py")
        assert len(lp.import_graph) == 2
        assert lp.unresolved_imports == []

    def test_unresolved_imports_default_empty(self):
        from interpreter.cfg_types import CFG
        from interpreter.registry import FunctionRegistry

        lp = LinkedProgram(
            modules={},
            merged_ir=[],
            merged_cfg=CFG(),
            merged_registry=FunctionRegistry(),
            entry_module=Path("main.py"),
            import_graph={},
        )
        assert lp.unresolved_imports == []


# ── CyclicImportError ────────────────────────────────────────────


class TestCyclicImportError:
    def test_message_contains_cycle(self):
        cycle = [Path("a.py"), Path("b.py"), Path("a.py")]
        err = CyclicImportError(cycle)
        assert "a.py" in str(err)
        assert "b.py" in str(err)

    def test_cycle_attribute(self):
        cycle = [Path("a.py"), Path("b.py"), Path("a.py")]
        err = CyclicImportError(cycle)
        assert err.cycle == cycle
