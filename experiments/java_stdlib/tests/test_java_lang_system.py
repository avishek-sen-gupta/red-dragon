from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.func_name import FuncName
from experiments.java_stdlib.stubs.java_io_print_stream import PRINT_STREAM_MODULE
from experiments.java_stdlib.stubs.java_lang_system import SYSTEM_MODULE


class TestSystemAndPrintStreamExports:
    def test_system_has_class(self):
        assert ClassName("System") in SYSTEM_MODULE.exports.classes

    def test_print_stream_exports_println(self):
        assert FuncName("println") in PRINT_STREAM_MODULE.exports.functions

    def test_print_stream_exports_print(self):
        assert FuncName("print") in PRINT_STREAM_MODULE.exports.functions

    def test_print_stream_has_class(self):
        assert ClassName("PrintStream") in PRINT_STREAM_MODULE.exports.classes


_STDLIB = {
    Path("java/io/PrintStream.java"): PRINT_STREAM_MODULE,
    Path("java/lang/System.java"): SYSTEM_MODULE,
}


class TestSystemExecution:
    def test_println_produces_output(self, capsys):
        from experiments.java_stdlib.tests.conftest import run_with_stdlib

        run_with_stdlib('System.out.println("hello");', _STDLIB)
        assert capsys.readouterr().out == "hello\n"
