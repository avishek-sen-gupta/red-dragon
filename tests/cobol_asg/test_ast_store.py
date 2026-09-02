# pyright: standard
from pathlib import Path

import pytest

import cobol_asg.ast_store as ast_store_module
from cobol_asg.ast_store import AstStore, temp_ast_store

_SRC = b"       IDENTIFICATION DIVISION.\n       PROGRAM-ID. HELLO.\n"


class _FakeParser:
    """Stand-in for ProLeapCobolParser: parse() returns a sentinel ASG, parse_to_file
    writes a JSON dict that CobolASG.from_dict can round-trip via a fake from_dict."""

    def __init__(self):
        self.parse_calls = 0

    def parse(self, source: bytes, preprocessor=lambda d: d):
        self.parse_calls += 1
        return preprocessor({"program_id": "HELLO", "src_len": len(source)})

    def parse_to_file(self, source: bytes, out_path: Path) -> Path:
        import json

        out_path.write_text(json.dumps({"program_id": "HELLO", "src_len": len(source)}))
        return out_path


class _StubCobolASG:
    """Echoes the dict back instead of constructing a real (strict) CobolASG.

    Keeps this unit test JVM-free and decoupled from ASG internals — the real
    CobolASG.from_dict builds a frozen dataclass (not subscriptable, and it
    silently drops unknown keys like "src_len"/"tag"), which is the wrong
    contract for a fake-parser unit test that only cares about AstStore's
    caching/keying/preprocessor behavior.
    """

    @staticmethod
    def from_dict(data: dict) -> dict:
        return data


@pytest.fixture(autouse=True)
def _stub_cobol_asg(monkeypatch):
    monkeypatch.setattr(ast_store_module, "CobolASG", _StubCobolASG)


def test_get_returns_parsed_asg(tmp_path):
    parser = _FakeParser()
    store = AstStore(tmp_path, max_workers=2)
    p = Path("HELLO.cbl")
    store.parse_all({p: _SRC}, parser)
    asg = store.get(p)
    assert asg["program_id"] == "HELLO"


def test_preprocessor_is_applied_on_load(tmp_path):
    # Only the raw bridge JSON is cached, so the preprocessor has to run in
    # get() -- nothing else ever sees the dict.
    parser = _FakeParser()
    store = AstStore(tmp_path)
    p = Path("HELLO.cbl")
    store.parse_all({p: _SRC}, parser, preprocessor=lambda d: {**d, "tag": "X"})
    assert store.get(p)["tag"] == "X"


def test_temp_ast_store_removes_its_cache_on_the_way_out():
    with temp_ast_store() as store:
        cache_dir = store.cache_dir
        store.parse_all({Path("HELLO.cbl"): _SRC}, _FakeParser())
        assert cache_dir.is_dir()
    assert not cache_dir.exists()


def test_parse_failure_names_the_member(tmp_path):
    # The bridge names the temp file it was handed, not the corpus member, so a
    # failure thousands of subprocesses deep is unattributable without this.
    from cobol_asg.ast_store import AstParseError

    class _Exploding:
        def parse_to_file(self, source: bytes, out: Path) -> None:
            raise RuntimeError("bridge said no")

    store = AstStore(tmp_path)
    with pytest.raises(AstParseError, match="HELLO.cbl: RuntimeError: bridge said no"):
        store.parse_all({Path("HELLO.cbl"): _SRC}, _Exploding())


def test_full_hex_key_no_truncation(tmp_path):
    # the store keys on the FULL 32-char md5 hex — truncation ([:8]) collides at scale
    from cobol_asg.ast_store import _digest

    a, b = Path("A.cbl"), Path("B.cbl")
    assert len(_digest(a)) == 32  # full hex, not truncated
    assert _digest(a) != _digest(b)  # distinct paths -> distinct keys

    parser = _FakeParser()
    store = AstStore(tmp_path)
    store.parse_all(
        {a: b"       PROGRAM-ID. A.\n", b: b"       PROGRAM-ID. BB.\n"}, parser
    )
    # distinct entries retrieved without collision (sources differ in length)
    assert store.get(a)["src_len"] != store.get(b)["src_len"]
