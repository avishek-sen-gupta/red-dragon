"""Integration tests for C++ frontend: constructor field storage, structured bindings."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.frontends.cpp.features import CppFeature
from interpreter.var_name import VarName
from tests.covers import covers
from tests.integration.exec_helpers import run_locals


def _run_cpp(source: str, max_steps: int = 500) -> dict:
    return run_locals(source, Language.CPP, max_steps)


class TestCppConstructorFieldExecution:
    """Constructor without explicit 'this' param produces correct field values."""

    @covers(CppFeature.THIS_POINTER)
    @covers(CppFeature.ARROW_OPERATOR)
    def test_field_access_on_constructed_object(self):
        """Constructing a class and accessing a field should return
        a concrete value (not SymbolicValue)."""
        vars_ = _run_cpp("""\
class Box {
public:
    int x;
    Box(int x) {
        this->x = x;
    }
};

Box* b = new Box(42);
int answer = b->x;
""")
        assert vars_[VarName("answer")] == 42

    @covers(CppFeature.POINTER_TYPE)
    @covers(CppFeature.ARROW_OPERATOR)
    @covers(CppFeature.NULLPTR)
    def test_linked_list_field_traversal(self):
        """Linked list with class nodes should allow field traversal
        to produce concrete sum."""
        vars_ = _run_cpp(
            """\
class Node {
public:
    int value;
    Node* nextNode;

    Node(int value, Node* nextNode) {
        this->value = value;
        this->nextNode = nextNode;
    }
};

int sumList(Node* node, int count) {
    if (count <= 0) {
        return 0;
    }
    return node->value + sumList(node->nextNode, count - 1);
}

Node* n3 = new Node(3, nullptr);
Node* n2 = new Node(2, n3);
Node* n1 = new Node(1, n2);
int answer = sumList(n1, 3);
""",
            max_steps=1000,
        )
        assert vars_[VarName("answer")] == 6


class TestCppStructuredBindingExecution:
    """auto [a, b] = expr; should decompose and bind correct values."""

    @covers(CppFeature.STRUCTURED_BINDING)
    @covers(CppFeature.ARRAY_LITERALS)
    def test_structured_binding_from_array(self):
        """auto [a, b] = arr; binds elements by position."""
        vars_ = _run_cpp("""\
int arr[2] = {10, 20};
auto [a, b] = arr;
int sum = a + b;
""")
        assert vars_[VarName("a")] == 10
        assert vars_[VarName("b")] == 20
        assert vars_[VarName("sum")] == 30

    @covers(CppFeature.STRUCTURED_BINDING)
    @covers(CppFeature.ARRAY_LITERALS)
    def test_structured_binding_three_elements(self):
        """auto [x, y, z] = arr; with three elements."""
        vars_ = _run_cpp("""\
int arr[3] = {1, 2, 3};
auto [x, y, z] = arr;
int total = x + y + z;
""")
        assert vars_[VarName("total")] == 6
