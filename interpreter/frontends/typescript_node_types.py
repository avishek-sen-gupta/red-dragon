# pyright: standard
"""Tree-sitter node type string constants used by the TypeScript frontend.

Centralises raw string literals so that typos are caught at import time
and refactoring is straightforward.
"""


class TypeScriptNodeType:
    """Tree-sitter node type strings used in the TypeScript frontend."""

    # ── TS-specific expression node types ────────────────────────

    TYPE_IDENTIFIER = "type_identifier"
    PREDEFINED_TYPE = "predefined_type"
    AS_EXPRESSION = "as_expression"
    NON_NULL_EXPRESSION = "non_null_expression"
    SATISFIES_EXPRESSION = "satisfies_expression"
    TYPE_ASSERTION = "type_assertion"

    # ── function / arrow node types (shared with JS, overridden) ─

    ARROW_FUNCTION = "arrow_function"
    FUNCTION = "function"
    FUNCTION_EXPRESSION = "function_expression"
    GENERATOR_FUNCTION = "generator_function"
    GENERATOR_FUNCTION_DECLARATION = "generator_function_declaration"

    # ── statement / declaration node types ────────────────────────

    FUNCTION_DECLARATION = "function_declaration"
    CLASS_DECLARATION = "class_declaration"
    CLASS_HERITAGE = "class_heritage"
    INTERFACE_DECLARATION = "interface_declaration"
    ENUM_DECLARATION = "enum_declaration"
    TYPE_ALIAS_DECLARATION = "type_alias_declaration"
    EXPORT_STATEMENT = "export_statement"
    IMPORT_STATEMENT = "import_statement"
    ABSTRACT_CLASS_DECLARATION = "abstract_class_declaration"
    PUBLIC_FIELD_DEFINITION = "public_field_definition"
    ABSTRACT_METHOD_SIGNATURE = "abstract_method_signature"
    INTERNAL_MODULE = "internal_module"
    FUNCTION_SIGNATURE = "function_signature"
    AMBIENT_DECLARATION = "ambient_declaration"
    IMPORT_ALIAS = "import_alias"

    # ── expression node types (TS-specific) ────────────────────────

    INSTANTIATION_EXPRESSION = "instantiation_expression"

    # ── class body member node types ─────────────────────────────

    METHOD_DEFINITION = "method_definition"
    CLASS_STATIC_BLOCK = "class_static_block"
    FIELD_DEFINITION = "field_definition"
    PROPERTY_IDENTIFIER = "property_identifier"
    EXPORT = "export"

    # ── parameter node types ─────────────────────────────────────

    REQUIRED_PARAMETER = "required_parameter"
    OPTIONAL_PARAMETER = "optional_parameter"
    TYPE_ANNOTATION = "type_annotation"

    # ── block / identifier node types (reused from JS) ───────────

    IDENTIFIER = "identifier"
    STATEMENT_BLOCK = "statement_block"

    # ── comment / noise types ────────────────────────────────────

    COMMENT = "comment"
    NEWLINE_CHAR = "\n"

    # ── punctuation tokens ───────────────────────────────────────

    OPEN_PAREN = "("
    CLOSE_PAREN = ")"
    COMMA = ","
    COLON = ":"
