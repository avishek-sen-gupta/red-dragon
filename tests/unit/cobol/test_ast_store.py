# pyright: standard
from pathlib import Path

import pytest

import interpreter.cobol.ast_store as ast_store_module
from interpreter.cobol.ast_store import AstStore, AstStrategy

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


@pytest.mark.parametrize("strategy", [AstStrategy.MEMORY, AstStrategy.DISK])
def test_get_returns_parsed_asg(tmp_path, strategy):
    parser = _FakeParser()
    store = AstStore(strategy, cache_dir=tmp_path, max_workers=2)
    p = Path("HELLO.cbl")
    store.parse_all({p: _SRC}, parser)
    asg = store.get(p)
    assert asg["program_id"] == "HELLO"
    store.close()


@pytest.mark.parametrize("strategy", [AstStrategy.MEMORY, AstStrategy.DISK])
def test_memory_and_disk_apply_preprocessor_identically(tmp_path, strategy):
    parser = _FakeParser()
    store = AstStore(strategy, cache_dir=tmp_path)
    p = Path("HELLO.cbl")
    store.parse_all({p: _SRC}, parser, preprocessor=lambda d: {**d, "tag": "X"})
    assert store.get(p)["tag"] == "X"  # DISK must apply the preprocessor on load too
    store.close()


def test_full_hex_key_no_truncation(tmp_path):
    # the store keys on the FULL 32-char md5 hex — truncation ([:8]) collides at scale
    from interpreter.cobol.ast_store import _key

    a, b = Path("A.cbl"), Path("B.cbl")
    assert len(_key(a)) == 32  # full hex, not truncated
    assert _key(a) != _key(b)  # distinct paths -> distinct keys

    parser = _FakeParser()
    store = AstStore(AstStrategy.DISK, cache_dir=tmp_path)
    store.parse_all(
        {a: b"       PROGRAM-ID. A.\n", b: b"       PROGRAM-ID. BB.\n"}, parser
    )
    # distinct entries retrieved without collision (sources differ in length)
    assert store.get(a)["src_len"] != store.get(b)["src_len"]
    store.close()
