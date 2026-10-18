# pyright: standard
import json
from pathlib import Path

import pytest

from cobol_asg.ast_store import AstStore, temp_ast_store

_SRC = b"       IDENTIFICATION DIVISION.\n       PROGRAM-ID. HELLO.\n"


class _FakeParser:
    """Stand-in for ProLeapCobolParser: parse_to_file writes a one-program
    compilation unit whose PROGRAM-ID is the source's text after PROGRAM-ID."""

    def parse_to_file(self, source: bytes, out_path: Path) -> Path:
        program_id = source.decode().split("PROGRAM-ID.")[1].strip().rstrip(".")
        out_path.write_text(json.dumps({"programs": [{"program_id": program_id}]}))
        return out_path


def test_get_returns_parsed_compilation_unit(tmp_path):
    parser = _FakeParser()
    store = AstStore(tmp_path, max_workers=2)
    p = Path("HELLO.cbl")
    store.parse_all({p: _SRC}, parser)
    assert [program.program_id for program in store.get(p).programs] == ["HELLO"]


def test_preprocessor_is_applied_on_load(tmp_path):
    # Only the raw bridge JSON is cached, so the preprocessor has to run in
    # get() -- nothing else ever sees the dict.
    parser = _FakeParser()
    store = AstStore(tmp_path)
    p = Path("HELLO.cbl")
    store.parse_all(
        {p: _SRC}, parser, preprocessor=lambda d: {**d, "program_id": "TAGGED"}
    )
    assert store.get(p).first_program.program_id == "TAGGED"


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
        def parse_to_file(self, source: bytes, out_path: Path) -> Path:
            raise RuntimeError("bridge said no")

    store = AstStore(tmp_path)
    with pytest.raises(
        AstParseError, match=r"HELLO\.cbl: RuntimeError: bridge said no"
    ):
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
    assert (
        store.get(a).first_program.program_id,
        store.get(b).first_program.program_id,
    ) == ("A", "BB")
