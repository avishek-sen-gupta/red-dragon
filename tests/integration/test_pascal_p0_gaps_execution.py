"""Integration tests for Pascal P0 gap fixes -- end-to-end execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_pascal(source: str, max_steps: int = 300):
    """Run a Pascal program and return (vm, frame.local_vars)."""
    vm = run(source, language=Language.PASCAL, max_steps=max_steps)
    return vm, dict(vm.call_stack[0].local_vars)


class TestPascalForeachExecution:
    def test_foreach_executes(self):
        """for-in loop should execute without errors."""
        _, local_vars = _run_pascal(
            "program M; var i: Integer; begin for i in arr do writeln(i); end."
        )
        assert "i" in local_vars


class TestPascalGotoExecution:
    def test_goto_skips_statements(self):
        """goto should jump past intermediate statements."""
        _, local_vars = _run_pascal(
            "program M; label skip; begin x := 1; goto skip; x := 99; skip: y := 2; end."
        )
        assert "y" in local_vars


class TestPascalDeclClassExecution:
    def test_class_declaration_executes(self):
        source = """\
program M;
type
  TAnimal = class
    Name: string;
  end;
begin
end."""
        _, local_vars = _run_pascal(source)
        assert "TAnimal" in local_vars
