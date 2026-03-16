"""Kotlin tree-sitter node type constants."""


class KotlinNodeType:
    """Constants for Kotlin tree-sitter node type strings."""

    # -- identifiers & literals ------------------------------------------
    SIMPLE_IDENTIFIER = "simple_identifier"
    INTEGER_LITERAL = "integer_literal"
    LONG_LITERAL = "long_literal"
    REAL_LITERAL = "real_literal"
    CHARACTER_LITERAL = "character_literal"
    STRING_LITERAL = "string_literal"
    BOOLEAN_LITERAL = "boolean_literal"
    NULL_LITERAL = "null_literal"
    HEX_LITERAL = "hex_literal"
    UNSIGNED_LITERAL = "unsigned_literal"
    LABEL = "label"

    # -- string interpolation --------------------------------------------
    STRING_CONTENT = "string_content"
    INTERPOLATED_IDENTIFIER = "interpolated_identifier"
    INTERPOLATED_EXPRESSION = "interpolated_expression"

    # -- expressions -----------------------------------------------------
    ADDITIVE_EXPRESSION = "additive_expression"
    MULTIPLICATIVE_EXPRESSION = "multiplicative_expression"
    COMPARISON_EXPRESSION = "comparison_expression"
    EQUALITY_EXPRESSION = "equality_expression"
    CONJUNCTION_EXPRESSION = "conjunction_expression"
    DISJUNCTION_EXPRESSION = "disjunction_expression"
    PREFIX_EXPRESSION = "prefix_expression"
    POSTFIX_EXPRESSION = "postfix_expression"
    PARENTHESIZED_EXPRESSION = "parenthesized_expression"
    CALL_EXPRESSION = "call_expression"
    NAVIGATION_EXPRESSION = "navigation_expression"
    IF_EXPRESSION = "if_expression"
    WHEN_EXPRESSION = "when_expression"
    COLLECTION_LITERAL = "collection_literal"
    THIS_EXPRESSION = "this_expression"
    SUPER_EXPRESSION = "super_expression"
    LAMBDA_LITERAL = "lambda_literal"
    OBJECT_LITERAL = "object_literal"
    RANGE_EXPRESSION = "range_expression"
    CHECK_EXPRESSION = "check_expression"
    TRY_EXPRESSION = "try_expression"
    ELVIS_EXPRESSION = "elvis_expression"
    INFIX_EXPRESSION = "infix_expression"
    INDEXING_EXPRESSION = "indexing_expression"
    AS_EXPRESSION = "as_expression"
    JUMP_EXPRESSION = "jump_expression"
    ANONYMOUS_FUNCTION = "anonymous_function"
    TYPE_TEST = "type_test"
    CALLABLE_REFERENCE = "callable_reference"
    SPREAD_EXPRESSION = "spread_expression"

    # -- declarations & statements ---------------------------------------
    PROPERTY_DECLARATION = "property_declaration"
    VARIABLE_DECLARATION = "variable_declaration"
    MULTI_VARIABLE_DECLARATION = "multi_variable_declaration"
    FUNCTION_DECLARATION = "function_declaration"
    CLASS_DECLARATION = "class_declaration"
    OBJECT_DECLARATION = "object_declaration"
    ASSIGNMENT = "assignment"
    WHILE_STATEMENT = "while_statement"
    FOR_STATEMENT = "for_statement"
    DO_WHILE_STATEMENT = "do_while_statement"
    IMPORT_LIST = "import_list"
    IMPORT_HEADER = "import_header"
    WILDCARD_IMPORT = "wildcard_import"
    PACKAGE_HEADER = "package_header"
    TYPE_ALIAS = "type_alias"
    SOURCE_FILE = "source_file"
    STATEMENTS = "statements"

    # -- parameters & arguments ------------------------------------------
    PARAMETER = "parameter"
    FUNCTION_VALUE_PARAMETERS = "function_value_parameters"
    VALUE_ARGUMENT = "value_argument"
    VALUE_ARGUMENTS = "value_arguments"
    LAMBDA_PARAMETERS = "lambda_parameters"

    # -- types -----------------------------------------------------------
    USER_TYPE = "user_type"
    NULLABLE_TYPE = "nullable_type"
    TYPE_IDENTIFIER = "type_identifier"

    # -- function & class body -------------------------------------------
    FUNCTION_BODY = "function_body"
    CLASS_BODY = "class_body"
    ENUM_CLASS_BODY = "enum_class_body"
    CONTROL_STRUCTURE_BODY = "control_structure_body"

    # -- class internals -------------------------------------------------
    PRIMARY_CONSTRUCTOR = "primary_constructor"
    CLASS_PARAMETER = "class_parameter"
    BINDING_PATTERN_KIND = "binding_pattern_kind"
    COMPANION_OBJECT = "companion_object"
    ENUM_ENTRY = "enum_entry"
    DELEGATION_SPECIFIER = "delegation_specifier"
    SECONDARY_CONSTRUCTOR = "secondary_constructor"
    CONSTRUCTOR_DELEGATION_CALL = "constructor_delegation_call"
    SETTER = "setter"
    GETTER = "getter"

    # -- suffixes --------------------------------------------------------
    CALL_SUFFIX = "call_suffix"
    NAVIGATION_SUFFIX = "navigation_suffix"
    INDEXING_SUFFIX = "indexing_suffix"

    # -- control flow helpers --------------------------------------------
    RETURN = "return"
    CATCH_BLOCK = "catch_block"
    FINALLY_BLOCK = "finally_block"
    WHEN_SUBJECT = "when_subject"
    WHEN_ENTRY = "when_entry"
    WHEN_CONDITION = "when_condition"
    DIRECTLY_ASSIGNABLE_EXPRESSION = "directly_assignable_expression"

    # -- comments --------------------------------------------------------
    COMMENT = "comment"
    MULTILINE_COMMENT = "multiline_comment"
    LINE_COMMENT = "line_comment"
