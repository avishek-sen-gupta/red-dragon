"""Tests for dependency graph construction and topological sort."""

from pathlib import Path

import pytest

from interpreter.project.types import CyclicImportError
from interpreter.project.resolver import topological_sort


class TestTopologicalSort:
    def test_single_node(self):
        graph = {Path("a.py"): []}
        result = topological_sort(graph)
        assert result == [Path("a.py")]

    def test_linear_chain(self):
        """a → b → c: c should come first (it has no deps)."""
        graph = {
            Path("a.py"): [Path("b.py")],
            Path("b.py"): [Path("c.py")],
            Path("c.py"): [],
        }
        result = topological_sort(graph)
        assert result.index(Path("c.py")) < result.index(Path("b.py"))
        assert result.index(Path("b.py")) < result.index(Path("a.py"))

    def test_diamond(self):
        """a → b, a → c, b → d, c → d: d comes first."""
        graph = {
            Path("a.py"): [Path("b.py"), Path("c.py")],
            Path("b.py"): [Path("d.py")],
            Path("c.py"): [Path("d.py")],
            Path("d.py"): [],
        }
        result = topological_sort(graph)
        assert result.index(Path("d.py")) < result.index(Path("b.py"))
        assert result.index(Path("d.py")) < result.index(Path("c.py"))
        assert result.index(Path("b.py")) < result.index(Path("a.py"))
        assert result.index(Path("c.py")) < result.index(Path("a.py"))

    def test_independent_files(self):
        """No edges — all files have no dependencies."""
        graph = {
            Path("a.py"): [],
            Path("b.py"): [],
            Path("c.py"): [],
        }
        result = topological_sort(graph)
        assert set(result) == {Path("a.py"), Path("b.py"), Path("c.py")}
        assert len(result) == 3

    def test_cycle_raises_error(self):
        """a → b → a: should raise CyclicImportError."""
        graph = {
            Path("a.py"): [Path("b.py")],
            Path("b.py"): [Path("a.py")],
        }
        with pytest.raises(CyclicImportError) as exc_info:
            topological_sort(graph)
        assert len(exc_info.value.cycle) > 0

    def test_three_node_cycle_raises_error(self):
        """a → b → c → a: should raise CyclicImportError."""
        graph = {
            Path("a.py"): [Path("b.py")],
            Path("b.py"): [Path("c.py")],
            Path("c.py"): [Path("a.py")],
        }
        with pytest.raises(CyclicImportError):
            topological_sort(graph)

    def test_self_cycle_raises_error(self):
        """a → a: self-import should raise CyclicImportError."""
        graph = {
            Path("a.py"): [Path("a.py")],
        }
        with pytest.raises(CyclicImportError):
            topological_sort(graph)

    def test_all_nodes_present_in_result(self):
        graph = {
            Path("a.py"): [Path("b.py")],
            Path("b.py"): [Path("c.py")],
            Path("c.py"): [],
        }
        result = topological_sort(graph)
        assert set(result) == {Path("a.py"), Path("b.py"), Path("c.py")}

    def test_deps_not_in_graph_as_keys(self):
        """If a dep is only mentioned as a target, it should still appear."""
        graph = {
            Path("a.py"): [Path("b.py")],
            # b.py is not a key in the graph
        }
        result = topological_sort(graph)
        assert Path("b.py") in result
        assert result.index(Path("b.py")) < result.index(Path("a.py"))
