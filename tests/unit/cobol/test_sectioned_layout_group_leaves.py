"""MaterialisedSectionedLayout exposes a group's leaf field names."""

from __future__ import annotations

from interpreter.cobol.data_layout import DataLayout, FieldLayout
from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.register import Register
from tests.covers import covers, NotLanguageFeature


def _alpha(n: int) -> CobolTypeDescriptor:
    return CobolTypeDescriptor(category=CobolDataCategory.ALPHANUMERIC, total_digits=n)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_group_leaf_names_returns_children_in_order() -> None:
    grp = DataLayout(
        fields={
            "USERIDO": FieldLayout(
                name="USERIDO", type_descriptor=_alpha(8), offset=12, byte_length=8
            ),
            "ERRMSGO": FieldLayout(
                name="ERRMSGO", type_descriptor=_alpha(78), offset=20, byte_length=78
            ),
        },
        offset=0,
        total_bytes=98,
    )
    ws = DataLayout(groups={"COSGN0AO": grp}, offset=0, total_bytes=98)
    empty = DataLayout()
    mat = MaterialisedSectionedLayout(
        working_storage=(ws, Register("%ws")),
        linkage=(empty, Register("%lk")),
        local_storage=(empty, Register("%ls")),
    )
    assert mat.group_leaf_names("COSGN0AO") == ["USERIDO", "ERRMSGO"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_group_leaf_names_missing_group_returns_empty() -> None:
    empty = DataLayout()
    mat = MaterialisedSectionedLayout(
        working_storage=(empty, Register("%ws")),
        linkage=(empty, Register("%lk")),
        local_storage=(empty, Register("%ls")),
    )
    assert mat.group_leaf_names("NOPE") == []
