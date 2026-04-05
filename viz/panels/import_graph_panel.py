"""Import graph panel — box-drawing DAG of the project's import structure."""

from __future__ import annotations
from pathlib import Path
from textual.widgets import Static


def render_import_graph(
    topo_order: list[Path],
    import_graph: dict[Path, list[Path]],
    exports: dict[Path, tuple[int, int]],
    project_root: Path,
) -> str:
    """Render a text-based import DAG."""
    lines: list[str] = []
    name_for: dict[Path, str] = {}

    for i, path in enumerate(topo_order, start=1):
        rel = (
            path.relative_to(project_root)
            if path.is_relative_to(project_root)
            else path
        )
        name_for[path] = str(rel)
        fn_count, var_count = exports.get(path, (0, 0))
        parts = []
        if fn_count:
            parts.append(f"{fn_count} fn")
        if var_count:
            parts.append(f"{var_count} var")
        summary = f" ({', '.join(parts)})" if parts else ""
        lines.append(f"  {i}. {rel}{summary}")

        deps = import_graph.get(path, [])
        if deps:
            dep_names = ", ".join(name_for.get(d, str(d)) for d in deps)
            lines.append(f"     └── imports ── {dep_names}")

        if i < len(topo_order):
            lines.append("     │")

    return "\n".join(lines)


class ImportGraphPanel(Static):
    """Displays a box-drawing DAG of the project's import graph."""

    def __init__(
        self,
        topo_order: list[Path],
        import_graph: dict[Path, list[Path]],
        exports: dict[Path, tuple[int, int]],
        project_root: Path,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._topo_order = topo_order
        self._import_graph = import_graph
        self._exports = exports
        self._project_root = project_root

    def on_mount(self) -> None:
        text = render_import_graph(
            self._topo_order, self._import_graph, self._exports, self._project_root
        )
        header = f" Import Graph ({len(self._topo_order)} modules, topo order)\n"
        header += "─" * 50 + "\n"
        self.update(header + text)
