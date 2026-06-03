import logging
from interpreter.cobol.asg_types import CobolASG, CobolField
from interpreter.cobol.data_layout import DataLayout, build_data_layout
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    build_sectioned_layout,
)
from interpreter.register import Register
from interpreter.cobol.features import CobolFeature
from tests.covers import covers, NotLanguageFeature


def _make_field(name: str, pic: str = "X(5)", offset: int = 0) -> CobolField:
    return CobolField(name=name, level=1, pic=pic, usage="DISPLAY", offset=offset)


def _make_layout(field_name: str, pic: str = "X(5)") -> DataLayout:
    return build_data_layout([_make_field(field_name, pic)])


@covers(CobolFeature.SECTION_LINKAGE)
def test_build_sectioned_layout_all_three_sections():
    asg = CobolASG(
        data_fields=[_make_field("WS-A")],
        linkage_fields=[_make_field("LK-B")],
        local_storage_fields=[_make_field("LS-C")],
    )
    sl = build_sectioned_layout(asg)

    assert sl.working_storage.lookup("WS-A") is not None
    assert sl.linkage.lookup("LK-B") is not None
    assert sl.local_storage.lookup("LS-C") is not None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_build_sectioned_layout_empty_sections():
    asg = CobolASG(data_fields=[_make_field("WS-A")])
    sl = build_sectioned_layout(asg)

    assert sl.working_storage.lookup("WS-A") is not None
    assert sl.linkage.lookup("anything") is None
    assert sl.local_storage.lookup("anything") is None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_materialised_resolve_ws_field():
    ws_layout = _make_layout("WS-X")
    ls_layout = DataLayout()
    lk_layout = DataLayout()
    ws_reg = Register("%r0")
    ls_reg = Register("%r1")
    lk_reg = Register("%r2")

    m = MaterialisedSectionedLayout(
        working_storage=(ws_layout, ws_reg),
        linkage=(lk_layout, lk_reg),
        local_storage=(ls_layout, ls_reg),
    )

    fl, rr = m.resolve("WS-X")
    assert fl.name == "WS-X"
    assert rr == ws_reg


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_materialised_resolve_local_storage_wins_over_ws_on_collision(caplog):
    ws_layout = _make_layout("SHARED-FIELD")
    ls_layout = _make_layout("SHARED-FIELD")
    lk_layout = DataLayout()
    ws_reg = Register("%r0")
    ls_reg = Register("%r1")
    lk_reg = Register("%r2")

    m = MaterialisedSectionedLayout(
        working_storage=(ws_layout, ws_reg),
        linkage=(lk_layout, lk_reg),
        local_storage=(ls_layout, ls_reg),
    )

    with caplog.at_level(logging.WARNING, logger="interpreter.cobol.sectioned_layout"):
        fl, rr = m.resolve("SHARED-FIELD")

    assert rr == ls_reg  # LOCAL-STORAGE wins
    assert any(
        "collision" in r.message.lower() or "SHARED-FIELD" in r.message
        for r in caplog.records
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_materialised_resolve_raises_key_error_for_unknown_field():
    m = MaterialisedSectionedLayout(
        working_storage=(DataLayout(), Register("%r0")),
        linkage=(DataLayout(), Register("%r1")),
        local_storage=(DataLayout(), Register("%r2")),
    )
    import pytest

    with pytest.raises(KeyError, match="UNKNOWN"):
        m.resolve("UNKNOWN")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_materialised_has_field():
    ws_layout = _make_layout("WS-X")
    ls_layout = DataLayout()
    lk_layout = _make_layout("LK-Y")
    m = MaterialisedSectionedLayout(
        working_storage=(ws_layout, Register("%r0")),
        linkage=(lk_layout, Register("%r1")),
        local_storage=(ls_layout, Register("%r2")),
    )

    assert m.has_field("WS-X")
    assert m.has_field("LK-Y")
    assert not m.has_field("MISSING")
