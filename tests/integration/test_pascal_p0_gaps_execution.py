"""Integration tests for Pascal P0 gap fixes -- end-to-end execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_pascal(source: str, max_steps: int = 300):
    """Run a Pascal program and return (vm, frame.local_vars)."""
    vm = run(source, language=Language.PASCAL, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestPascalForeachExecution:
    def test_foreach_executes(self):
        """for-in loop should execute without errors."""
        _, local_vars = _run_pascal(
            "program M; var i: Integer; begin for i in arr do writeln(i); end."
        )
        assert "i" in local_vars

    def test_foreach_accumulates_via_index(self):
        """for-in loop should iterate — verify the index counter advances."""
        _, local_vars = _run_pascal(
            "program M; var s, i: Integer; begin s := 0; for i in arr do s := s + 1; end.",
            max_steps=500,
        )
        # __foreach_idx_i tracks iterations; should be > 0 if loop ran
        assert (
            local_vars.get("__foreach_idx_i", 0) > 0
        ), "foreach should iterate at least once"


class TestPascalGotoExecution:
    def test_goto_skips_statements(self):
        """goto should jump past intermediate statements."""
        _, local_vars = _run_pascal(
            "program M; label skip; begin x := 1; goto skip; x := 99; skip: y := 2; end."
        )
        assert local_vars["x"] == 1, "goto should skip x := 99"
        assert local_vars["y"] == 2

    def test_goto_backward_jump(self):
        """goto can jump backward to create a loop."""
        _, local_vars = _run_pascal(
            "program M; label top; var x: Integer; begin x := 0; top: x := x + 1; if x < 3 then goto top; end.",
            max_steps=500,
        )
        assert local_vars["x"] == 3


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
