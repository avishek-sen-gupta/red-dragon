"""Tests for COBOL I/O provider — NullIOProvider and StubIOProvider."""

from interpreter.cobol.io_provider import (
    CobolIOProvider,
    NullIOProvider,
    StubIOProvider,
    StubFile,
)
from interpreter.typed_value import typed_from_runtime
from interpreter.vm import Operators

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


class TestNullIOProvider:
    def test_accept_returns_uncomputable(self):
        provider = NullIOProvider()
        assert (
            provider.handle_call("__cobol_accept", [typed_from_runtime("CONSOLE")])
            is _UNCOMPUTABLE
        )

    def test_open_returns_uncomputable(self):
        provider = NullIOProvider()
        assert (
            provider.handle_call(
                "__cobol_open_file",
                [typed_from_runtime("F1"), typed_from_runtime("INPUT")],
            )
            is _UNCOMPUTABLE
        )

    def test_close_returns_uncomputable(self):
        provider = NullIOProvider()
        assert (
            provider.handle_call("__cobol_close_file", [typed_from_runtime("F1")])
            is _UNCOMPUTABLE
        )

    def test_read_returns_uncomputable(self):
        provider = NullIOProvider()
        assert (
            provider.handle_call("__cobol_read_record", [typed_from_runtime("F1")])
            is _UNCOMPUTABLE
        )

    def test_write_returns_uncomputable(self):
        provider = NullIOProvider()
        assert (
            provider.handle_call(
                "__cobol_write_record",
                [typed_from_runtime("F1"), typed_from_runtime("DATA")],
            )
            is _UNCOMPUTABLE
        )

    def test_rewrite_returns_uncomputable(self):
        provider = NullIOProvider()
        assert (
            provider.handle_call(
                "__cobol_rewrite_record",
                [typed_from_runtime("F1"), typed_from_runtime("DATA")],
            )
            is _UNCOMPUTABLE
        )

    def test_start_returns_uncomputable(self):
        provider = NullIOProvider()
        assert (
            provider.handle_call(
                "__cobol_start_file",
                [typed_from_runtime("F1"), typed_from_runtime("KEY1")],
            )
            is _UNCOMPUTABLE
        )

    def test_delete_returns_uncomputable(self):
        provider = NullIOProvider()
        assert (
            provider.handle_call("__cobol_delete_record", [typed_from_runtime("F1")])
            is _UNCOMPUTABLE
        )

    def test_unknown_func_returns_uncomputable(self):
        provider = NullIOProvider()
        assert provider.handle_call("__cobol_bogus", []) is _UNCOMPUTABLE


class TestStubIOProvider:
    def test_accept_returns_queued_values(self):
        provider = StubIOProvider(accept_values=["Y", "JOHN DOE"])
        assert (
            provider.handle_call("__cobol_accept", [typed_from_runtime("CONSOLE")])
            == "Y"
        )
        assert (
            provider.handle_call("__cobol_accept", [typed_from_runtime("CONSOLE")])
            == "JOHN DOE"
        )

    def test_accept_returns_uncomputable_when_empty(self):
        provider = StubIOProvider(accept_values=["ONLY"])
        assert (
            provider.handle_call("__cobol_accept", [typed_from_runtime("CONSOLE")])
            == "ONLY"
        )
        assert (
            provider.handle_call("__cobol_accept", [typed_from_runtime("CONSOLE")])
            is _UNCOMPUTABLE
        )

    def test_read_returns_queued_records(self):
        provider = StubIOProvider(files={"CUST-FILE": {"records": ["REC1", "REC2"]}})
        assert (
            provider.handle_call(
                "__cobol_read_record", [typed_from_runtime("CUST-FILE")]
            )
            == "REC1"
        )
        assert (
            provider.handle_call(
                "__cobol_read_record", [typed_from_runtime("CUST-FILE")]
            )
            == "REC2"
        )

    def test_read_returns_uncomputable_when_exhausted(self):
        provider = StubIOProvider(files={"CUST-FILE": {"records": ["ONLY"]}})
        assert (
            provider.handle_call(
                "__cobol_read_record", [typed_from_runtime("CUST-FILE")]
            )
            == "ONLY"
        )
        assert (
            provider.handle_call(
                "__cobol_read_record", [typed_from_runtime("CUST-FILE")]
            )
            is _UNCOMPUTABLE
        )

    def test_read_unknown_file_returns_uncomputable(self):
        provider = StubIOProvider()
        assert (
            provider.handle_call(
                "__cobol_read_record", [typed_from_runtime("NONEXISTENT")]
            )
            is _UNCOMPUTABLE
        )

    def test_write_captures_data(self):
        provider = StubIOProvider()
        result = provider.handle_call(
            "__cobol_write_record",
            [typed_from_runtime("OUT-FILE"), typed_from_runtime("DATA1")],
        )
        assert result == "DATA1"
        result = provider.handle_call(
            "__cobol_write_record",
            [typed_from_runtime("OUT-FILE"), typed_from_runtime("DATA2")],
        )
        assert result == "DATA2"
        assert provider.get_file("OUT-FILE").written == ["DATA1", "DATA2"]

    def test_open_sets_is_open(self):
        provider = StubIOProvider()
        result = provider.handle_call(
            "__cobol_open_file", [typed_from_runtime("F1"), typed_from_runtime("INPUT")]
        )
        assert result == 0
        assert provider.get_file("F1").is_open is True

    def test_close_clears_is_open(self):
        provider = StubIOProvider(files={"F1": {"records": []}})
        provider.handle_call(
            "__cobol_open_file", [typed_from_runtime("F1"), typed_from_runtime("INPUT")]
        )
        assert provider.get_file("F1").is_open is True
        provider.handle_call("__cobol_close_file", [typed_from_runtime("F1")])
        assert provider.get_file("F1").is_open is False

    def test_close_nonexistent_file_is_noop(self):
        provider = StubIOProvider()
        result = provider.handle_call(
            "__cobol_close_file", [typed_from_runtime("NOPE")]
        )
        assert result == 0

    def test_unknown_func_returns_uncomputable(self):
        provider = StubIOProvider()
        assert provider.handle_call("__cobol_bogus", []) is _UNCOMPUTABLE

    def test_rewrite_replaces_last_written(self):
        provider = StubIOProvider()
        provider.handle_call(
            "__cobol_write_record",
            [typed_from_runtime("F1"), typed_from_runtime("OLD")],
        )
        result = provider.handle_call(
            "__cobol_rewrite_record",
            [typed_from_runtime("F1"), typed_from_runtime("NEW")],
        )
        assert result == "NEW"
        assert provider.get_file("F1").written == ["NEW"]

    def test_rewrite_appends_when_no_prior_writes(self):
        provider = StubIOProvider()
        result = provider.handle_call(
            "__cobol_rewrite_record",
            [typed_from_runtime("F1"), typed_from_runtime("DATA")],
        )
        assert result == "DATA"
        assert provider.get_file("F1").written == ["DATA"]

    def test_start_returns_zero(self):
        provider = StubIOProvider()
        result = provider.handle_call(
            "__cobol_start_file", [typed_from_runtime("F1"), typed_from_runtime("KEY1")]
        )
        assert result == 0

    def test_delete_removes_first_record(self):
        provider = StubIOProvider(files={"F1": {"records": ["REC1", "REC2"]}})
        result = provider.handle_call(
            "__cobol_delete_record", [typed_from_runtime("F1")]
        )
        assert result == "REC1"
        assert provider.get_file("F1").records == ["REC2"]

    def test_delete_returns_uncomputable_when_no_records(self):
        provider = StubIOProvider(files={"F1": {"records": []}})
        assert (
            provider.handle_call("__cobol_delete_record", [typed_from_runtime("F1")])
            is _UNCOMPUTABLE
        )

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
