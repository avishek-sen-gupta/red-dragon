"""A condition as the bridge writes it, resolved into the AND/OR tree."""

from cobol_asg.abbreviated_condition import resolve_condition


def _ref(name: str) -> dict:
    return {"kind": "ref", "name": name}


def _rel(left: str, op: str, right: str, negated: bool = False) -> dict:
    return {
        "not": negated,
        "relation": {"left": _ref(left), "op": op, "right": _ref(right)},
    }


def _abbreviation(right: str, negated: bool, op: str = "") -> dict:
    return {"not": negated, "right": _ref(right)} | ({"op": op} if op else {})


def test_abbreviations_take_the_last_stated_subject_and_operator() -> None:
    written = {
        "first": _rel("A", ">", "B"),
        "rest": [
            {
                "bool": "AND",
                "abbreviations": [
                    _abbreviation("C", True, "<"),
                    _abbreviation("D", True),
                ],
            },
            {"bool": "OR", "atom": {"not": False, "condition_name": "E"}},
            {"bool": "AND", "atom": {"not": True, "condition_name": "F"}},
            {"bool": "OR", "abbreviations": [_abbreviation("G", False, "==")]},
        ],
    }

    implied = {"left": _ref("A"), "op": ">="}
    assert resolve_condition(written) == {
        "op": "OR",
        "left": {
            "op": "OR",
            "left": {
                "op": "AND",
                "left": _rel("A", ">", "B"),
                "right": {
                    "op": "AND",
                    "left": _rel("A", ">=", "C"),
                    "right": _rel("A", ">=", "D", negated=True),
                },
            },
            "right": {
                "op": "AND",
                "left": {"not": False, "condition_name": "E", "abbreviation": implied},
                "right": {"not": True, "condition_name": "F", "abbreviation": implied},
            },
        },
        "right": _rel("A", "==", "G"),
    }


def test_combined_and_nested_relations_expand_and_a_resolved_tree_is_kept() -> None:
    combined = {
        "left": _ref("X"),
        "op": "<",
        "bool": "OR",
        "operands": [_ref("Y"), _ref("Z")],
    }
    written = {
        "first": {"not": True, "combined": combined},
        "rest": [
            {
                "bool": "AND",
                "atom": {
                    "not": False,
                    "condition": {
                        "first": {"not": False, "condition_name": "K"},
                        "rest": [],
                    },
                },
            },
            {"bool": "AND", "abbreviations": [_abbreviation("W", False)]},
        ],
    }
    resolved = {
        "op": "AND",
        "left": {
            "op": "AND",
            "left": {
                "not": True,
                "condition": {
                    "op": "OR",
                    "left": _rel("X", "<", "Y"),
                    "right": _rel("X", "<", "Z"),
                },
            },
            "right": {"not": False, "condition": {"not": False, "condition_name": "K"}},
        },
        "right": {"text": ""},
    }

    assert resolve_condition(written) == resolved
    assert resolve_condition(resolved) == resolved
