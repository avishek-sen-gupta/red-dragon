"""Tree-sitter node type strings used in JavaScript frontend lowerers.

Centralises raw string literals so that typos are caught at import time
and grep/refactor is trivial.
"""


class JavaScriptNodeType:
    """Tree-sitter node type strings used in JavaScript frontend lowerers."""

    # ── Literals & atoms ─────────────────────────────────────────────
    IDENTIFIER = "identifier"
    NUMBER = "number"
    STRING = "string"
    REGEX = "regex"
    STRING_FRAGMENT = "string_fragment"
    TEMPLATE_STRING = "template_string"
    TEMPLATE_SUBSTITUTION = "template_substitution"
    TRUE = "true"
    FALSE = "false"
    NULL = "null"
    UNDEFINED = "undefined"
    THIS = "this"
    SUPER = "super"
    PROPERTY_IDENTIFIER = "property_identifier"
    SHORTHAND_PROPERTY_IDENTIFIER = "shorthand_property_identifier"

    # ── Expressions ──────────────────────────────────────────────────
    BINARY_EXPRESSION = "binary_expression"
    AUGMENTED_ASSIGNMENT_EXPRESSION = "augmented_assignment_expression"
    UNARY_EXPRESSION = "unary_expression"
    UPDATE_EXPRESSION = "update_expression"
    CALL_EXPRESSION = "call_expression"
    NEW_EXPRESSION = "new_expression"
    MEMBER_EXPRESSION = "member_expression"
    SUBSCRIPT_EXPRESSION = "subscript_expression"
    PARENTHESIZED_EXPRESSION = "parenthesized_expression"
    ASSIGNMENT_EXPRESSION = "assignment_expression"
    ARROW_FUNCTION = "arrow_function"
    TERNARY_EXPRESSION = "ternary_expression"
    AWAIT_EXPRESSION = "await_expression"
    YIELD_EXPRESSION = "yield_expression"
    SEQUENCE_EXPRESSION = "sequence_expression"
    SPREAD_ELEMENT = "spread_element"
    META_PROPERTY = "meta_property"
    OPTIONAL_CHAIN = "optional_chain"
    COMPUTED_PROPERTY_NAME = "computed_property_name"

    # ── Collection literals ──────────────────────────────────────────
    ARRAY = "array"
    OBJECT = "object"
    PAIR = "pair"

    # ── Function / class nodes ───────────────────────────────────────
    FUNCTION = "function"
    FUNCTION_EXPRESSION = "function_expression"
    GENERATOR_FUNCTION = "generator_function"
    GENERATOR_FUNCTION_DECLARATION = "generator_function_declaration"
    FUNCTION_DECLARATION = "function_declaration"
    CLASS_DECLARATION = "class_declaration"
    CLASS = "class"
    CLASS_HERITAGE = "class_heritage"
    METHOD_DEFINITION = "method_definition"
    CLASS_STATIC_BLOCK = "class_static_block"
    FIELD_DEFINITION = "field_definition"

    # ── Statements ───────────────────────────────────────────────────
    EXPRESSION_STATEMENT = "expression_statement"
    LEXICAL_DECLARATION = "lexical_declaration"
    VARIABLE_DECLARATION = "variable_declaration"
    USING_DECLARATION = "using_declaration"
    VARIABLE_DECLARATOR = "variable_declarator"
    RETURN_STATEMENT = "return_statement"
    IF_STATEMENT = "if_statement"
    WHILE_STATEMENT = "while_statement"
    FOR_STATEMENT = "for_statement"
    FOR_IN_STATEMENT = "for_in_statement"
    THROW_STATEMENT = "throw_statement"
    STATEMENT_BLOCK = "statement_block"
    EMPTY_STATEMENT = "empty_statement"
    BREAK_STATEMENT = "break_statement"
    CONTINUE_STATEMENT = "continue_statement"
    TRY_STATEMENT = "try_statement"
    SWITCH_STATEMENT = "switch_statement"
    DO_STATEMENT = "do_statement"
    LABELED_STATEMENT = "labeled_statement"
    IMPORT_STATEMENT = "import_statement"
    EXPORT_STATEMENT = "export_statement"
    WITH_STATEMENT = "with_statement"

    # ── Switch clauses ───────────────────────────────────────────────
    SWITCH_CASE = "switch_case"
    SWITCH_DEFAULT = "switch_default"

    # ── Control-flow clause types ────────────────────────────────────
    ELSE_CLAUSE = "else_clause"

    # ── Destructuring patterns ───────────────────────────────────────
    OBJECT_PATTERN = "object_pattern"
    ARRAY_PATTERN = "array_pattern"
    ASSIGNMENT_PATTERN = "assignment_pattern"
    SHORTHAND_PROPERTY_IDENTIFIER_PATTERN = "shorthand_property_identifier_pattern"
    PAIR_PATTERN = "pair_pattern"
    REST_PATTERN = "rest_pattern"

    # ── Export nodes ─────────────────────────────────────────────────
    EXPORT_CLAUSE = "export_clause"
    EXPORT_SPECIFIER = "export_specifier"

    # ── Keywords (appear as node types in tree-sitter) ───────────────
    EXPORT = "export"
    DEFAULT = "default"
    STATIC = "static"
    ELSE = "else"

    # ── Block / program containers ───────────────────────────────────
    PROGRAM = "program"
    MODULE = "module"

    # ── Comment / noise ──────────────────────────────────────────────
    COMMENT = "comment"
    NEWLINE = "\n"

    # ── Punctuation tokens ───────────────────────────────────────────
    OPEN_PAREN = "("
    CLOSE_PAREN = ")"
    COMMA = ","
    BACKTICK = "`"
