"""Scala tree-sitter node type constants."""


class ScalaNodeType:
    """Constants for Scala tree-sitter node type strings."""

    # Literals and identifiers
    IDENTIFIER = "identifier"
    TYPE_IDENTIFIER = "type_identifier"
    INTEGER_LITERAL = "integer_literal"
    FLOATING_POINT_LITERAL = "floating_point_literal"
    STRING = "string"
    STRING_LITERAL = "string_literal"
    BOOLEAN_LITERAL = "boolean_literal"
    NULL_LITERAL = "null_literal"
    UNIT = "unit"

    # Expressions
    INFIX_EXPRESSION = "infix_expression"
    PREFIX_EXPRESSION = "prefix_expression"
    PARENTHESIZED_EXPRESSION = "parenthesized_expression"
    CALL_EXPRESSION = "call_expression"
    FIELD_EXPRESSION = "field_expression"
    IF_EXPRESSION = "if_expression"
    MATCH_EXPRESSION = "match_expression"
    ASSIGNMENT_EXPRESSION = "assignment_expression"
    RETURN_EXPRESSION = "return_expression"
    TUPLE_EXPRESSION = "tuple_expression"
    INTERPOLATED_STRING_EXPRESSION = "interpolated_string_expression"
    INTERPOLATED_STRING = "interpolated_string"
    LAMBDA_EXPRESSION = "lambda_expression"
    INSTANCE_EXPRESSION = "instance_expression"
    TRY_EXPRESSION = "try_expression"
    THROW_EXPRESSION = "throw_expression"
    WHILE_EXPRESSION = "while_expression"
    FOR_EXPRESSION = "for_expression"
    DO_WHILE_EXPRESSION = "do_while_expression"
    BREAK_EXPRESSION = "break_expression"
    CONTINUE_EXPRESSION = "continue_expression"
    GENERIC_TYPE = "generic_type"
    GENERIC_FUNCTION = "generic_function"
    POSTFIX_EXPRESSION = "postfix_expression"
    STABLE_TYPE_IDENTIFIER = "stable_type_identifier"
    OPERATOR_IDENTIFIER = "operator_identifier"
    TYPE_ARGUMENTS = "type_arguments"

    # Keywords (used as node types in tree-sitter)
    THIS = "this"
    SUPER = "super"
    RETURN = "return"
    THROW = "throw"

    # Blocks and bodies
    BLOCK = "block"
    TEMPLATE_BODY = "template_body"
    COMPILATION_UNIT = "compilation_unit"
    ARGUMENTS = "arguments"

    # Definitions and declarations
    VAL_DEFINITION = "val_definition"
    VAR_DEFINITION = "var_definition"
    FUNCTION_DEFINITION = "function_definition"
    FUNCTION_DECLARATION = "function_declaration"
    CLASS_DEFINITION = "class_definition"
    OBJECT_DEFINITION = "object_definition"
    TRAIT_DEFINITION = "trait_definition"
    CASE_CLASS_DEFINITION = "case_class_definition"
    EXTENDS_CLAUSE = "extends_clause"
    LAZY_VAL_DEFINITION = "lazy_val_definition"
    TYPE_DEFINITION = "type_definition"
    IMPORT_DECLARATION = "import_declaration"
    EXPORT_DECLARATION = "export_declaration"
    PACKAGE_CLAUSE = "package_clause"
    EXPRESSION_STATEMENT = "expression_statement"
    PARAMETER = "parameter"

    # Abstract declarations
    VAL_DECLARATION = "val_declaration"

    # Patterns
    WILDCARD = "wildcard"
    ALTERNATIVE_PATTERN = "alternative_pattern"
    CASE_CLASS_PATTERN = "case_class_pattern"
    TYPED_PATTERN = "typed_pattern"
    TUPLE_PATTERN = "tuple_pattern"
    INFIX_PATTERN = "infix_pattern"

    # Match / case
    CASE_CLAUSE = "case_clause"
    CASE_BLOCK = "case_block"
    GUARD = "guard"

    # Control flow parts
    ENUMERATORS = "enumerators"
    ENUMERATOR = "enumerator"
    CATCH_CLAUSE = "catch_clause"
    FINALLY_CLAUSE = "finally_clause"

    # Lambda parts
    BINDINGS = "bindings"
    BINDING = "binding"

    # String interpolation
    INTERPOLATION = "interpolation"

    # Comments
    COMMENT = "comment"
    BLOCK_COMMENT = "block_comment"

    # Punctuation tokens (used in child-type filtering)
    LPAREN = "("
    RPAREN = ")"
    COMMA = ","
    LBRACE = "{"
    RBRACE = "}"
    SEMICOLON = ";"
    DOUBLE_QUOTE = '"'
