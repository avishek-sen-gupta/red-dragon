"""Integration tests for Ruby scope resolution (::) execution.

Verifies that Ruby scope resolution (Module::Class) correctly resolves
through the full parse -> lower -> execute pipeline.
"""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.vm.vm_types import SymbolicValue
from tests.unit.rosetta.conftest import execute_for_language


class TestRubyScopeResolutionExecution:
    def test_module_class_scope_resolution_does_not_crash(self):
        """Animals::Dog.new() with scope resolution lowers and executes without crashing.

        The VM does not yet fully resolve classes nested inside modules,
        so we verify the scope-resolution syntax (::) is lowered and the
        program completes — but the method dispatch returns symbolic.
        """
        source = """\
module Animals
  class Dog
    def initialize()
      @legs = 4
    end
    def get_legs()
      return @legs
    end
  end
end

d = Animals::Dog.new()
answer = d.get_legs()
"""
        vm, stats = execute_for_language("ruby", source)
        assert VarName("answer") in vm.call_stack[0].local_vars
        assert stats.llm_calls == 0
        # Module-scoped method returns symbolic until module bodies execute
        val = vm.call_stack[0].local_vars[VarName("answer")]
        assert isinstance(val.value, SymbolicValue)

    def test_scope_resolution_constant_access_does_not_crash(self):
        """Config::PI with scope resolution lowers and executes without crashing.

        The VM does not yet execute module bodies, so constants defined
        inside a module are not materialized.  We verify the :: syntax
        is lowered and the program completes.
        """
        source = """\
module Config
  PI = 3
end

answer = Config::PI
"""
        vm, stats = execute_for_language("ruby", source)
        assert VarName("answer") in vm.call_stack[0].local_vars
        assert stats.llm_calls == 0
        # Module constants are not yet materialized — value is symbolic
        val = vm.call_stack[0].local_vars[VarName("answer")]
        assert isinstance(val.value, SymbolicValue)

    def test_scope_resolution_in_class_method_does_not_crash(self):
        """MathConsts::PI inside a class method lowers and executes without crashing.

        The VM does not yet execute module bodies, so module constants
        resolve to symbolic values.  We verify the :: syntax inside a
        method body is lowered and the program completes.
        """
        source = """\
module MathConsts
  PI = 3
end

class Circle
  def initialize(r)
    @r = r
  end
  def area()
    return @r * @r * MathConsts::PI
  end
end

c = Circle.new(2)
answer = c.area()
"""
        vm, stats = execute_for_language("ruby", source)
        assert VarName("answer") in vm.call_stack[0].local_vars
        assert stats.llm_calls == 0
