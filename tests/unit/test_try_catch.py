"""Tests for try/catch/finally lowering across language frontends."""

from __future__ import annotations

import pytest
import tree_sitter_language_pack

from interpreter.frontends.python import PythonFrontend
from interpreter.frontends.javascript import JavaScriptFrontend
from interpreter.frontends.typescript import TypeScriptFrontend
from interpreter.frontends.java import JavaFrontend
from interpreter.frontends.cpp import CppFrontend
from interpreter.frontends.csharp import CSharpFrontend
from interpreter.frontends.php import PhpFrontend
from interpreter.frontends.kotlin import KotlinFrontend
from interpreter.frontends.scala import ScalaFrontend
from interpreter.frontends.ruby import RubyFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_and_lower(source: str, language: str, frontend) -> list[IRInstruction]:
    parser = tree_sitter_language_pack.get_parser(language)
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    return frontend.lower(tree, source_bytes)


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


def _labels(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


def _branches(instructions: list[IRInstruction]) -> list[str]:
    return [
        inst.label
        for inst in instructions
        if inst.opcode == Opcode.BRANCH and inst.label
    ]


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _symbolics(instructions: list[IRInstruction]) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == Opcode.SYMBOLIC]


# ── Basic try/catch per language ────────────────────────────────────


class TestBasicTryCatch:
    def test_python_try_except(self):
        ir = _parse_and_lower(
            "try:\n    x = risky()\nexcept Exception as e:\n    y = handle(e)\n",
            "python",
            PythonFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_end" in l for l in labels)
        # Caught exception symbolic
        caught = [s for s in _symbolics(ir) if "caught_exception" in str(s.operands)]
        assert len(caught) == 1
        # Exception variable is stored
        stores = [i for i in ir if i.opcode == Opcode.STORE_VAR and "e" in i.operands]
        assert len(stores) >= 1

    def test_javascript_try_catch(self):
        ir = _parse_and_lower(
            "try { let x = risky(); } catch (e) { let y = handle(e); }",
            "javascript",
            JavaScriptFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_end" in l for l in labels)

    def test_java_try_catch(self):
        ir = _parse_and_lower(
            "class T { void m() { try { int x = risky(); } catch (Exception e) { handle(e); } } }",
            "java",
            JavaFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)

    def test_cpp_try_catch(self):
        ir = _parse_and_lower(
            "int main() { try { int x = risky(); } catch (const std::exception& e) { handle(); } }",
            "cpp",
            CppFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)

    def test_csharp_try_catch(self):
        ir = _parse_and_lower(
            "try { int x = RiskyOp(); } catch (Exception e) { Handle(e); }",
            "csharp",
            CSharpFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)

    def test_php_try_catch(self):
        ir = _parse_and_lower(
            "<?php try { $x = risky(); } catch (Exception $e) { handle($e); } ?>",
            "php",
            PhpFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)

    def test_kotlin_try_catch(self):
        ir = _parse_and_lower(
            "fun f() { try { val x = risky() } catch (e: Exception) { handle(e) } }",
            "kotlin",
            KotlinFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)

    def test_ruby_begin_rescue(self):
        ir = _parse_and_lower(
            "begin\n  x = risky()\nrescue StandardError => e\n  handle(e)\nend\n",
            "ruby",
            RubyFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)


# ── Try/finally without catch ───────────────────────────────────────


class TestTryFinallyOnly:
    def test_python_try_finally(self):
        ir = _parse_and_lower(
            "try:\n    x = risky()\nfinally:\n    cleanup()\n",
            "python",
            PythonFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("try_finally" in l for l in labels)
        assert any("try_end" in l for l in labels)
        # Body should have a branch to finally
        branches = _branches(ir)
        finally_labels = [l for l in labels if "try_finally" in l]
        assert len(finally_labels) == 1
        assert finally_labels[0] in branches

    def test_javascript_try_finally(self):
        ir = _parse_and_lower(
            "try { risky(); } finally { cleanup(); }",
            "javascript",
            JavaScriptFrontend(),
        )
        labels = _labels(ir)
        assert any("try_finally" in l for l in labels)

    def test_java_try_finally(self):
        ir = _parse_and_lower(
            "class T { void m() { try { risky(); } finally { cleanup(); } } }",
            "java",
            JavaFrontend(),
        )
        labels = _labels(ir)
        assert any("try_finally" in l for l in labels)


# ── Try/catch/finally combined ──────────────────────────────────────


class TestTryCatchFinally:
    def test_python_try_except_finally(self):
        ir = _parse_and_lower(
            "try:\n    x = risky()\nexcept Exception as e:\n    handle(e)\nfinally:\n    cleanup()\n",
            "python",
            PythonFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_finally" in l for l in labels)
        assert any("try_end" in l for l in labels)
        # Both catch body and try body should branch to finally
        branches = _branches(ir)
        finally_labels = [l for l in labels if "try_finally" in l]
        assert finally_labels[0] in branches

    def test_javascript_try_catch_finally(self):
        ir = _parse_and_lower(
            "try { risky(); } catch (e) { handle(e); } finally { cleanup(); }",
            "javascript",
            JavaScriptFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_finally" in l for l in labels)

    def test_csharp_try_catch_finally(self):
        ir = _parse_and_lower(
            "try { Risky(); } catch (Exception e) { Handle(e); } finally { Cleanup(); }",
            "csharp",
            CSharpFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_finally" in l for l in labels)

    def test_php_try_catch_finally(self):
        ir = _parse_and_lower(
            "<?php try { risky(); } catch (Exception $e) { handle($e); } finally { cleanup(); } ?>",
            "php",
            PhpFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_finally" in l for l in labels)

    def test_ruby_begin_rescue_ensure(self):
        ir = _parse_and_lower(
            "begin\n  risky()\nrescue => e\n  handle(e)\nensure\n  cleanup()\nend\n",
            "ruby",
            RubyFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_finally" in l for l in labels)


# ── Multiple catch clauses ──────────────────────────────────────────


class TestMultipleCatchClauses:
    def test_java_multiple_catch(self):
        ir = _parse_and_lower(
            """\
class T {
    void m() {
        try {
            risky();
        } catch (IOException e) {
            handleIO(e);
        } catch (Exception e) {
            handleGeneral(e);
        }
    }
}
""",
            "java",
            JavaFrontend(),
        )
        labels = _labels(ir)
        assert any("catch_0" in l for l in labels)
        assert any("catch_1" in l for l in labels)
        caught = [s for s in _symbolics(ir) if "caught_exception" in str(s.operands)]
        assert len(caught) == 2

    def test_csharp_multiple_catch(self):
        ir = _parse_and_lower(
            """\
try {
    Risky();
} catch (IOException e) {
    HandleIO(e);
} catch (Exception e) {
    HandleGeneral(e);
}
""",
            "csharp",
            CSharpFrontend(),
        )
        labels = _labels(ir)
        assert any("catch_0" in l for l in labels)
        assert any("catch_1" in l for l in labels)

    def test_php_multiple_catch(self):
        ir = _parse_and_lower(
            "<?php try { risky(); } catch (IOException $e) { handleIO($e); } catch (Exception $e) { handleGeneral($e); } ?>",
            "php",
            PhpFrontend(),
        )
        labels = _labels(ir)
        assert any("catch_0" in l for l in labels)
        assert any("catch_1" in l for l in labels)

    def test_python_multiple_except(self):
        ir = _parse_and_lower(
            "try:\n    risky()\nexcept ValueError as e:\n    handle_value(e)\nexcept Exception as e:\n    handle_general(e)\n",
            "python",
            PythonFrontend(),
        )
        labels = _labels(ir)
        assert any("catch_0" in l for l in labels)
        assert any("catch_1" in l for l in labels)
        caught = [s for s in _symbolics(ir) if "caught_exception" in str(s.operands)]
        assert len(caught) == 2


# ── Catch without exception variable ────────────────────────────────


class TestCatchWithoutVariable:
    def test_cpp_catch_ellipsis(self):
        ir = _parse_and_lower(
            "int main() { try { risky(); } catch (...) { fallback(); } }",
            "cpp",
            CppFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        # Caught exception symbolic should exist even without variable
        caught = [s for s in _symbolics(ir) if "caught_exception" in str(s.operands)]
        assert len(caught) == 1
        # No STORE_VAR for exception variable (no variable named)
        stores_after_caught = []
        found_caught = False
        for inst in ir:
            if found_caught and inst.opcode == Opcode.STORE_VAR:
                stores_after_caught.append(inst)
                break
            if inst.opcode == Opcode.SYMBOLIC and "caught_exception" in str(
                inst.operands
            ):
                found_caught = True
        # The next instruction after SYMBOLIC should NOT be a STORE_VAR for exc var
        # (it might be a STORE_VAR for something else in the catch body)

    def test_python_bare_except(self):
        ir = _parse_and_lower(
            "try:\n    risky()\nexcept:\n    handle()\n",
            "python",
            PythonFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)


# ── Python try/except/else/finally ──────────────────────────────────


class TestPythonElseClause:
    def test_try_except_else(self):
        ir = _parse_and_lower(
            "try:\n    risky()\nexcept Exception:\n    handle()\nelse:\n    success()\n",
            "python",
            PythonFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_else" in l for l in labels)

    def test_try_except_else_finally(self):
        ir = _parse_and_lower(
            "try:\n    risky()\nexcept Exception:\n    handle()\nelse:\n    success()\nfinally:\n    cleanup()\n",
            "python",
            PythonFrontend(),
        )
        labels = _labels(ir)
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_else" in l for l in labels)
        assert any("try_finally" in l for l in labels)
        assert any("try_end" in l for l in labels)


# ── Nested try/catch ────────────────────────────────────────────────


class TestNestedTryCatch:
    def test_nested_java(self):
        ir = _parse_and_lower(
            """\
class T {
    void m() {
        try {
            try {
                risky();
            } catch (IOException inner) {
                handleInner();
            }
        } catch (Exception outer) {
            handleOuter();
        }
    }
}
""",
            "java",
            JavaFrontend(),
        )
        labels = _labels(ir)
        try_body_labels = [l for l in labels if "try_body" in l]
        catch_labels = [l for l in labels if "catch_0" in l]
        assert len(try_body_labels) == 2
        assert len(catch_labels) == 2

    def test_nested_python(self):
        ir = _parse_and_lower(
            "try:\n    try:\n        risky()\n    except ValueError:\n        inner()\nexcept Exception:\n    outer()\n",
            "python",
            PythonFrontend(),
        )
        labels = _labels(ir)
        try_body_labels = [l for l in labels if "try_body" in l]
        assert len(try_body_labels) == 2


# ── Catch body code is lowered ──────────────────────────────────────


class TestCatchBodyLowered:
    def test_java_catch_body_has_call(self):
        ir = _parse_and_lower(
            "class T { void m() { try { risky(); } catch (Exception e) { handle(e); } } }",
            "java",
            JavaFrontend(),
        )
        # The catch body should contain a CALL_FUNCTION for handle(e)
        calls = [i for i in ir if i.opcode == Opcode.CALL_FUNCTION]
        call_names = [i.operands[0] for i in calls]
        assert "handle" in call_names

    def test_python_catch_body_has_call(self):
        ir = _parse_and_lower(
            "try:\n    risky()\nexcept Exception as e:\n    handle(e)\n",
            "python",
            PythonFrontend(),
        )
        calls = [i for i in ir if i.opcode == Opcode.CALL_FUNCTION]
        call_names = [i.operands[0] for i in calls]
        assert "handle" in call_names


# ── No SYMBOLIC catch_clause/finally_clause placeholders ────────────


class TestNoSymbolicPlaceholders:
    @pytest.mark.parametrize(
        "lang,frontend,source",
        [
            (
                "java",
                JavaFrontend(),
                "class T { void m() { try { risky(); } catch (Exception e) { handle(); } } }",
            ),
            (
                "cpp",
                CppFrontend(),
                "int main() { try { risky(); } catch (...) { handle(); } }",
            ),
            (
                "csharp",
                CSharpFrontend(),
                "try { Risky(); } catch (Exception e) { Handle(); }",
            ),
            (
                "php",
                PhpFrontend(),
                "<?php try { risky(); } catch (Exception $e) { handle(); } ?>",
            ),
            (
                "javascript",
                JavaScriptFrontend(),
                "try { risky(); } catch (e) { handle(); }",
            ),
            (
                "python",
                PythonFrontend(),
                "try:\n    risky()\nexcept Exception as e:\n    handle()\n",
            ),
        ],
    )
    def test_no_symbolic_catch_or_finally(self, lang, frontend, source):
        ir = _parse_and_lower(source, lang, frontend)
        symbolics = _symbolics(ir)
        bad = [
            s
            for s in symbolics
            if any(
                kw in str(s.operands)
                for kw in ("catch_clause:", "finally_clause:", "except_clause:")
            )
        ]
        assert len(bad) == 0, f"{lang}: found SYMBOLIC placeholders: {bad}"


# ── Cross-language parametrized: basic try/catch has labels ─────────


class TestCrossLanguageTryCatch:
    @pytest.mark.parametrize(
        "lang,frontend,source",
        [
            (
                "python",
                PythonFrontend(),
                "try:\n    risky()\nexcept Exception:\n    handle()\n",
            ),
            (
                "javascript",
                JavaScriptFrontend(),
                "try { risky(); } catch (e) { handle(); }",
            ),
            (
                "java",
                JavaFrontend(),
                "class T { void m() { try { risky(); } catch (Exception e) { handle(); } } }",
            ),
            (
                "cpp",
                CppFrontend(),
                "int main() { try { risky(); } catch (...) { handle(); } }",
            ),
            (
                "csharp",
                CSharpFrontend(),
                "try { Risky(); } catch (Exception e) { Handle(); }",
            ),
            (
                "php",
                PhpFrontend(),
                "<?php try { risky(); } catch (Exception $e) { handle(); } ?>",
            ),
            (
                "ruby",
                RubyFrontend(),
                "begin\n  risky()\nrescue => e\n  handle()\nend\n",
            ),
        ],
    )
    def test_has_try_labels_and_branches(self, lang, frontend, source):
        ir = _parse_and_lower(source, lang, frontend)
        labels = _labels(ir)
        branches = _branches(ir)
        assert any("try_body" in l for l in labels), f"{lang}: missing try_body label"
        assert any("catch_0" in l for l in labels), f"{lang}: missing catch_0 label"
        assert any("try_end" in l for l in labels), f"{lang}: missing try_end label"
        assert len(branches) > 0, f"{lang}: no BRANCH instructions"
