"""Tree-sitter node type strings used in Java frontend lowerers.

Centralises raw string literals so that typos are caught at import time
and grep/refactor is trivial.
"""


class JavaNodeType:
    """Tree-sitter node type strings used in Java frontend lowerers."""

    # ── Literals & atoms ─────────────────────────────────────────────
    IDENTIFIER = "identifier"
    DECIMAL_INTEGER_LITERAL = "decimal_integer_literal"
    HEX_INTEGER_LITERAL = "hex_integer_literal"
    OCTAL_INTEGER_LITERAL = "octal_integer_literal"
    BINARY_INTEGER_LITERAL = "binary_integer_literal"
    DECIMAL_FLOATING_POINT_LITERAL = "decimal_floating_point_literal"
    STRING_LITERAL = "string_literal"
    CHARACTER_LITERAL = "character_literal"
    NULL_LITERAL = "null_literal"
    TRUE = "true"
    FALSE = "false"
    THIS = "this"
    SUPER = "super"
    TYPE_IDENTIFIER = "type_identifier"

    # ── Expressions ──────────────────────────────────────────────────
    BINARY_EXPRESSION = "binary_expression"
    UNARY_EXPRESSION = "unary_expression"
    UPDATE_EXPRESSION = "update_expression"
    PARENTHESIZED_EXPRESSION = "parenthesized_expression"
    METHOD_INVOCATION = "method_invocation"
    OBJECT_CREATION_EXPRESSION = "object_creation_expression"
    FIELD_ACCESS = "field_access"
    ARRAY_ACCESS = "array_access"
    ARRAY_CREATION_EXPRESSION = "array_creation_expression"
    ARRAY_INITIALIZER = "array_initializer"
    ASSIGNMENT_EXPRESSION = "assignment_expression"
    CAST_EXPRESSION = "cast_expression"
    INSTANCEOF_EXPRESSION = "instanceof_expression"
    TERNARY_EXPRESSION = "ternary_expression"
    METHOD_REFERENCE = "method_reference"
    LAMBDA_EXPRESSION = "lambda_expression"
    CLASS_LITERAL = "class_literal"
    SCOPED_IDENTIFIER = "scoped_identifier"

    # ── Statements ───────────────────────────────────────────────────
    EXPRESSION_STATEMENT = "expression_statement"
    LOCAL_VARIABLE_DECLARATION = "local_variable_declaration"
    RETURN_STATEMENT = "return_statement"
    IF_STATEMENT = "if_statement"
    WHILE_STATEMENT = "while_statement"
    FOR_STATEMENT = "for_statement"
    ENHANCED_FOR_STATEMENT = "enhanced_for_statement"
    THROW_STATEMENT = "throw_statement"
    BREAK_STATEMENT = "break_statement"
    CONTINUE_STATEMENT = "continue_statement"
    DO_STATEMENT = "do_statement"
    ASSERT_STATEMENT = "assert_statement"
    LABELED_STATEMENT = "labeled_statement"
    SYNCHRONIZED_STATEMENT = "synchronized_statement"
    IMPORT_DECLARATION = "import_declaration"
    PACKAGE_DECLARATION = "package_declaration"

    # ── Switch ───────────────────────────────────────────────────────
    SWITCH_EXPRESSION = "switch_expression"
    SWITCH_BLOCK_STATEMENT_GROUP = "switch_block_statement_group"
    SWITCH_RULE = "switch_rule"
    SWITCH_LABEL = "switch_label"

    # ── Declarations / class body ────────────────────────────────────
    METHOD_DECLARATION = "method_declaration"
    CLASS_DECLARATION = "class_declaration"
    INTERFACE_DECLARATION = "interface_declaration"
    ENUM_DECLARATION = "enum_declaration"
    ANNOTATION_TYPE_DECLARATION = "annotation_type_declaration"
    RECORD_DECLARATION = "record_declaration"
    CONSTRUCTOR_DECLARATION = "constructor_declaration"
    FIELD_DECLARATION = "field_declaration"
    STATIC_INITIALIZER = "static_initializer"
    VARIABLE_DECLARATOR = "variable_declarator"
    ENUM_CONSTANT = "enum_constant"
    EXPLICIT_CONSTRUCTOR_INVOCATION = "explicit_constructor_invocation"

    # ── Try / catch ──────────────────────────────────────────────────
    TRY_STATEMENT = "try_statement"
    TRY_WITH_RESOURCES_STATEMENT = "try_with_resources_statement"
    CATCH_CLAUSE = "catch_clause"
    CATCH_FORMAL_PARAMETER = "catch_formal_parameter"
    FINALLY_CLAUSE = "finally_clause"

    # ── Parameter types ──────────────────────────────────────────────
    FORMAL_PARAMETERS = "formal_parameters"
    FORMAL_PARAMETER = "formal_parameter"
    SPREAD_PARAMETER = "spread_parameter"

    # ── Modifiers / annotations ──────────────────────────────────────
    MODIFIERS = "modifiers"
    STATIC = "static"
    MARKER_ANNOTATION = "marker_annotation"
    ANNOTATION = "annotation"

    # ── Block / containers ───────────────────────────────────────────
    BLOCK = "block"
    PROGRAM = "program"

    # ── Dimension expressions ────────────────────────────────────────
    DIMENSIONS_EXPR = "dimensions_expr"

    # ── Comment / noise ──────────────────────────────────────────────
    COMMENT = "comment"
    LINE_COMMENT = "line_comment"
    BLOCK_COMMENT = "block_comment"
    NEWLINE = "\n"

    # ── Keywords (appear as node types in tree-sitter) ───────────────
    ELSE = "else"
