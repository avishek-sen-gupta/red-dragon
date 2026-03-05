"""Type annotation extraction utilities for tree-sitter frontends.

Pure functions that extract type text from tree-sitter AST nodes and
normalize language-specific type names to canonical TypeName values.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from interpreter.constants import Language

if TYPE_CHECKING:
    from interpreter.frontends.context import TreeSitterEmitContext


# ── Per-language mapping of raw type strings to canonical TypeName values ──

LANGUAGE_TYPE_MAP: dict[Language, dict[str, str]] = {
    Language.JAVA: {
        "int": "Int",
        "long": "Int",
        "short": "Int",
        "byte": "Int",
        "char": "Int",
        "Integer": "Int",
        "Long": "Int",
        "Short": "Int",
        "Byte": "Int",
        "Character": "Int",
        "double": "Float",
        "float": "Float",
        "Double": "Float",
        "Float": "Float",
        "boolean": "Bool",
        "Boolean": "Bool",
        "String": "String",
        "void": "Any",
    },
    Language.GO: {
        "int": "Int",
        "int8": "Int",
        "int16": "Int",
        "int32": "Int",
        "int64": "Int",
        "uint": "Int",
        "uint8": "Int",
        "uint16": "Int",
        "uint32": "Int",
        "uint64": "Int",
        "uintptr": "Int",
        "rune": "Int",
        "byte": "Int",
        "float32": "Float",
        "float64": "Float",
        "bool": "Bool",
        "string": "String",
    },
    Language.RUST: {
        "i8": "Int",
        "i16": "Int",
        "i32": "Int",
        "i64": "Int",
        "i128": "Int",
        "isize": "Int",
        "u8": "Int",
        "u16": "Int",
        "u32": "Int",
        "u64": "Int",
        "u128": "Int",
        "usize": "Int",
        "f32": "Float",
        "f64": "Float",
        "bool": "Bool",
        "String": "String",
        "str": "String",
        "&str": "String",
    },
    Language.C: {
        "int": "Int",
        "long": "Int",
        "short": "Int",
        "char": "Int",
        "unsigned": "Int",
        "signed": "Int",
        "size_t": "Int",
        "float": "Float",
        "double": "Float",
        "bool": "Bool",
        "_Bool": "Bool",
        "void": "Any",
    },
    Language.CPP: {
        "int": "Int",
        "long": "Int",
        "short": "Int",
        "char": "Int",
        "unsigned": "Int",
        "signed": "Int",
        "size_t": "Int",
        "float": "Float",
        "double": "Float",
        "bool": "Bool",
        "void": "Any",
        "string": "String",
        "std::string": "String",
    },
    Language.CSHARP: {
        "int": "Int",
        "long": "Int",
        "short": "Int",
        "byte": "Int",
        "sbyte": "Int",
        "uint": "Int",
        "ulong": "Int",
        "ushort": "Int",
        "char": "Int",
        "Int32": "Int",
        "Int64": "Int",
        "float": "Float",
        "double": "Float",
        "decimal": "Float",
        "Single": "Float",
        "Double": "Float",
        "Decimal": "Float",
        "bool": "Bool",
        "Boolean": "Bool",
        "string": "String",
        "String": "String",
        "void": "Any",
        "object": "Object",
        "Object": "Object",
    },
    Language.KOTLIN: {
        "Int": "Int",
        "Long": "Int",
        "Short": "Int",
        "Byte": "Int",
        "Char": "Int",
        "Float": "Float",
        "Double": "Float",
        "Boolean": "Bool",
        "String": "String",
        "Unit": "Any",
        "Any": "Any",
    },
    Language.SCALA: {
        "Int": "Int",
        "Long": "Int",
        "Short": "Int",
        "Byte": "Int",
        "Char": "Int",
        "Float": "Float",
        "Double": "Float",
        "Boolean": "Bool",
        "String": "String",
        "Unit": "Any",
        "Any": "Any",
    },
    Language.PASCAL: {
        "integer": "Int",
        "longint": "Int",
        "shortint": "Int",
        "byte": "Int",
        "word": "Int",
        "cardinal": "Int",
        "real": "Float",
        "single": "Float",
        "double": "Float",
        "extended": "Float",
        "boolean": "Bool",
        "char": "String",
        "string": "String",
    },
    Language.TYPESCRIPT: {
        "number": "Float",
        "string": "String",
        "boolean": "Bool",
        "void": "Any",
        "any": "Any",
        "undefined": "Any",
        "null": "Any",
        "never": "Any",
        "object": "Object",
    },
    Language.PYTHON: {
        "int": "Int",
        "float": "Float",
        "bool": "Bool",
        "str": "String",
        "bytes": "String",
        "list": "Array",
        "dict": "Object",
        "object": "Object",
        "None": "Any",
    },
    Language.PHP: {
        "int": "Int",
        "integer": "Int",
        "float": "Float",
        "double": "Float",
        "bool": "Bool",
        "boolean": "Bool",
        "string": "String",
        "array": "Array",
        "object": "Object",
        "void": "Any",
        "mixed": "Any",
        "null": "Any",
    },
}


def normalize_type_hint(raw: str, language: Language) -> str:
    """Map a language-specific type name to a canonical TypeName value.

    Unknown types pass through as-is (for Object/class types).
    """
    type_map = LANGUAGE_TYPE_MAP.get(language, {})
    return type_map.get(raw, raw)


def extract_type_from_field(
    ctx: TreeSitterEmitContext, node, field_name: str = "type"
) -> str:
    """Extract type text from a tree-sitter node's named field.

    Returns the text of the field child, or "" if the field is absent.
    """
    type_node = node.child_by_field_name(field_name)
    return ctx.node_text(type_node) if type_node else ""


def extract_type_from_child(
    ctx: TreeSitterEmitContext, node, child_types: tuple[str, ...]
) -> str:
    """Extract type text from the first child matching one of *child_types*.

    Used for languages where types appear as named children rather than
    field-named children (e.g. Kotlin ``user_type``, Pascal ``type``).
    Returns "" if no matching child is found.
    """
    type_child = next(
        (c for c in node.children if c.type in child_types),
        None,
    )
    return ctx.node_text(type_child) if type_child else ""
