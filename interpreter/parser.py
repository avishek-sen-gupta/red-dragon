"""Tree-Sitter Parsing Layer."""
from __future__ import annotations


class Parser:
    """Thin wrapper around tree-sitter-language-pack."""

    def parse(self, source: str, language: str):
        import tree_sitter_language_pack as tslp

        parser = tslp.get_parser(language)
        tree = parser.parse(source.encode("utf-8"))
        return tree
