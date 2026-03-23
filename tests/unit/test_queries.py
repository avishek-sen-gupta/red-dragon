"""Unit tests for interprocedural query interface."""

import pytest

from interpreter.ir import CodeLabel
from interpreter.interprocedural.queries import (
    backward_slice,
    forward_slice,
    impact_of,
    taint_path,
    taint_reaches,
)
from interpreter.interprocedural.types import (
    CallGraph,
    FieldEndpoint,
    FunctionEntry,
    InterproceduralResult,
    NO_DEFINITION,
    NO_INSTRUCTION_LOC,
    ReturnEndpoint,
    VariableEndpoint,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def endpoints():
    a = VariableEndpoint(name="a", definition=NO_DEFINITION)
    b = VariableEndpoint(name="b", definition=NO_DEFINITION)
    c = VariableEndpoint(name="c", definition=NO_DEFINITION)
    d = VariableEndpoint(name="d", definition=NO_DEFINITION)
    f_entry = FunctionEntry(label=CodeLabel("func__f"), params=("x",))
    ret = ReturnEndpoint(function=f_entry, location=NO_INSTRUCTION_LOC)
    field = FieldEndpoint(base=a, field="name", location=NO_INSTRUCTION_LOC)
    return {"a": a, "b": b, "c": c, "d": d, "ret": ret, "field": field}


@pytest.fixture()
def result(endpoints):
    a, b, c, d, field = (
        endpoints["a"],
        endpoints["b"],
        endpoints["c"],
        endpoints["d"],
        endpoints["field"],
    )
    # a → b → c, a → field, d isolated
    raw = {a: frozenset({b, field}), b: frozenset({c})}
    transitive = {a: frozenset({b, c, field}), b: frozenset({c})}

    return InterproceduralResult(
        call_graph=CallGraph(functions=frozenset(), call_sites=frozenset()),
        summaries={},
        whole_program_graph=transitive,
        raw_program_graph=raw,
    )


# ---------------------------------------------------------------------------
# impact_of tests
# ---------------------------------------------------------------------------


def test_impact_of_a_returns_transitive_closure(result, endpoints):
    assert impact_of(result, endpoints["a"]) == frozenset(
        {endpoints["b"], endpoints["c"], endpoints["field"]}
    )


def test_impact_of_isolated_node_returns_empty(result, endpoints):
    assert impact_of(result, endpoints["d"]) == frozenset()


def test_impact_of_leaf_node_returns_empty(result, endpoints):
    assert impact_of(result, endpoints["c"]) == frozenset()


# ---------------------------------------------------------------------------
# taint_reaches tests
# ---------------------------------------------------------------------------


def test_taint_reaches_a_to_c_is_true(result, endpoints):
    assert taint_reaches(result, endpoints["a"], endpoints["c"]) is True


def test_taint_reaches_a_to_d_is_false(result, endpoints):
    assert taint_reaches(result, endpoints["a"], endpoints["d"]) is False


def test_taint_reaches_d_to_a_is_false(result, endpoints):
    assert taint_reaches(result, endpoints["d"], endpoints["a"]) is False


# ---------------------------------------------------------------------------
# taint_path tests
# ---------------------------------------------------------------------------


def test_taint_path_a_to_c_via_bfs(result, endpoints):
    path = taint_path(result, endpoints["a"], endpoints["c"])
    assert path == (endpoints["a"], endpoints["b"], endpoints["c"])


def test_taint_path_unreachable_returns_empty_tuple(result, endpoints):
    path = taint_path(result, endpoints["a"], endpoints["d"])
    assert path == ()


def test_taint_path_direct_edge(result, endpoints):
    path = taint_path(result, endpoints["a"], endpoints["field"])
    assert path == (endpoints["a"], endpoints["field"])


# ---------------------------------------------------------------------------
# backward_slice tests
# ---------------------------------------------------------------------------


def test_backward_slice_c_returns_a_and_b(result, endpoints):
    assert backward_slice(result, endpoints["c"]) == frozenset(
        {endpoints["a"], endpoints["b"]}
    )


def test_backward_slice_a_returns_empty(result, endpoints):
    assert backward_slice(result, endpoints["a"]) == frozenset()


# ---------------------------------------------------------------------------
# forward_slice tests
# ---------------------------------------------------------------------------


def test_forward_slice_a_returns_all_reachable(result, endpoints):
    assert forward_slice(result, endpoints["a"]) == frozenset(
        {endpoints["b"], endpoints["c"], endpoints["field"]}
    )
