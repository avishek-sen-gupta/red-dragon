"""Tests for exception control flow — THROW redirecting to catch blocks."""

from __future__ import annotations

import pytest

from interpreter.var_name import VarName
from interpreter.ir import Opcode
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint


def _run_program(source: str, language: str = "python", max_steps: int = 300) -> dict:
    """Run a program and return the main frame's local_vars."""
    vm = run(
        source,
        language=language,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestThrowRedirectsToCatch:
    def test_catch_block_entered_on_raise(self):
        """raise inside try should redirect to except block."""
        source = """\
answer = 0
try:
    answer = 1
    raise Exception("test")
    answer = 99
except Exception as e:
    answer = -1
"""
        vars_ = _run_program(source)
        assert vars_[VarName("answer")] == -1

    def test_code_after_raise_not_executed(self):
        """Code after raise should not execute."""
        source = """\
marker = 0
try:
    marker = 1
    raise Exception("boom")
    marker = 2
except Exception as e:
    marker = 10
"""
        vars_ = _run_program(source)
        # marker should be 10 (catch block), NOT 2 (code after raise)
        assert (
            vars_[VarName("marker")] != 2
        ), "Code after raise should not have executed"
        assert vars_[VarName("marker")] == 10

    def test_no_exception_skips_catch(self):
        """If no exception is raised, catch block is not entered."""
        source = """\
answer = 0
try:
    answer = 42
except Exception as e:
    answer = -1
"""
        vars_ = _run_program(source)
        assert vars_[VarName("answer")] == 42

    def test_finally_always_executes_on_raise(self):
        """Finally block should execute even when exception is raised."""
        source = """\
cleanup = 0
answer = 0
try:
    answer = 1
    raise Exception("test")
except Exception as e:
    answer = -1
finally:
    cleanup = 1
"""
        vars_ = _run_program(source)
        assert vars_[VarName("answer")] == -1
        assert vars_[VarName("cleanup")] == 1

    def test_finally_executes_without_exception(self):
        """Finally block should execute on normal flow too."""
        source = """\
cleanup = 0
answer = 0
try:
    answer = 42
finally:
    cleanup = 1
"""
        vars_ = _run_program(source)
        assert vars_[VarName("answer")] == 42
        assert vars_[VarName("cleanup")] == 1


class TestTryPushPopInIR:
    def test_try_push_emitted(self):
        """try/except should emit TRY_PUSH instruction."""
        from interpreter.frontends import get_deterministic_frontend

        frontend = get_deterministic_frontend("python")
        ir = frontend.lower(b"""\
try:
    x = 1
except:
    x = 2
""")
        opcodes = [inst.opcode for inst in ir]
        assert Opcode.TRY_PUSH in opcodes

    def test_try_pop_emitted(self):
        """try/except should emit TRY_POP instruction."""
        from interpreter.frontends import get_deterministic_frontend

        frontend = get_deterministic_frontend("python")
        ir = frontend.lower(b"""\
try:
    x = 1
except:
    x = 2
""")
        opcodes = [inst.opcode for inst in ir]
        assert Opcode.TRY_POP in opcodes


class TestExceptionFlowCrossLanguage:
    """Test exception control flow works across multiple languages."""

    @pytest.fixture(
        params=["python", "javascript", "java", "php", "ruby", "kotlin", "cpp"],
        ids=lambda lang: lang,
    )
    def language(self, request):
        return request.param

    def test_catch_entered_on_throw(self, language):
        """Each language's try/catch should redirect throw to catch block."""
        from tests.unit.rosetta.conftest import execute_for_language, extract_answer

        programs = {
            "python": """\
answer = 0
try:
    raise Exception("test")
    answer = 99
except Exception as e:
    answer = -1
""",
            "javascript": """\
let answer = 0;
try {
    throw new Error("test");
    answer = 99;
} catch (e) {
    answer = -1;
}
""",
            "java": """\
class M {
    static int answer = 0;
    static {
        try {
            throw new Exception("test");
        } catch (Exception e) {
            answer = -1;
        }
    }
}
""",
            "php": """\
<?php
$answer = 0;
try {
    throw new Exception("test");
    $answer = 99;
} catch (Exception $e) {
    $answer = -1;
}
?>
""",
            "ruby": """\
answer = 0
begin
    raise "test"
    answer = 99
rescue => e
    answer = -1
end
""",
            "kotlin": """\
var answer: Int = 0
try {
    throw Exception("test")
    answer = 99
} catch (e: Exception) {
    answer = -1
}
""",
            "cpp": """\
int answer = 0;
try {
    throw 1;
    answer = 99;
} catch (...) {
    answer = -1;
}
""",
        }
        vm, stats = execute_for_language(language, programs[language])
        answer = extract_answer(vm, language)
        assert answer == -1, f"[{language}] expected answer=-1, got {answer}"
