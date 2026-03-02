"""Tests for COBOL I/O provider — NullIOProvider and StubIOProvider."""

from interpreter.cobol.io_provider import (
    CobolIOProvider,
    NullIOProvider,
    StubIOProvider,
    StubFile,
)
from interpreter.vm import Operators

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


class TestNullIOProvider:
    def test_accept_returns_uncomputable(self):
        provider = NullIOProvider()
        assert provider.handle_call("__cobol_accept", ["CONSOLE"]) is _UNCOMPUTABLE

    def test_open_returns_uncomputable(self):
        provider = NullIOProvider()
        assert (
            provider.handle_call("__cobol_open_file", ["F1", "INPUT"]) is _UNCOMPUTABLE
        )

    def test_close_returns_uncomputable(self):
        provider = NullIOProvider()
        assert provider.handle_call("__cobol_close_file", ["F1"]) is _UNCOMPUTABLE

    def test_read_returns_uncomputable(self):
        provider = NullIOProvider()
        assert provider.handle_call("__cobol_read_record", ["F1"]) is _UNCOMPUTABLE

    def test_write_returns_uncomputable(self):
        provider = NullIOProvider()
        assert (
            provider.handle_call("__cobol_write_record", ["F1", "DATA"])
            is _UNCOMPUTABLE
        )

    def test_unknown_func_returns_uncomputable(self):
        provider = NullIOProvider()
        assert provider.handle_call("__cobol_bogus", []) is _UNCOMPUTABLE


class TestStubIOProvider:
    def test_accept_returns_queued_values(self):
        provider = StubIOProvider(accept_values=["Y", "JOHN DOE"])
        assert provider.handle_call("__cobol_accept", ["CONSOLE"]) == "Y"
        assert provider.handle_call("__cobol_accept", ["CONSOLE"]) == "JOHN DOE"

    def test_accept_returns_uncomputable_when_empty(self):
        provider = StubIOProvider(accept_values=["ONLY"])
        assert provider.handle_call("__cobol_accept", ["CONSOLE"]) == "ONLY"
        assert provider.handle_call("__cobol_accept", ["CONSOLE"]) is _UNCOMPUTABLE

    def test_read_returns_queued_records(self):
        provider = StubIOProvider(files={"CUST-FILE": {"records": ["REC1", "REC2"]}})
        assert provider.handle_call("__cobol_read_record", ["CUST-FILE"]) == "REC1"
        assert provider.handle_call("__cobol_read_record", ["CUST-FILE"]) == "REC2"

    def test_read_returns_uncomputable_when_exhausted(self):
        provider = StubIOProvider(files={"CUST-FILE": {"records": ["ONLY"]}})
        assert provider.handle_call("__cobol_read_record", ["CUST-FILE"]) == "ONLY"
        assert (
            provider.handle_call("__cobol_read_record", ["CUST-FILE"]) is _UNCOMPUTABLE
        )

    def test_read_unknown_file_returns_uncomputable(self):
        provider = StubIOProvider()
        assert (
            provider.handle_call("__cobol_read_record", ["NONEXISTENT"])
            is _UNCOMPUTABLE
        )

    def test_write_captures_data(self):
        provider = StubIOProvider()
        result = provider.handle_call("__cobol_write_record", ["OUT-FILE", "DATA1"])
        assert result == "DATA1"
        result = provider.handle_call("__cobol_write_record", ["OUT-FILE", "DATA2"])
        assert result == "DATA2"
        assert provider.get_file("OUT-FILE").written == ["DATA1", "DATA2"]

    def test_open_sets_is_open(self):
        provider = StubIOProvider()
        result = provider.handle_call("__cobol_open_file", ["F1", "INPUT"])
        assert result == 0
        assert provider.get_file("F1").is_open is True

    def test_close_clears_is_open(self):
        provider = StubIOProvider(files={"F1": {"records": []}})
        provider.handle_call("__cobol_open_file", ["F1", "INPUT"])
        assert provider.get_file("F1").is_open is True
        provider.handle_call("__cobol_close_file", ["F1"])
        assert provider.get_file("F1").is_open is False

    def test_close_nonexistent_file_is_noop(self):
        provider = StubIOProvider()
        result = provider.handle_call("__cobol_close_file", ["NOPE"])
        assert result == 0

    def test_unknown_func_returns_uncomputable(self):
        provider = StubIOProvider()
        assert provider.handle_call("__cobol_bogus", []) is _UNCOMPUTABLE

    def test_get_file_creates_stub(self):
        provider = StubIOProvider()
        stub = provider.get_file("NEW-FILE")
        assert isinstance(stub, StubFile)
        assert stub.records == []
        assert stub.written == []
        assert stub.is_open is False


class TestStubFile:
    def test_default_values(self):
        stub = StubFile()
        assert stub.records == []
        assert stub.written == []
        assert stub.is_open is False

    def test_with_records(self):
        stub = StubFile(records=["A", "B"], is_open=True)
        assert stub.records == ["A", "B"]
        assert stub.is_open is True
