"""Tests for COBOL import extraction (COPY/CALL)."""

from pathlib import Path

import pytest

from interpreter.project.imports import extract_imports
from interpreter.project.resolver import NO_PATH
from interpreter.project.types import ImportKind, ImportRef
from interpreter.constants import Language


class TestCobolCopyExtraction:
    """Test COBOL COPY statement extraction."""

    def test_simple_copy(self):
        source = b"       COPY CUSTOMER-RECORD.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        assert len(refs) == 1
        assert refs[0].module_path == "CUSTOMER-RECORD"
        assert refs[0].kind == ImportKind.INCLUDE

    def test_copy_with_library(self):
        source = b"       COPY DATFMT OF COPYLIB.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        assert len(refs) == 1
        assert refs[0].module_path == "DATFMT"

    def test_multiple_copies(self):
        source = b"       COPY REC1.\n       COPY REC2.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        assert len(refs) == 2
        modules = {r.module_path for r in refs}
        assert "REC1" in modules
        assert "REC2" in modules

    def test_copy_lowercase(self):
        source = b"       copy customer-record.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        assert len(refs) == 1
        assert refs[0].module_path.upper() == "CUSTOMER-RECORD"


class TestCobolCallExtraction:
    """Test COBOL CALL statement extraction."""

    def test_call_literal(self):
        source = b'       CALL "SUBPROG1" USING WS-DATA.\n'
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        call_refs = [r for r in refs if r.kind == ImportKind.REQUIRE]
        assert len(call_refs) == 1
        assert call_refs[0].module_path == "SUBPROG1"

    def test_call_with_single_quotes(self):
        source = b"       CALL 'SUBPROG2'.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        call_refs = [r for r in refs if r.kind == ImportKind.REQUIRE]
        assert len(call_refs) == 1
        assert call_refs[0].module_path == "SUBPROG2"

    def test_call_dynamic_variable_skipped(self):
        """CALL WS-PROG (dynamic) should be skipped — we can't resolve it."""
        source = b"       CALL WS-PROGRAM-NAME USING WS-DATA.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        call_refs = [r for r in refs if r.kind == ImportKind.REQUIRE]
        assert len(call_refs) == 0

    def test_mixed_copy_and_call(self):
        source = b"       COPY CUSTOMER-RECORD.\n       CALL 'VALIDATE'.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        assert len(refs) == 2
        kinds = {r.kind for r in refs}
        assert ImportKind.INCLUDE in kinds
        assert ImportKind.REQUIRE in kinds


class TestCobolResolver:
    """Test COBOL import resolution with real tmp directories."""

    @pytest.fixture
    def cobol_project(self, tmp_path):
        (tmp_path / "MAIN.cbl").write_text(
            "       COPY CUSTOMER-REC.\n       CALL 'VALIDATE'.\n"
        )
        (tmp_path / "CUSTOMER-REC.cpy").write_text(
            "       01 CUSTOMER-NAME PIC X(30).\n"
        )
        (tmp_path / "VALIDATE.cbl").write_text("       DISPLAY 'VALID'.\n")
        return tmp_path

    def test_resolves_copybook(self, cobol_project):
        from interpreter.project.resolver import CobolImportResolver

        resolver = CobolImportResolver()
        ref = ImportRef(
            source_file=cobol_project / "MAIN.cbl",
            module_path="CUSTOMER-REC",
            kind=ImportKind.INCLUDE,
        )
        result = resolver.resolve(ref, cobol_project)
        assert result.resolved_path == cobol_project / "CUSTOMER-REC.cpy"

    def test_resolves_called_program(self, cobol_project):
        from interpreter.project.resolver import CobolImportResolver

        resolver = CobolImportResolver()
        ref = ImportRef(
            source_file=cobol_project / "MAIN.cbl",
            module_path="VALIDATE",
            kind=ImportKind.REQUIRE,
        )
        result = resolver.resolve(ref, cobol_project)
        assert result.resolved_path == cobol_project / "VALIDATE.cbl"

    def test_nonexistent_copybook(self, cobol_project):
        from interpreter.project.resolver import CobolImportResolver

        resolver = CobolImportResolver()
        ref = ImportRef(
            source_file=cobol_project / "MAIN.cbl",
            module_path="MISSING-COPY",
            kind=ImportKind.INCLUDE,
        )
        result = resolver.resolve(ref, cobol_project)
        assert result.resolved_path == NO_PATH
