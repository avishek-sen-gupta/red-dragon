"""Tests for COBOL import extraction (COPY/CALL)."""

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from interpreter.constants import Language
from cobol_asg.cobol_imports import extract_cobol_imports
from interpreter.project.imports import extract_imports
from interpreter.project.resolver import NO_PATH
from interpreter.project.types import ImportKind, ImportRef
from tests.covers import covers


class TestCobolCopyExtraction:
    """Test COBOL COPY statement extraction."""

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_simple_copy(self):
        source = b"       COPY CUSTOMER-RECORD.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        assert len(refs) == 1
        assert refs[0].module_path == "CUSTOMER-RECORD"
        assert refs[0].kind == ImportKind.INCLUDE

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_copy_with_library(self):
        source = b"       COPY DATFMT OF COPYLIB.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        assert len(refs) == 1
        assert refs[0].module_path == "DATFMT"

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_multiple_copies(self):
        source = b"       COPY REC1.\n       COPY REC2.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        assert len(refs) == 2
        modules = {r.module_path for r in refs}
        assert "REC1" in modules
        assert "REC2" in modules

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_copy_lowercase(self):
        source = b"       copy customer-record.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        assert len(refs) == 1
        assert refs[0].module_path.upper() == "CUSTOMER-RECORD"


class TestCobolCallExtraction:
    """Test COBOL CALL statement extraction."""

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_call_literal(self):
        source = b'       CALL "SUBPROG1" USING WS-DATA.\n'
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        call_refs = [r for r in refs if r.kind == ImportKind.REQUIRE]
        assert len(call_refs) == 1
        assert call_refs[0].module_path == "SUBPROG1"

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_call_with_single_quotes(self):
        source = b"       CALL 'SUBPROG2'.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        call_refs = [r for r in refs if r.kind == ImportKind.REQUIRE]
        assert len(call_refs) == 1
        assert call_refs[0].module_path == "SUBPROG2"

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_call_dynamic_variable_skipped(self):
        """CALL WS-PROG (dynamic) should be skipped — we can't resolve it."""
        source = b"       CALL WS-PROGRAM-NAME USING WS-DATA.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        call_refs = [r for r in refs if r.kind == ImportKind.REQUIRE]
        assert len(call_refs) == 0

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_mixed_copy_and_call(self):
        source = b"       COPY CUSTOMER-RECORD.\n       CALL 'VALIDATE'.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        assert len(refs) == 2
        kinds = {r.kind for r in refs}
        assert ImportKind.INCLUDE in kinds
        assert ImportKind.REQUIRE in kinds


class TestCobolImportFalsePositiveGuards:
    """False-positive suppression: comments and string literals must not yield imports."""

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_fixed_format_star_comment_line_not_matched(self):
        """Column-7 '*' indicator marks a comment — COPY inside must be ignored."""
        source = b"      * COPY PHANTOM.\n       COPY REAL-REC.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        modules = {r.module_path for r in refs}
        assert "PHANTOM" not in modules
        assert "REAL-REC" in modules

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_fixed_format_slash_comment_line_not_matched(self):
        """Column-7 '/' (page-eject comment) — COPY inside must be ignored."""
        source = b"      / COPY PHANTOM.\n       COPY REAL-REC.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        modules = {r.module_path for r in refs}
        assert "PHANTOM" not in modules
        assert "REAL-REC" in modules

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_free_format_inline_comment_line_not_matched(self):
        """*> comment lines must be ignored."""
        source = b"*> COPY PHANTOM.\n       COPY REAL-REC.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        modules = {r.module_path for r in refs}
        assert "PHANTOM" not in modules
        assert "REAL-REC" in modules

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_copy_inside_string_literal_not_matched(self):
        """'COPY FOO' inside a string literal must not yield an import."""
        source = b"       MOVE 'COPY PHANTOM' TO WS-MSG.\n       COPY REAL-REC.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        modules = {r.module_path for r in refs}
        assert "PHANTOM" not in modules
        assert "REAL-REC" in modules

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_call_inside_string_literal_not_matched(self):
        """CALL target embedded in a larger string literal must not yield an import."""
        source = b"       MOVE \"CALL 'PHANTOM'\" TO WS-MSG.\n       CALL 'REAL'.\n"
        refs = extract_imports(source, Path("main.cbl"), Language.COBOL)
        modules = {r.module_path for r in refs}
        assert "PHANTOM" not in modules
        assert "REAL" in modules


class TestCobolResolver:
    """Test COBOL import resolution with real tmp directories."""

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
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

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_resolves_copybook(self, cobol_project):
        from interpreter.project.resolver import CobolImportResolver

        resolver = CobolImportResolver()
        ref = ImportRef(
            source_file=cobol_project / "MAIN.cbl",
            module_path="CUSTOMER-REC",
            kind=ImportKind.INCLUDE,
        )
        [result] = resolver.resolve(ref, cobol_project)
        assert result.resolved_path == cobol_project / "CUSTOMER-REC.cpy"

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_resolves_called_program(self, cobol_project):
        from interpreter.project.resolver import CobolImportResolver

        resolver = CobolImportResolver()
        ref = ImportRef(
            source_file=cobol_project / "MAIN.cbl",
            module_path="VALIDATE",
            kind=ImportKind.REQUIRE,
        )
        [result] = resolver.resolve(ref, cobol_project)
        assert result.resolved_path == cobol_project / "VALIDATE.cbl"

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_nonexistent_copybook(self, cobol_project):
        from interpreter.project.resolver import CobolImportResolver

        resolver = CobolImportResolver()
        ref = ImportRef(
            source_file=cobol_project / "MAIN.cbl",
            module_path="MISSING-COPY",
            kind=ImportKind.INCLUDE,
        )
        [result] = resolver.resolve(ref, cobol_project)
        assert result.resolved_path == NO_PATH


class TestCobolImportSourcePositions:
    """A COPY's line number is what makes a missing copybook actionable: 315 names
    missing across 1766 programs is a number, ``member X line 412`` is somewhere to
    look. The scanner is the one place that knows it, and it has to be exact —
    comment lines are stripped before the grammar runs, so anything that changes
    the line count between the file on disk and the text handed to Lark makes every
    reported position downstream of it wrong."""

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_a_copy_reports_the_line_it_is_on(self):
        source = (
            b"       PROGRAM-ID. FOO.\n"
            b"       WORKING-STORAGE SECTION.\n"
            b"       COPY CUSTREC.\n"
        )
        (ref,) = extract_cobol_imports(source, Path("FOO.cbl"))
        assert ref.module_path == "CUSTREC"
        assert ref.line == 3

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_a_copy_after_comment_lines_reports_its_true_source_line(self):
        """Comment lines used to be *deleted* before tokenisation, which shifted
        every position after them up by the number of comments removed."""
        source = (
            b"       PROGRAM-ID. FOO.\n"
            b"      * a box comment\n"
            b"      * another one\n"
            b"      / and a page eject\n"
            b"       COPY CUSTREC.\n"
        )
        (ref,) = extract_cobol_imports(source, Path("FOO.cbl"))
        assert ref.line == 5

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_a_copy_after_a_free_format_comment_reports_its_true_source_line(self):
        source = (
            b"       PROGRAM-ID. FOO.\n"
            b"    *> free-format comment\n"
            b"       COPY CUSTREC.\n"
        )
        (ref,) = extract_cobol_imports(source, Path("FOO.cbl"))
        assert ref.line == 3

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_a_call_reports_the_line_it_is_on(self):
        source = b"       PROGRAM-ID. FOO.\n\n       CALL 'SUBPROG'.\n"
        (ref,) = extract_cobol_imports(source, Path("FOO.cbl"))
        assert ref.kind == ImportKind.REQUIRE
        assert ref.line == 3

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_the_same_copybook_copied_twice_reports_both_lines(self):
        """A diagnostic groups by copybook name, so two COPYs of one name in one
        program must stay two entries with distinct lines, not collapse to one."""
        source = b"       COPY CUSTREC.\n       DISPLAY 'X'.\n       COPY CUSTREC.\n"
        refs = extract_cobol_imports(source, Path("FOO.cbl"))
        assert [r.line for r in refs] == [1, 3]

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_text_in_the_identification_area_is_not_scanned_as_code(self):
        """Columns 73-80 are the identification area, not program text. A member
        stamped there with something COPY-shaped must not become an edge."""
        source = b"       DISPLAY 'X'.".ljust(72) + b"COPY XX\n"
        assert extract_cobol_imports(source, Path("FOO.cbl")) == []


class TestCobolFixedFormatContinuation:
    """A non-numeric literal too long for area B is split at column 72 and resumed
    on the next line, which carries '-' in column 7 and re-opens with a quote.
    Reading such a member a line at a time is not merely imprecise, it is four
    distinct defects: a split COPY name reports a truncated name that resolves to
    nothing, a split CALL literal is missed outright, and text inside the open
    literal gets scanned as code, which invents COPY/CALL statements that are prose.

    The indicator lives at column 7, so folding is inherently fixed-format. That is
    what the corpus is: no caller sets the bridge's source format flag, so it always
    takes its FIXED default, and source_text decodes fixed-format members."""

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_a_copy_name_split_across_a_continuation_reports_the_whole_name(self):
        """Worse than a miss: the unfolded read yields LONGCOPYBOOKNAM, a name no
        copybook has, which the diagnostic then reports as unresolvable."""
        source = b"       COPY LONGCOPYBOOKNAM\n      -    E.\n"
        (ref,) = extract_cobol_imports(source, Path("FOO.cbl"))
        assert ref.module_path == "LONGCOPYBOOKNAME"

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_a_call_literal_split_across_a_continuation_is_found(self):
        """CALL_STMT needs a complete quoted literal, so a split one matches nothing
        and the call edge simply disappears."""
        source = b"       CALL 'SUBPRO\n      -    'GRAM' USING WS-A.\n"
        (ref,) = extract_cobol_imports(source, Path("FOO.cbl"))
        assert ref.kind == ImportKind.REQUIRE
        assert ref.module_path == "SUBPROGRAM"

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_a_copy_keyword_inside_a_continued_literal_is_not_reported(self):
        """Prose in a message literal is not a copy statement. Unfolded, the open
        quote cannot be paired, so the literal's words are tokenised as code."""
        source = b"       MOVE 'PLS COPY MEMBER1 NO\n      -    'W' TO WS-MSG.\n"
        assert extract_cobol_imports(source, Path("FOO.cbl")) == []

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_a_copy_keyword_split_inside_a_continued_literal_is_not_reported(self):
        """The same defect with the literal's own text split, which unfolded invents
        a COPY of MEMB -- a name assembled out of half a word."""
        source = (
            b"       MOVE 'ASK THEM TO COPY MEMB\n      -    'ER1 TODAY' TO WS-MSG.\n"
        )
        assert extract_cobol_imports(source, Path("FOO.cbl")) == []

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_a_doubled_quote_before_a_continuation_does_not_close_the_literal(self):
        """'' inside a literal is an escaped quote, not its terminator. Treating it
        as the end makes the following line look like code rather than a resume."""
        source = (
            b"       MOVE 'IT''S A LONG\n"
            b"      -    ' MESSAGE' TO WS-MSG.\n"
            b"       COPY CUSTREC.\n"
        )
        (ref,) = extract_cobol_imports(source, Path("FOO.cbl"))
        assert ref.module_path == "CUSTREC"
        assert ref.line == 3

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_a_comment_line_may_sit_between_a_line_and_its_continuation(self):
        """A comment line is legal anywhere, including inside a continued statement.
        Dropping it must not make the continuation attach to the comment instead of
        to the line it continues."""
        source = (
            b"       MOVE 'ABC\n"
            b"      * a box comment\n"
            b"      -    'DEF' TO WS-MSG.\n"
            b"       COPY CUSTREC.\n"
        )
        (ref,) = extract_cobol_imports(source, Path("FOO.cbl"))
        assert ref.module_path == "CUSTREC"
        assert ref.line == 4

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_a_word_continuation_joins_with_no_intervening_space(self):
        """Fixed-format continuation splices the first nonblank of area B directly
        onto the last nonblank of the continued line -- a space would be a different
        program, and is why continuation is only ever used mid-token."""
        source = b"       COPY CUST\n      -    REC.\n"
        (ref,) = extract_cobol_imports(source, Path("FOO.cbl"))
        assert ref.module_path == "CUSTREC"

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_a_copy_after_a_continuation_reports_its_true_source_line(self):
        """Folding joins lines, so a token's position in the folded text is no longer
        its position in the file. Without a map back, every ref after the first
        continuation points at the wrong line."""
        source = (
            b"       MOVE 'ABCDEFGHIJ\n"
            b"      -    'KLM' TO WS-MSG.\n"
            b"       COPY CUSTREC.\n"
        )
        (ref,) = extract_cobol_imports(source, Path("FOO.cbl"))
        assert ref.line == 3


class TestCobolMalformedSourceTolerance:
    """Malformed source must degrade to noise, not raise: tolerance, not correctness."""

    @covers(CobolFeature.MULTI_FILE_IMPORTS)
    def test_an_unterminated_literal_does_not_hide_a_later_copy(self):
        """The 328-member failure. STRING matched newlines, so an unterminated quote
        paired with the next line's quote, the mispairing cascaded, and eventually
        nothing matched -- taking every COPY in the rest of the file with it.

        This source is malformed COBOL (a continuation that resumes no literal), so
        folding cannot rescue it. What matters is that it degrades to noise instead
        of raising, because a member we cannot read is a member build_graph drops
        from the graph entirely.
        """
        source = (
            b"       MOVE 'UNTERMINATED\n       DISPLAY 'X'.\n       COPY CUSTREC.\n"
        )
        refs = extract_cobol_imports(source, Path("FOO.cbl"))
        assert [r.module_path for r in refs] == ["CUSTREC"]
