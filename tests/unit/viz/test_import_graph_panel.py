"""Tests for ImportGraphPanel — box-drawing import DAG."""

from pathlib import Path
from viz.panels.import_graph_panel import render_import_graph


class TestRenderImportGraph:
    def test_single_module(self) -> None:
        root = Path("/project")
        topo = [Path("/project/main.py")]
        graph: dict[Path, list[Path]] = {topo[0]: []}
        exports: dict[Path, tuple[int, int]] = {topo[0]: (1, 0)}
        text = render_import_graph(topo, graph, exports, root)
        assert "main.py" in text
        assert "1." in text

    def test_two_modules_with_edge(self) -> None:
        root = Path("/project")
        utils = Path("/project/utils.py")
        main = Path("/project/main.py")
        topo = [utils, main]
        graph: dict[Path, list[Path]] = {utils: [], main: [utils]}
        exports: dict[Path, tuple[int, int]] = {utils: (1, 0), main: (1, 0)}
        text = render_import_graph(topo, graph, exports, root)
        assert "utils.py" in text
        assert "main.py" in text

    def test_three_modules_chain(self) -> None:
        root = Path("/project")
        a = Path("/project/a.py")
        b = Path("/project/b.py")
        c = Path("/project/c.py")
        topo = [a, b, c]
        graph: dict[Path, list[Path]] = {a: [], b: [a], c: [b]}
        exports: dict[Path, tuple[int, int]] = {a: (0, 1), b: (2, 0), c: (1, 0)}
        text = render_import_graph(topo, graph, exports, root)
        lines = text.strip().split("\n")
        assert len(lines) >= 3
