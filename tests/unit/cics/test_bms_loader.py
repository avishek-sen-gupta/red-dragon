"""Unit tests for BMS map loader."""

import tempfile
from pathlib import Path

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.bms.loader import BmsLoader, BmsMap, BmsField


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bms_loader_loads_stub_map():
    loader = BmsLoader(maps_dir=None)
    loader.register_stub(
        "COSGN0A",
        BmsMap(
            name="COSGN0A",
            fields={
                "USERID": BmsField(offset=0, length=8),
                "PASSWORD": BmsField(offset=8, length=8),
            },
        ),
    )
    bms_map = loader.get("COSGN0A")
    assert bms_map is not None
    assert "USERID" in bms_map.fields
    assert bms_map.fields["USERID"].length == 8


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bms_loader_returns_none_for_unknown():
    loader = BmsLoader(maps_dir=None)
    assert loader.get("UNKNOWN") is None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bms_map_renders_dict():
    bms_map = BmsMap(name="COSGN0A", fields={"USERID": BmsField(offset=0, length=8)})
    d = bms_map.to_dict()
    assert d["name"] == "COSGN0A"
    assert "USERID" in d["fields"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bms_loader_from_dir_with_empty_dir():
    with tempfile.TemporaryDirectory() as td:
        loader = BmsLoader(maps_dir=Path(td))
        assert loader.get("ANYTHING") is None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bms_map_extract_fields():
    bms_map = BmsMap(
        name="M",
        fields={
            "A": BmsField(offset=0, length=4),
            "B": BmsField(offset=4, length=4),
        },
    )
    extracted = bms_map.extract_fields(b"AAAABBBB")
    assert extracted["A"] == b"AAAA"
    assert extracted["B"] == b"BBBB"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bms_map_write_fields_pads_and_truncates():
    bms_map = BmsMap(name="M", fields={"A": BmsField(offset=0, length=4)})
    region = bytearray(b"        ")
    bms_map.write_fields(region, {"A": b"XY"})
    assert region[0:4] == b"XY  "  # space-padded to length 4


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bms_loader_parses_bms_file(tmp_path):
    bms = tmp_path / "sgn.bms"
    bms.write_text(
        "COSGN0A  DFHMDI SIZE=(24,80)\n"
        "USERID   DFHMDF POS=(1,1),LENGTH=8\n"
        "PASSWD   DFHMDF POS=(2,1),LENGTH=8\n"
    )
    loader = BmsLoader(maps_dir=tmp_path)
    m = loader.get("COSGN0A")
    assert m is not None
    assert "USERID" in m.fields
    assert m.fields["USERID"].length == 8
    # offset = (row-1)*80 + (col-1); USERID at (1,1) -> 0
    assert m.fields["USERID"].offset == 0
    assert m.fields["PASSWD"].offset == 80
