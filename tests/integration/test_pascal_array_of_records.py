"""Integration tests: Pascal array-of-records pre-population with record objects.

Verifies that ``array[lo..hi] of TRecord`` declarations create actual record
instances at each index so that field access and mutation work correctly.
"""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint


def _run_pascal(source: str, max_steps: int = 2000) -> dict:
    """Run a Pascal program and return unwrapped local vars."""
    vm = run(
        source,
        language=Language.PASCAL,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestPascalArrayOfRecords:
    def test_simple_field_assignment_and_read(self):
        """Assign to nodes[0].value, then read it back."""
        vars_ = _run_pascal("""\
program M;
type
    TNode = record
        value: integer;
    end;
var
    nodes: array[0..1] of TNode;
    answer: integer;
begin
    nodes[0].value := 42;
    answer := nodes[0].value;
end.""")
        assert vars_[VarName("answer")] == 42

    def test_multiple_elements_independent(self):
        """Assign to different array elements, verify independence."""
        vars_ = _run_pascal("""\
program M;
type
    TNode = record
        value: integer;
    end;
var
    nodes: array[0..2] of TNode;
    a: integer;
    b: integer;
    c: integer;
begin
    nodes[0].value := 10;
    nodes[1].value := 20;
    nodes[2].value := 30;
    a := nodes[0].value;
    b := nodes[1].value;
    c := nodes[2].value;
end.""")
        assert vars_[VarName("a")] == 10
        assert vars_[VarName("b")] == 20
        assert vars_[VarName("c")] == 30

    def test_linked_list_traversal(self):
        """Array-of-records with index-based linked list traversal (red-dragon-b8k)."""
        vars_ = _run_pascal("""\
program M;
type
    TNode = record
        value: integer;
        nextIdx: integer;
    end;
var
    nodes: array[0..2] of TNode;
    answer: integer;
function sumList(idx: integer; count: integer): integer;
begin
    if count <= 0 then
        sumList := 0
    else
        sumList := nodes[idx].value + sumList(nodes[idx].nextIdx, count - 1);
end;
begin
    nodes[0].value := 1;
    nodes[0].nextIdx := 1;
    nodes[1].value := 2;
    nodes[1].nextIdx := 2;
    nodes[2].value := 3;
    nodes[2].nextIdx := 0;
    answer := sumList(0, 3);
end.""")
        assert vars_[VarName("answer")] == 6

    def test_multiple_fields_same_element(self):
        """Multiple field assignments to the same array element persist."""
        vars_ = _run_pascal("""\
program M;
type
    TPair = record
        x: integer;
        y: integer;
    end;
var
    pairs: array[0..0] of TPair;
    rx: integer;
    ry: integer;
begin
    pairs[0].x := 3;
    pairs[0].y := 7;
    rx := pairs[0].x;
    ry := pairs[0].y;
end.""")
        assert vars_[VarName("rx")] == 3
        assert vars_[VarName("ry")] == 7
