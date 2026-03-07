"""Tree-sitter node type string constants used by BaseFrontend.

Centralises raw string literals so that typos are caught at import time
and refactoring is straightforward.
"""


class BaseNodeType:
    """Tree-sitter node type strings used in BaseFrontend."""

    # ── semantic node types ──────────────────────────────────────

    IDENTIFIER = "identifier"
    ATTRIBUTE = "attribute"
    MEMBER_EXPRESSION = "member_expression"
    SELECTOR_EXPRESSION = "selector_expression"
    MEMBER_ACCESS_EXPRESSION = "member_access_expression"
    FIELD_ACCESS = "field_access"
    METHOD_INDEX_EXPRESSION = "method_index_expression"
    SUBSCRIPT = "subscript"
    PARENTHESIZED_EXPRESSION = "parenthesized_expression"

    # ── call-related node types ──────────────────────────────────

    ARGUMENT = "argument"
    VALUE_ARGUMENT = "value_argument"

    # ── statement node types ─────────────────────────────────────

    RETURN = "return"
    ELIF_CLAUSE = "elif_clause"
    ELSE_CLAUSE = "else_clause"
    ELSE = "else"
    VARIABLE_DECLARATOR = "variable_declarator"

    # ── literal / container node types ───────────────────────────

    PAIR = "pair"

    # ── comment / noise node types ───────────────────────────────

    COMMENT = "comment"
    NEWLINE = "newline"

    # ── punctuation tokens ───────────────────────────────────────

    OPEN_PAREN = "("
    CLOSE_PAREN = ")"
    COMMA = ","
    COLON = ":"
    ARROW = "->"
    SEMICOLON = ";"
    OPEN_BRACKET = "["
    CLOSE_BRACKET = "]"
    OPEN_BRACE = "{"
    CLOSE_BRACE = "}"
    NEWLINE_CHAR = "\n"
