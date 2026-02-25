"""Tree-Sitter Parsing Layer."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ParserFactory(ABC):
    """Abstract factory for obtaining a language parser."""

    @abstractmethod
    def get_parser(self, language: str): ...


class TreeSitterParserFactory(ParserFactory):
    """Concrete factory that delegates to tree-sitter-language-pack."""

    def get_parser(self, language: str):
        import tree_sitter_language_pack as tslp

        return tslp.get_parser(language)


class Parser:
    """Thin wrapper around a parser factory."""

    def __init__(self, parser_factory: ParserFactory):
        self._factory = parser_factory

    def parse(self, source: str, language: str):
        parser = self._factory.get_parser(language)
        tree = parser.parse(source.encode("utf-8"))
        return tree
