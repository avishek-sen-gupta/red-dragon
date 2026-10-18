"""Figurative constants arrive as written; the ASG reader names each canonically."""

from cobol_asg.figurative_names import with_canonical_figuratives


def _fig(value: str) -> dict:
    return {"kind": "figurative", "value": value}


def test_every_spelling_of_a_constant_reads_as_its_plural_name() -> None:
    written = {
        "data_fields": [{"name": "X", "value": "ZERO", "kind": "figurative"}],
        "statements": [
            {
                "type": "IF",
                "condition": {
                    "relation": {
                        "left": _fig("SPACE"),
                        "op": "==",
                        "right": _fig("ZEROES"),
                    }
                },
                "operands": [
                    _fig(v)
                    for v in ("LOW-VALUE", "HIGH-VALUE", "QUOTE", "NULLS", "ZERO")
                ],
            },
            {
                "type": "MOVE",
                "operands": [{"kind": "lit", "value": "ZERO"}, _fig("ALL")],
            },
        ],
    }

    assert with_canonical_figuratives(written) == {
        "data_fields": [{"name": "X", "value": "ZERO", "kind": "figurative"}],
        "statements": [
            {
                "type": "IF",
                "condition": {
                    "relation": {
                        "left": _fig("SPACES"),
                        "op": "==",
                        "right": _fig("ZEROS"),
                    }
                },
                "operands": [
                    _fig(v)
                    for v in ("LOW-VALUES", "HIGH-VALUES", "QUOTES", "NULL", "ZEROS")
                ],
            },
            {
                "type": "MOVE",
                "operands": [{"kind": "lit", "value": "ZERO"}, _fig("ALL")],
            },
        ],
    }
