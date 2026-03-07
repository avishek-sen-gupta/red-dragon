"""C++ tree-sitter node type constants."""


class CppNodeType:
    """Constants for C++ tree-sitter node type strings."""

    # Identifiers and names
    IDENTIFIER = "identifier"
    TYPE_IDENTIFIER = "type_identifier"
    FIELD_IDENTIFIER = "field_identifier"
    QUALIFIED_IDENTIFIER = "qualified_identifier"
    SCOPED_IDENTIFIER = "scoped_identifier"
    SCOPE_RESOLUTION = "scope_resolution"
    THIS = "this"

    # Literals
    NULLPTR = "nullptr"
    USER_DEFINED_LITERAL = "user_defined_literal"
    RAW_STRING_LITERAL = "raw_string_literal"

    # Declarations
    DECLARATION = "declaration"
    INIT_DECLARATOR = "init_declarator"
    FIELD_DECLARATION = "field_declaration"
    FRIEND_DECLARATION = "friend_declaration"
    USING_DECLARATION = "using_declaration"
    ALIAS_DECLARATION = "alias_declaration"
    STATIC_ASSERT_DECLARATION = "static_assert_declaration"
    ACCESS_SPECIFIER = "access_specifier"
    FUNCTION_DECLARATOR = "function_declarator"

    # Definitions
    FUNCTION_DEFINITION = "function_definition"
    NAMESPACE_DEFINITION = "namespace_definition"
    CONCEPT_DEFINITION = "concept_definition"

    # Class / struct
    CLASS_SPECIFIER = "class_specifier"
    STRUCT_SPECIFIER = "struct_specifier"

    # Templates
    TEMPLATE_DECLARATION = "template_declaration"
    TEMPLATE_FUNCTION = "template_function"
    TEMPLATE_PARAMETER_LIST = "template_parameter_list"
    TEMPLATE_PARAMETER_DECLARATION = "template_parameter_declaration"

    # Expressions
    NEW_EXPRESSION = "new_expression"
    DELETE_EXPRESSION = "delete_expression"
    LAMBDA_EXPRESSION = "lambda_expression"
    THROW_EXPRESSION = "throw_expression"
    ASSIGNMENT_EXPRESSION = "assignment_expression"
    SUBSCRIPT_EXPRESSION = "subscript_expression"
    CONDITION_CLAUSE = "condition_clause"

    # Cast expressions
    STATIC_CAST_EXPRESSION = "static_cast_expression"
    DYNAMIC_CAST_EXPRESSION = "dynamic_cast_expression"
    REINTERPRET_CAST_EXPRESSION = "reinterpret_cast_expression"
    CONST_CAST_EXPRESSION = "const_cast_expression"

    # Statements
    IF_STATEMENT = "if_statement"
    WHILE_STATEMENT = "while_statement"
    FOR_RANGE_LOOP = "for_range_loop"
    TRY_STATEMENT = "try_statement"
    THROW_STATEMENT = "throw_statement"

    # Statement / block parts
    COMPOUND_STATEMENT = "compound_statement"
    PARAMETER_LIST = "parameter_list"
    ARGUMENT_LIST = "argument_list"
    SUBSCRIPT_ARGUMENT_LIST = "subscript_argument_list"

    # Exception handling
    CATCH_CLAUSE = "catch_clause"
    CATCH_DECLARATOR = "catch_declarator"

    # Field initializers
    FIELD_INITIALIZER_LIST = "field_initializer_list"
    FIELD_INITIALIZER = "field_initializer"

    # Keywords (used in type-based filtering)
    ELSE_KEYWORD = "else"
    THROW_KEYWORD = "throw"
