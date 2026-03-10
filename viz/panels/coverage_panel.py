"""Coverage matrix panel — cross-language handler availability grid."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from viz.coverage import FrontendCoverage, all_node_types


class CoveragePanel(Static):
    """Displays a cross-language coverage matrix of AST node handler support."""

    def __init__(
        self,
        coverages: list[FrontendCoverage],
        filter_text: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._coverages = coverages
        self._filter_text = filter_text
        self._all_types = all_node_types(coverages)

    def set_filter(self, filter_text: str) -> None:
        self._filter_text = filter_text
        self._render_matrix()

    def on_mount(self) -> None:
        self._render_matrix()

    def _render_matrix(self) -> None:
        if not self._coverages:
            self.update("[dim]No coverage data[/dim]")
            return

        text = Text()
        langs = [c.language for c in self._coverages]
        lang_width = 6

        # Header row
        text.append("  " + "Node Type".ljust(35), style="bold")
        text.append("│", style="dim")
        for lang in langs:
            text.append(f" {lang[:lang_width].center(lang_width)} ", style="bold cyan")
        text.append("\n")

        # Separator
        text.append("  " + "─" * 35, style="dim")
        text.append("┼", style="dim")
        text.append(("─" * (lang_width + 2)) * len(langs), style="dim")
        text.append("\n")

        # Filter types
        visible_types = [
            t
            for t in self._all_types
            if not self._filter_text or self._filter_text.lower() in t.lower()
        ]

        for ntype in visible_types:
            text.append(f"  {ntype[:35].ljust(35)}")
            text.append("│", style="dim")

            for cov in self._coverages:
                handler = cov.stmt_handlers.get(ntype) or cov.expr_handlers.get(ntype)
                if handler:
                    if handler.is_shared:
                        symbol = "  ✓*  "
                        style = "green"
                    else:
                        symbol = "  ✓   "
                        style = "bold green"
                else:
                    symbol = "  ·   "
                    style = "dim"
                text.append(symbol, style=style)

            text.append("\n")

        # Legend
        text.append("\n")
        text.append("  ✓", style="bold green")
        text.append(" language-specific  ", style="dim")
        text.append("✓*", style="green")
        text.append(" shared (common/)  ", style="dim")
        text.append("·", style="dim")
        text.append(" not supported", style="dim")

        self.update(text)
