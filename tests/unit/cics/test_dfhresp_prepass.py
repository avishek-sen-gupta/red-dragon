# pyright: standard
"""Tests for the DFHRESP expression node pre-pass (red-dragon-kieo)."""

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.dfhresp_prepass import resolve_dfhresp_nodes


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dfhresp_node_in_simple_dict_resolves_to_lit() -> None:
    """A top-level dfhresp node is replaced with a lit node."""
    result = resolve_dfhresp_nodes({"kind": "dfhresp", "condition": "NOTFND"})
    assert result == {"kind": "lit", "value": "13"}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dfhresp_node_pgmiderr_resolves() -> None:
    result = resolve_dfhresp_nodes({"kind": "dfhresp", "condition": "PGMIDERR"})
    assert result == {"kind": "lit", "value": "27"}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dfhresp_node_unknown_resolves_to_sentinel() -> None:
    result = resolve_dfhresp_nodes({"kind": "dfhresp", "condition": "BOGUS"})
    assert result == {"kind": "lit", "value": "9999"}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dfhresp_nested_inside_condition_dict_resolves() -> None:
    """A dfhresp node nested as the right side of a condition is resolved."""
    data = {
        "not": False,
        "relation": {
            "left": {"kind": "ref", "name": "EIBRESP"},
            "op": "==",
            "right": {"kind": "dfhresp", "condition": "NOTFND"},
        },
    }
    result = resolve_dfhresp_nodes(data)
    assert result["relation"]["right"] == {"kind": "lit", "value": "13"}
    assert result["relation"]["left"] == {"kind": "ref", "name": "EIBRESP"}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dfhresp_inside_list_resolves() -> None:
    """dfhresp nodes inside lists (e.g. operands) are resolved."""
    data = [{"kind": "dfhresp", "condition": "NORMAL"}, {"kind": "ref", "name": "X"}]
    result = resolve_dfhresp_nodes(data)
    assert result[0] == {"kind": "lit", "value": "0"}
    assert result[1] == {"kind": "ref", "name": "X"}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_non_dfhresp_nodes_pass_through_unchanged() -> None:
    """Non-dfhresp expression nodes are left intact."""
    data = {
        "kind": "binop",
        "op": "+",
        "left": {"kind": "lit", "value": "1"},
        "right": {"kind": "ref", "name": "X"},
    }
    result = resolve_dfhresp_nodes(data)
    assert result == data


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_scalars_pass_through_unchanged() -> None:
    assert resolve_dfhresp_nodes("NORMAL") == "NORMAL"
    assert resolve_dfhresp_nodes(42) == 42
    assert resolve_dfhresp_nodes(None) is None
