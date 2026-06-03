# tests/unit/test_mutation_test_script.py
"""Tests for scripts/mutation_test.py — verify correct subprocess commands are built."""

from __future__ import annotations

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

from tests.covers import covers, NotLanguageFeature

# Make scripts/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
import mutation_test  # pyright: ignore[reportMissingImports]  # noqa: E402


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_targets_dict_has_expected_keys():
    assert set(mutation_test.TARGETS.keys()) == {"core", "vm", "handlers", "all-core"}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_target_core_paths():
    assert "interpreter/ir.py" in mutation_test.TARGETS["core"]
    assert "interpreter/instructions.py" in mutation_test.TARGETS["core"]
    assert "interpreter/register.py" in mutation_test.TARGETS["core"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_target_vm_paths():
    assert mutation_test.TARGETS["vm"] == ["interpreter/vm/"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_target_handlers_paths():
    assert mutation_test.TARGETS["handlers"] == ["interpreter/handlers/"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_target_all_core_is_union():
    all_core = mutation_test.TARGETS["all-core"]
    for path in mutation_test.TARGETS["core"]:
        assert path in all_core
    assert "interpreter/vm/" in all_core
    assert "interpreter/handlers/" in all_core


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_run_target_calls_mutmut_with_correct_paths():
    with patch("mutation_test.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        mutation_test.run_target("vm")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "mutmut" in cmd
        assert "run" in cmd
        assert any("interpreter/vm/" in arg for arg in cmd)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_run_target_core_joins_multiple_paths():
    with patch("mutation_test.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        mutation_test.run_target("core")
        cmd = mock_run.call_args[0][0]
        paths_arg = next(arg for arg in cmd if "paths" in arg.lower())
        assert "interpreter/ir.py" in paths_arg
        assert "interpreter/instructions.py" in paths_arg
        assert "interpreter/register.py" in paths_arg


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_run_target_use_coverage_runs_pytest_first():
    with patch("mutation_test.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        mutation_test.run_target("vm", use_coverage=True)
        assert mock_run.call_count == 2
        first_call_cmd = mock_run.call_args_list[0][0][0]
        assert "pytest" in first_call_cmd
        assert "--cov" in " ".join(first_call_cmd)
        second_call_cmd = mock_run.call_args_list[1][0][0]
        assert "mutmut" in second_call_cmd
        assert "--use-coverage" in second_call_cmd


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_show_results_calls_mutmut_results():
    with patch("mutation_test.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        mutation_test.show_results()
        cmd = mock_run.call_args[0][0]
        assert "mutmut" in cmd
        assert "results" in cmd


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_list_targets_prints_all_targets(capsys):
    mutation_test.list_targets()
    captured = capsys.readouterr()
    for target in ("core", "vm", "handlers", "all-core"):
        assert target in captured.out


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_main_list_flag(capsys):
    with patch("sys.argv", ["mutation_test.py", "--list"]):
        mutation_test.main()
    captured = capsys.readouterr()
    assert "vm" in captured.out
    assert "handlers" in captured.out


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_main_results_flag():
    with patch("mutation_test.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("sys.argv", ["mutation_test.py", "--results"]):
            with pytest.raises(SystemExit):
                mutation_test.main()
        cmd = mock_run.call_args[0][0]
        assert "results" in cmd


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_main_target_flag():
    with patch("mutation_test.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("sys.argv", ["mutation_test.py", "--target", "handlers"]):
            with pytest.raises(SystemExit):
                mutation_test.main()
        cmd = mock_run.call_args[0][0]
        assert "interpreter/handlers/" in " ".join(cmd)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_main_exits_with_mutmut_return_code():
    with patch("mutation_test.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=3)
        with patch("sys.argv", ["mutation_test.py", "--target", "vm"]):
            with pytest.raises(SystemExit) as exc_info:
                mutation_test.main()
            assert exc_info.value.code == 3
