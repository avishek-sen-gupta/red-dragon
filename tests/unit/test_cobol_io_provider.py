"""Tests for COBOL I/O provider — NullIOProvider and StubIOProvider."""

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.io_provider import (
    IOResult,
    NullIOProvider,
    StubFile,
    StubIOProvider,
)
from interpreter.func_name import FuncName
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm import Operators
from tests.covers import covers

_UNCOMPUTABLE = Operators.UNCOMPUTABLE

# Helpers for building typed args for _open_file (filename, mode, record_length, organization, key_offset, key_length)
_OPEN_ARGS = [
    typed_from_runtime("F1"),
    typed_from_runtime("INPUT"),
    typed_from_runtime(80),
    typed_from_runtime("SEQUENTIAL"),
    typed_from_runtime(0),
    typed_from_runtime(0),
]

# _read_record now takes (filename, key)
_READ_ARGS_F1 = [typed_from_runtime("F1"), typed_from_runtime("")]

# _start_file now takes (filename, key, relop)
_START_ARGS_F1 = [
    typed_from_runtime("F1"),
    typed_from_runtime("KEY1"),
    typed_from_runtime(">="),
]


class TestNullIOProvider:
    @covers(CobolFeature.IO_PROVIDER, CobolFeature.ACCEPT)
    def test_accept_returns_uncomputable(self):
        provider = NullIOProvider()
        assert (
            provider.handle_call(
                FuncName("__cobol_accept"), [typed_from_runtime("CONSOLE")]
            )
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.OPEN)
    def test_open_returns_io_result_ok(self):
        provider = NullIOProvider()
        result = provider.handle_call(FuncName("__cobol_open_file"), _OPEN_ARGS)
        assert result == IOResult("00", None)

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.CLOSE)
    def test_close_returns_io_result_ok(self):
        provider = NullIOProvider()
        result = provider.handle_call(
            FuncName("__cobol_close_file"), [typed_from_runtime("F1")]
        )
        assert result == IOResult("00", None)

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.READ)
    def test_read_returns_uncomputable(self):
        provider = NullIOProvider()
        assert (
            provider.handle_call(FuncName("__cobol_read_record"), _READ_ARGS_F1)
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.WRITE)
    def test_write_returns_io_result_ok(self):
        provider = NullIOProvider()
        result = provider.handle_call(
            FuncName("__cobol_write_record"),
            [typed_from_runtime("F1"), typed_from_runtime("DATA")],
        )
        assert result == IOResult("00", None)

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.REWRITE)
    def test_rewrite_returns_io_result_ok(self):
        provider = NullIOProvider()
        result = provider.handle_call(
            FuncName("__cobol_rewrite_record"),
            [typed_from_runtime("F1"), typed_from_runtime("DATA")],
        )
        assert result == IOResult("00", None)

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.START)
    def test_start_returns_io_result_ok(self):
        provider = NullIOProvider()
        result = provider.handle_call(FuncName("__cobol_start_file"), _START_ARGS_F1)
        assert result == IOResult("00", None)

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.DELETE_RECORD)
    def test_delete_returns_io_result_ok(self):
        provider = NullIOProvider()
        result = provider.handle_call(
            FuncName("__cobol_delete_record"), [typed_from_runtime("F1")]
        )
        assert result == IOResult("00", None)

    @covers(CobolFeature.IO_PROVIDER)
    def test_unknown_func_returns_uncomputable(self):
        provider = NullIOProvider()
        assert provider.handle_call(FuncName("__cobol_bogus"), []) is _UNCOMPUTABLE


class TestStubIOProvider:
    @covers(CobolFeature.IO_PROVIDER, CobolFeature.ACCEPT)
    def test_accept_returns_queued_values(self):
        provider = StubIOProvider(accept_values=["Y", "JOHN DOE"])
        assert (
            provider.handle_call(
                FuncName("__cobol_accept"), [typed_from_runtime("CONSOLE")]
            )
            == "Y"
        )
        assert (
            provider.handle_call(
                FuncName("__cobol_accept"), [typed_from_runtime("CONSOLE")]
            )
            == "JOHN DOE"
        )

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.ACCEPT)
    def test_accept_returns_uncomputable_when_empty(self):
        provider = StubIOProvider(accept_values=["ONLY"])
        assert (
            provider.handle_call(
                FuncName("__cobol_accept"), [typed_from_runtime("CONSOLE")]
            )
            == "ONLY"
        )
        assert (
            provider.handle_call(
                FuncName("__cobol_accept"), [typed_from_runtime("CONSOLE")]
            )
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.READ)
    def test_read_returns_queued_records(self):
        provider = StubIOProvider(files={"CUST-FILE": {"records": ["REC1", "REC2"]}})
        result1 = provider.handle_call(
            FuncName("__cobol_read_record"),
            [typed_from_runtime("CUST-FILE"), typed_from_runtime("")],
        )
        assert result1 == IOResult("00", "REC1")
        result2 = provider.handle_call(
            FuncName("__cobol_read_record"),
            [typed_from_runtime("CUST-FILE"), typed_from_runtime("")],
        )
        assert result2 == IOResult("00", "REC2")

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.READ)
    def test_read_returns_at_end_when_exhausted(self):
        provider = StubIOProvider(files={"CUST-FILE": {"records": ["ONLY"]}})
        assert provider.handle_call(
            FuncName("__cobol_read_record"),
            [typed_from_runtime("CUST-FILE"), typed_from_runtime("")],
        ) == IOResult("00", "ONLY")
        assert provider.handle_call(
            FuncName("__cobol_read_record"),
            [typed_from_runtime("CUST-FILE"), typed_from_runtime("")],
        ) == IOResult("10", None)

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.READ)
    def test_read_unknown_file_returns_at_end(self):
        provider = StubIOProvider()
        result = provider.handle_call(
            FuncName("__cobol_read_record"),
            [typed_from_runtime("NONEXISTENT"), typed_from_runtime("")],
        )
        assert result == IOResult("10", None)

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.WRITE)
    def test_write_captures_data(self):
        provider = StubIOProvider()
        result = provider.handle_call(
            FuncName("__cobol_write_record"),
            [typed_from_runtime("OUT-FILE"), typed_from_runtime("DATA1")],
        )
        assert result == IOResult("00", None)
        result = provider.handle_call(
            FuncName("__cobol_write_record"),
            [typed_from_runtime("OUT-FILE"), typed_from_runtime("DATA2")],
        )
        assert result == IOResult("00", None)
        assert provider.get_file("OUT-FILE").written == ["DATA1", "DATA2"]

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.OPEN)
    def test_open_sets_is_open(self):
        provider = StubIOProvider()
        result = provider.handle_call(
            FuncName("__cobol_open_file"),
            [
                typed_from_runtime("F1"),
                typed_from_runtime("INPUT"),
                typed_from_runtime(80),
                typed_from_runtime("SEQUENTIAL"),
                typed_from_runtime(0),
                typed_from_runtime(0),
            ],
        )
        assert result == IOResult("00", None)
        assert provider.get_file("F1").is_open is True

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.OPEN, CobolFeature.CLOSE)
    def test_close_clears_is_open(self):
        provider = StubIOProvider(files={"F1": {"records": []}})
        provider.handle_call(
            FuncName("__cobol_open_file"),
            [
                typed_from_runtime("F1"),
                typed_from_runtime("INPUT"),
                typed_from_runtime(80),
                typed_from_runtime("SEQUENTIAL"),
                typed_from_runtime(0),
                typed_from_runtime(0),
            ],
        )
        assert provider.get_file("F1").is_open is True
        provider.handle_call(FuncName("__cobol_close_file"), [typed_from_runtime("F1")])
        assert provider.get_file("F1").is_open is False

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.CLOSE)
    def test_close_nonexistent_file_is_noop(self):
        provider = StubIOProvider()
        result = provider.handle_call(
            FuncName("__cobol_close_file"), [typed_from_runtime("NOPE")]
        )
        assert result == IOResult("00", None)

    @covers(CobolFeature.IO_PROVIDER)
    def test_unknown_func_returns_uncomputable(self):
        provider = StubIOProvider()
        assert provider.handle_call(FuncName("__cobol_bogus"), []) is _UNCOMPUTABLE

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.WRITE, CobolFeature.REWRITE)
    def test_rewrite_replaces_last_written(self):
        provider = StubIOProvider()
        provider.handle_call(
            FuncName("__cobol_write_record"),
            [typed_from_runtime("F1"), typed_from_runtime("OLD")],
        )
        result = provider.handle_call(
            FuncName("__cobol_rewrite_record"),
            [typed_from_runtime("F1"), typed_from_runtime("NEW")],
        )
        assert result == IOResult("00", None)
        assert provider.get_file("F1").written == ["NEW"]

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.REWRITE)
    def test_rewrite_appends_when_no_prior_writes(self):
        provider = StubIOProvider()
        result = provider.handle_call(
            FuncName("__cobol_rewrite_record"),
            [typed_from_runtime("F1"), typed_from_runtime("DATA")],
        )
        assert result == IOResult("00", None)
        assert provider.get_file("F1").written == ["DATA"]

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.START)
    def test_start_returns_io_result_ok(self):
        provider = StubIOProvider()
        result = provider.handle_call(
            FuncName("__cobol_start_file"),
            [
                typed_from_runtime("F1"),
                typed_from_runtime("KEY1"),
                typed_from_runtime(">="),
            ],
        )
        assert result == IOResult("00", None)

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.DELETE_RECORD)
    def test_delete_removes_first_record(self):
        provider = StubIOProvider(files={"F1": {"records": ["REC1", "REC2"]}})
        result = provider.handle_call(
            FuncName("__cobol_delete_record"), [typed_from_runtime("F1")]
        )
        assert result == IOResult("00", None)
        assert provider.get_file("F1").records == ["REC2"]

    @covers(CobolFeature.IO_PROVIDER, CobolFeature.DELETE_RECORD)
    def test_delete_returns_io_result_ok_when_no_records(self):
        provider = StubIOProvider(files={"F1": {"records": []}})
        result = provider.handle_call(
            FuncName("__cobol_delete_record"), [typed_from_runtime("F1")]
        )
        assert result == IOResult("00", None)

    @covers(CobolFeature.IO_PROVIDER)
    def test_get_file_creates_stub(self):
        provider = StubIOProvider()
        stub = provider.get_file("NEW-FILE")
        assert isinstance(stub, StubFile)
        assert stub.records == []
        assert stub.written == []
        assert stub.is_open is False


class TestIOResult:
    @covers(CobolFeature.IO_PROVIDER)
    def test_io_result_frozen(self):
        r = IOResult("00", "some data")
        assert r.status == "00"
        assert r.data == "some data"

    @covers(CobolFeature.IO_PROVIDER)
    def test_io_result_none_data(self):
        r = IOResult("00", None)
        assert r.data is None

    @covers(CobolFeature.IO_PROVIDER)
    def test_io_result_at_end(self):
        r = IOResult("10", None)
        assert r.status == "10"
        assert r.data is None


class TestIOStatusAndDataMethods:
    @covers(CobolFeature.IO_PROVIDER)
    def test_io_status_extracts_from_io_result(self):
        provider = NullIOProvider()
        result = provider._io_status(IOResult("00", "rec"))
        assert result == "00"

    @covers(CobolFeature.IO_PROVIDER)
    def test_io_data_extracts_from_io_result(self):
        provider = NullIOProvider()
        result = provider._io_data(IOResult("00", "mydata"))
        assert result == "mydata"

    @covers(CobolFeature.IO_PROVIDER)
    def test_io_data_none_returns_empty_string(self):
        provider = NullIOProvider()
        result = provider._io_data(IOResult("00", None))
        assert result == ""

    @covers(CobolFeature.IO_PROVIDER)
    def test_io_status_uncomputable_for_non_io_result(self):
        provider = NullIOProvider()
        result = provider._io_status("plain string")
        assert result is _UNCOMPUTABLE

    @covers(CobolFeature.IO_PROVIDER)
    def test_io_data_uncomputable_for_non_io_result(self):
        provider = NullIOProvider()
        result = provider._io_data(42)
        assert result is _UNCOMPUTABLE

    @covers(CobolFeature.IO_PROVIDER)
    def test_io_status_via_dispatch(self):
        provider = NullIOProvider()
        io_result = IOResult("10", None)
        result = provider.handle_call(
            FuncName("__cobol_io_status"), [typed_from_runtime(io_result)]
        )
        assert result == "10"

    @covers(CobolFeature.IO_PROVIDER)
    def test_io_data_via_dispatch(self):
        provider = NullIOProvider()
        io_result = IOResult("00", "record content")
        result = provider.handle_call(
            FuncName("__cobol_io_data"), [typed_from_runtime(io_result)]
        )
        assert result == "record content"


class TestStubFile:
    @covers(CobolFeature.IO_PROVIDER)
    def test_default_values(self):
        stub = StubFile()
        assert stub.records == []
        assert stub.written == []
        assert stub.is_open is False

    @covers(CobolFeature.IO_PROVIDER)
    def test_with_records(self):
        stub = StubFile(records=["A", "B"], is_open=True)
        assert stub.records == ["A", "B"]
        assert stub.is_open is True
