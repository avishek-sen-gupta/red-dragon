"""SPECIAL-NAMES CLASS clauses: the ASG, the character sets they name and the class test."""

from __future__ import annotations

from cobol_asg.alphabet_item import AlphabetItem
from cobol_asg.alphabet_link import AlphabetLink
from cobol_asg.alphabet_literal_kind import AlphabetLiteralKind
from cobol_asg.asg_types import CobolASG
from cobol_asg.class_definition import ClassDefinition
from interpreter.cobol.byte_builtins import _builtin_is_in_class
from interpreter.cobol.class_name_index import ClassNameIndex
from interpreter.cobol.features import CobolFeature
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm_types import VMState
from tests.covers import covers


def _item(link: str, kind: str, value: str) -> dict[str, str]:
    return {"link": link, "kind": kind, "value": value}


_CLASSES = {
    "special_names": {
        "classes": [
            {
                "name": "A-THRU-D",
                "items": [
                    _item("NONE", "NONNUMERIC", "A"),
                    _item("THRU", "NONNUMERIC", "D"),
                ],
            },
            {
                "name": "D-THRU-A",
                "items": [
                    _item("NONE", "NONNUMERIC", "D"),
                    _item("THRU", "NONNUMERIC", "A"),
                ],
            },
            {
                "name": "ORDINALS",
                "items": [
                    _item("NONE", "NUMERIC", "194"),
                    _item("THRU", "NUMERIC", "197"),
                ],
            },
            {
                "name": "LETTERS",
                "items": [
                    _item("NONE", "NONNUMERIC", "XZ"),
                    _item("NONE", "NUMERIC", "241"),
                ],
            },
        ]
    }
}


@covers(CobolFeature.CLASS_NAME)
def test_class_clauses_parse_round_trip_and_name_native_character_sets() -> None:
    asg = CobolASG.from_dict(_CLASSES)
    index = ClassNameIndex(asg.classes)

    assert asg.classes[0] == ClassDefinition(
        "A-THRU-D",
        (
            AlphabetItem(AlphabetLink.NONE, AlphabetLiteralKind.NONNUMERIC, "A"),
            AlphabetItem(AlphabetLink.THRU, AlphabetLiteralKind.NONNUMERIC, "D"),
        ),
    )
    assert CobolASG.from_dict(asg.to_dict()) == asg
    assert (
        [index.characters(c.name) for c in asg.classes],
        index.has_class("a-thru-d"),
        index.has_class("NUMERIC"),
    ) == (["ABCD", "ABCD", "ABCD", "XZ0"], True, False)


@covers(CobolFeature.CLASS_NAME)
def test_class_test_is_true_only_when_every_character_is_in_the_set() -> None:
    results = [
        _builtin_is_in_class(
            [typed_from_runtime(value), typed_from_runtime("ABCD")], VMState()
        ).value
        for value in ("ADCBA", "ABCDE", "A B", "")
    ]
    assert results == [True, False, False, True]
