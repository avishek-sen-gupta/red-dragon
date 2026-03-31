"""Integration tests for Pascal property declarations -- end-to-end VM execution."""

from __future__ import annotations

import pytest

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint


def _run_pascal(source: str, max_steps: int = 500) -> tuple:
    """Run a Pascal program and return (vm, unwrapped local vars)."""
    vm = run(
        source,
        language=Language.PASCAL,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestPascalPropertyAccessorExecution:
    """End-to-end property accessor tests via VM execution."""

    def test_field_read_property_returns_backing_field_value(self):
        """foo.Name should return the backing field FName's value via getter."""
        _, vars_ = _run_pascal("""\
program M;
type
  TFoo = class
  private
    FName: string;
  public
    property Name: string read FName;
  end;
var
  foo: TFoo;
  answer: string;
begin
  foo := TFoo();
  foo.FName := 'Alice';
  answer := foo.Name;
end.""")
        assert vars_[VarName("answer")] == "Alice"

    def test_field_write_property_stores_to_backing_field(self):
        """foo.Name := 'x' with field-targeted write should store to FName."""
        _, vars_ = _run_pascal("""\
program M;
type
  TFoo = class
  private
    FName: string;
  public
    property Name: string read FName write FName;
  end;
var
  foo: TFoo;
  answer: string;
begin
  foo := TFoo();
  foo.Name := 'Bob';
  answer := foo.FName;
end.""")
        assert vars_[VarName("answer")] == "Bob"

    def test_method_write_property_calls_setter_procedure(self):
        """foo.Name := 'x' should call SetName which stores to self.FName."""
        _, vars_ = _run_pascal(
            """\
program M;
type
  TFoo = class
  private
    FName: string;
    procedure SetName(const AValue: string);
  public
    property Name: string read FName write SetName;
  end;

procedure TFoo.SetName(const AValue: string);
begin
  self.FName := AValue;
end;

var
  foo: TFoo;
  answer: string;
begin
  foo := TFoo();
  foo.Name := 'Charlie';
  answer := foo.Name;
end.""",
            max_steps=1000,
        )
        assert vars_[VarName("answer")] == "Charlie"

    def test_read_only_property_returns_value(self):
        """Read-only property (no write accessor) returns backing field value."""
        _, vars_ = _run_pascal("""\
program M;
type
  TFoo = class
  private
    FValue: Integer;
  public
    property Value: Integer read FValue;
  end;
var
  foo: TFoo;
  answer: Integer;
begin
  foo := TFoo();
  foo.FValue := 42;
  answer := foo.Value;
end.""")
        assert vars_[VarName("answer")] == 42

    def test_class_without_properties_regression(self):
        """Class without properties should still work (regression guard)."""
        _, vars_ = _run_pascal("""\
program M;
type
  TPoint = class
  public
    X: Integer;
    Y: Integer;
  end;
var
  p: TPoint;
  answer: Integer;
begin
  p := TPoint();
  p.X := 10;
  p.Y := 20;
  answer := p.X + p.Y;
end.""")
        assert vars_[VarName("answer")] == 30
