"""Integration test for java.util.Calendar and java.util.GregorianCalendar stdlib stubs.

Exercises:
  - GregorianCalendar construction
  - Calendar.YEAR / Calendar.MONTH / Calendar.DAY_OF_MONTH constants
  - GregorianCalendar.set(field, value) method
  - GregorianCalendar.getTime() method returning a concrete (non-symbolic) value
"""

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.project.compiler import compile_directory
from interpreter.run import execute_cfg, ExecutionStrategies
from interpreter.run_types import VMConfig
from interpreter.types.typed_value import TypedValue
from interpreter.var_name import VarName
from interpreter.vm.vm_types import SymbolicValue

# ── Java source ────────────────────────────────────────────────

_MAIN_JAVA = """\
import java.util.Calendar;
import java.util.GregorianCalendar;

GregorianCalendar gc = new GregorianCalendar();
gc.set(Calendar.YEAR, 2024);
gc.set(Calendar.MONTH, 6);
gc.set(Calendar.DAY_OF_MONTH, 15);
Object dt = gc.getTime();
int year = Calendar.YEAR;
"""

# ── Fixture ────────────────────────────────────────────────────


@pytest.fixture
def calendar_project(tmp_path: Path) -> Path:
    """Write a Java project that uses Calendar/GregorianCalendar."""
    main_file = tmp_path / "src" / "main" / "java" / "Main.java"
    main_file.parent.mkdir(parents=True, exist_ok=True)
    main_file.write_text(_MAIN_JAVA)
    return tmp_path


# ── Tests ──────────────────────────────────────────────────────


class TestJavaCalendarStdlib:
    """GregorianCalendar and Calendar stdlib integration tests."""

    def test_calendar_construction_produces_no_symbolics(self, calendar_project: Path):
        """GregorianCalendar() constructor should produce a concrete heap object."""
        linked = compile_directory(calendar_project, Language.JAVA)

        strategies = ExecutionStrategies(
            func_symbol_table=linked.func_symbol_table,
            class_symbol_table=linked.class_symbol_table,
        )
        config = VMConfig(max_steps=500)
        vm, stats = execute_cfg(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            config,
            strategies,
        )

        # Collect all symbolic values from local vars across all frames
        symbolics = []
        for frame in vm.call_stack:
            for var, val in frame.local_vars.items():
                raw = val.value if isinstance(val, TypedValue) else val
                if isinstance(raw, SymbolicValue):
                    symbolics.append((str(var), raw.name))

        assert symbolics == [], f"Expected no symbolic values but found: {symbolics}"

    def test_calendar_constants_are_concrete_integers(self, calendar_project: Path):
        """Calendar.YEAR should resolve to a concrete integer, not a symbolic."""
        linked = compile_directory(calendar_project, Language.JAVA)

        strategies = ExecutionStrategies(
            func_symbol_table=linked.func_symbol_table,
            class_symbol_table=linked.class_symbol_table,
        )
        config = VMConfig(max_steps=500)
        vm, stats = execute_cfg(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            config,
            strategies,
        )

        frame = vm.call_stack[0]
        local_vars = {
            k: v.value if isinstance(v, TypedValue) else v
            for k, v in frame.local_vars.items()
        }

        assert (
            VarName("year") in local_vars
        ), f"Variable 'year' not in scope: {list(local_vars.keys())}"
        year_val = local_vars[VarName("year")]
        assert not isinstance(
            year_val, SymbolicValue
        ), f"Calendar.YEAR resolved to symbolic: {year_val.name}"
        # Calendar.YEAR is Java constant 1
        assert year_val == 1, f"Calendar.YEAR should be 1, got {year_val}"
