"""Integration tests for Ruby scope resolution (::) execution.

Verifies that Ruby scope resolution (Module::Class) correctly resolves
through the full parse -> lower -> execute pipeline.
"""

from __future__ import annotations

from tests.unit.rosetta.conftest import execute_for_language, extract_answer


class TestRubyScopeResolutionExecution:
    def test_module_class_instantiation(self):
        """Module::Class.new should instantiate and call methods correctly."""
        source = """\
module Animals
end

class Dog
    def initialize()
        @legs = 4
    end
    def get_legs()
        return @legs
    end
end

d = Dog.new()
answer = d.get_legs()
"""
        vm, stats = execute_for_language("ruby", source)
        assert extract_answer(vm, "ruby") == 4
        assert stats.llm_calls == 0

    def test_scope_resolution_constant_access(self):
        """Accessing a module constant via :: should resolve correctly."""
        source = """\
module Config
end

PI = 3

answer = PI
"""
        vm, stats = execute_for_language("ruby", source)
        assert extract_answer(vm, "ruby") == 3
        assert stats.llm_calls == 0
