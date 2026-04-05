"""Tests for EntryPointPickerPanel — entry point grouping."""

from pathlib import Path
from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel
from interpreter.refs.func_ref import FuncRef
from viz.panels.entry_point_picker_panel import group_entry_points


class TestGroupEntryPoints:
    def test_empty_modules(self) -> None:
        result = group_entry_points([], {})
        assert result == []

    def test_single_module_single_function(self) -> None:
        path = Path("/project/main.py")
        ref = FuncRef(name=FuncName("main"), label=CodeLabel("main.func_main_0"))
        func_table = {CodeLabel("main.func_main_0"): ref}
        result = group_entry_points([path], func_table)
        assert len(result) == 1
        module_path, funcs = result[0]
        assert module_path == path
        assert len(funcs) == 1
        assert funcs[0].name == FuncName("main")

    def test_two_modules(self) -> None:
        utils = Path("/project/utils.py")
        main = Path("/project/main.py")
        ref1 = FuncRef(name=FuncName("helper"), label=CodeLabel("utils.func_helper_0"))
        ref2 = FuncRef(name=FuncName("run"), label=CodeLabel("main.func_run_0"))
        func_table = {ref1.label: ref1, ref2.label: ref2}
        result = group_entry_points([utils, main], func_table)
        assert len(result) == 2
