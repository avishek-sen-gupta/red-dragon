"""Chunked LLM frontend — decomposes large files into top-level chunks for LLM lowering."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from .frontend import Frontend
from .ir import IRInstruction, Opcode
from .llm_frontend import IRParsingError, LLMFrontend
from .parser import ParserFactory
from . import constants

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceChunk:
    """A top-level source code fragment extracted from a file."""

    chunk_type: str  # "function", "class", or "top_level"
    name: str  # function/class name, or "__top_level__"
    source_text: str
    start_line: int


class ChunkExtractor:
    """Extracts top-level code chunks from a tree-sitter parse tree."""

    FUNCTION_NODE_TYPES: frozenset[str] = frozenset(
        {
            "function_definition",
            "function_declaration",
            "method_declaration",
            "function_item",
            "function_expression",
            "arrow_function",
        }
    )

    CLASS_NODE_TYPES: frozenset[str] = frozenset(
        {
            "class_definition",
            "class_declaration",
            "class_specifier",
            "struct_item",
            "struct_declaration",
            "impl_item",
            "interface_declaration",
        }
    )

    COMMENT_NODE_TYPES: frozenset[str] = frozenset(
        {
            "comment",
            "line_comment",
            "block_comment",
        }
    )

    def extract_chunks(
        self, tree: Any, source: bytes, language: str
    ) -> list[SourceChunk]:
        """Extract top-level chunks from a parse tree.

        Functions and classes come first, then top-level statements
        (grouped into contiguous blocks).
        """
        root = tree.root_node
        functions_and_classes: list[SourceChunk] = []
        top_level_pending: list[Any] = []
        top_level_groups: list[SourceChunk] = []

        def _flush_top_level():
            if not top_level_pending:
                return
            first_node = top_level_pending[0]
            combined_text = "\n".join(
                source[n.start_byte : n.end_byte].decode("utf-8")
                for n in top_level_pending
            )
            top_level_groups.append(
                SourceChunk(
                    chunk_type="top_level",
                    name="__top_level__",
                    source_text=combined_text,
                    start_line=first_node.start_point[0] + 1,
                )
            )
            top_level_pending.clear()

        for child in root.children:
            node_type = child.type

            if node_type in self.COMMENT_NODE_TYPES:
                continue

            if not child.is_named:
                continue

            if node_type in self.FUNCTION_NODE_TYPES:
                _flush_top_level()
                name = self._extract_name(child, language)
                text = source[child.start_byte : child.end_byte].decode("utf-8")
                functions_and_classes.append(
                    SourceChunk(
                        chunk_type="function",
                        name=name,
                        source_text=text,
                        start_line=child.start_point[0] + 1,
                    )
                )
            elif node_type in self.CLASS_NODE_TYPES:
                _flush_top_level()
                name = self._extract_name(child, language)
                text = source[child.start_byte : child.end_byte].decode("utf-8")
                functions_and_classes.append(
                    SourceChunk(
                        chunk_type="class",
                        name=name,
                        source_text=text,
                        start_line=child.start_point[0] + 1,
                    )
                )
            else:
                top_level_pending.append(child)

        _flush_top_level()

        logger.info(
            "ChunkExtractor: %d functions/classes, %d top-level groups from %s source",
            len(functions_and_classes),
            len(top_level_groups),
            language,
        )
        return functions_and_classes + top_level_groups

    def _extract_name(self, node: Any, language: str) -> str:
        """Extract the name from a function or class node."""
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return name_node.text.decode("utf-8")
        return f"_anonymous_{node.start_point[0]}"


_REG_PATTERN = re.compile(r"^%(\d+)$")
_FUNC_REF_LABEL_PATTERN = re.compile(r"(<(?:function|class):\w+@)(\w+)(>)")


class IRRenumberer:
    """Renumbers registers and labels in IR instructions to avoid cross-chunk collisions."""

    def renumber(
        self,
        instructions: list[IRInstruction],
        reg_offset: int,
        label_suffix: str,
    ) -> tuple[list[IRInstruction], int]:
        """Renumber registers and labels in the given instructions.

        Args:
            instructions: IR instructions to renumber.
            reg_offset: Offset to add to all register numbers.
            label_suffix: Suffix to append to all labels.

        Returns:
            Tuple of (renumbered instructions, next available reg_offset).
        """
        max_reg = -1
        result: list[IRInstruction] = []

        for inst in instructions:
            new_result_reg = self._renumber_reg(inst.result_reg, reg_offset)
            new_operands = [
                self._renumber_operand(op, reg_offset, label_suffix)
                for op in inst.operands
            ]
            new_label = self._renumber_label(inst.label, label_suffix, inst.opcode)

            result.append(
                IRInstruction(
                    opcode=inst.opcode,
                    result_reg=new_result_reg,
                    operands=new_operands,
                    label=new_label,
                    source_location=inst.source_location,
                )
            )

            max_reg = max(max_reg, self._extract_reg_number(new_result_reg))
            for op in new_operands:
                max_reg = max(max_reg, self._extract_reg_number(op))

        next_offset = max_reg + 1 if max_reg >= 0 else reg_offset
        return result, next_offset

    def _renumber_reg(self, reg: str | None, offset: int) -> str | None:
        if reg is None:
            return None
        match = _REG_PATTERN.match(reg)
        if match:
            return f"%{int(match.group(1)) + offset}"
        return reg

    def _renumber_operand(self, operand: Any, offset: int, label_suffix: str) -> Any:
        if not isinstance(operand, str):
            return operand
        match = _REG_PATTERN.match(operand)
        if match:
            return f"%{int(match.group(1)) + offset}"
        # Renumber function/class ref labels: <function:foo@func_foo_0> → <function:foo@func_foo_0_suffix>
        ref_match = _FUNC_REF_LABEL_PATTERN.search(operand)
        if ref_match:
            return _FUNC_REF_LABEL_PATTERN.sub(
                lambda m: f"{m.group(1)}{m.group(2)}{label_suffix}{m.group(3)}",
                operand,
            )
        return operand

    def _renumber_label(
        self, label: str | None, suffix: str, opcode: Opcode
    ) -> str | None:
        if label is None:
            return None
        if opcode == Opcode.BRANCH_IF:
            # Comma-separated labels
            parts = [part.strip() + suffix for part in label.split(",")]
            return ",".join(parts)
        return label + suffix

    def _extract_reg_number(self, value: Any) -> int:
        if not isinstance(value, str):
            return -1
        match = _REG_PATTERN.match(value)
        if match:
            return int(match.group(1))
        return -1


class ChunkedLLMFrontend(Frontend):
    """Frontend that decomposes source into chunks and sends each to an LLMFrontend.

    Wraps an existing LLMFrontend, using tree-sitter to split the source
    into top-level functions/classes/statements before lowering each independently.
    """

    def __init__(
        self,
        llm_frontend: LLMFrontend,
        parser_factory: ParserFactory,
        language: str,
    ):
        self._llm_frontend = llm_frontend
        self._parser_factory = parser_factory
        self._language = language
        self._chunk_extractor = ChunkExtractor()
        self._renumberer = IRRenumberer()

    def lower(self, tree: Any, source: bytes) -> list[IRInstruction]:
        """Lower source code to IR by chunking and delegating to wrapped LLMFrontend.

        Args:
            tree: Optional tree-sitter tree. If None, parses internally.
            source: Raw source code bytes.

        Returns:
            Combined list of IR instructions with a single entry label.
        """
        source_bytes = source if isinstance(source, bytes) else source.encode("utf-8")

        if tree is None:
            parser = self._parser_factory.get_parser(self._language)
            tree = parser.parse(source_bytes)

        chunks = self._chunk_extractor.extract_chunks(
            tree, source_bytes, self._language
        )

        if not chunks:
            logger.warning(
                "ChunkedLLMFrontend: no chunks extracted, returning entry label only"
            )
            return [IRInstruction(opcode=Opcode.LABEL, label=constants.CFG_ENTRY_LABEL)]

        all_instructions: list[IRInstruction] = []
        reg_offset = 0

        for i, chunk in enumerate(chunks):
            logger.info(
                "ChunkedLLMFrontend: lowering chunk %d/%d [%s] '%s' (%d chars, line %d)",
                i + 1,
                len(chunks),
                chunk.chunk_type,
                chunk.name,
                len(chunk.source_text),
                chunk.start_line,
            )

            try:
                chunk_instructions = self._llm_frontend.lower(
                    None, chunk.source_text.encode("utf-8")
                )
            except (IRParsingError, Exception) as exc:
                logger.warning(
                    "ChunkedLLMFrontend: chunk '%s' failed: %s — inserting placeholder",
                    chunk.name,
                    exc,
                )
                placeholder = IRInstruction(
                    opcode=Opcode.SYMBOLIC,
                    result_reg=f"%{reg_offset}",
                    operands=[f"chunk_error:{chunk.name}"],
                )
                all_instructions.append(placeholder)
                reg_offset += 1
                continue

            # Strip the entry label from this chunk's output
            chunk_instructions = [
                inst
                for inst in chunk_instructions
                if not (
                    inst.opcode == Opcode.LABEL
                    and inst.label == constants.CFG_ENTRY_LABEL
                )
            ]

            label_suffix = f"_chunk{i}"
            renumbered, reg_offset = self._renumberer.renumber(
                chunk_instructions, reg_offset, label_suffix
            )
            all_instructions.extend(renumbered)

        # Prepend the single entry label
        entry = IRInstruction(opcode=Opcode.LABEL, label=constants.CFG_ENTRY_LABEL)
        combined = [entry] + all_instructions

        logger.info(
            "ChunkedLLMFrontend: produced %d IR instructions from %d chunks",
            len(combined),
            len(chunks),
        )
        return combined
