# pyright: standard
"""Semantic feature enumeration for the Pascal language frontend."""

from __future__ import annotations

from enum import Enum


class PascalFeature(Enum):
    """Semantic features of the Pascal language."""

    # Declarations
    VARIABLE_DECLARATION = "var x: T variable declarations"
    CONST_DECLARATION = "const x = value constant declarations"
    TYPE_DECLARATION = "type Foo = ... type alias declarations"
    USES_CLAUSE = "uses Unit1, Unit2 unit import declarations"
    PROCEDURE_DECLARATION = "procedure P(...) subroutine declarations"
    FUNCTION_DECLARATION = "function F(...): T function declarations"
    CLASS_DECLARATION = "class type declarations"
    ENUM_DECLARATION = "(A, B, C) enumeration type declarations"
    FIELD_DECLARATION = "field declarations inside class and record types"
    ARRAY_DECLARATION = "array[range] of T array type declarations"
    DEFAULT_PARAMETER_VALUES = "function parameters with default values"
    MODULE_NAME = "program Name and unit Name module name declarations"

    # Expressions
    ARITHMETIC = "+, -, *, /, div, mod arithmetic expressions"
    DOT_ACCESS = "obj.field dot member access expressions"
    SUBSCRIPT_ACCESS = "a[i] array element access expressions"
    UNARY_EXPRESSION = "unary -, not, and @ operator expressions"
    PARENTHESIZED_EXPRESSION = "(expr) parenthesized expressions"
    RANGE_EXPRESSION = "low..high subrange expressions"
    BITWISE_OPERATORS = "and, or, xor, shl, shr bitwise operators"
    SET_LITERAL = "[a, b, c] set literal expressions"

    # Statements
    ASSIGNMENT = ":= assignment statements"
    PROCEDURE_CALL = "P(...) procedure call statements"
    FUNCTION_CALL = "F(...) function call expressions"
    LABEL_DECLARATION = "label n; label declarations for goto targets"

    # Control flow
    IF_ELSE = "if cond then ... else ... conditional statements"
    WHILE_LOOP = "while cond do ... loop statements"
    FOR_LOOP = "for i := start to/downto limit do ... loop statements"
    REPEAT_UNTIL = "repeat ... until cond loop statements"
    CASE_STATEMENT = "case expr of ... end case branch statements"
    FOREACH = "for x in collection do ... foreach iteration (FPC)"
    GOTO = "goto label unconditional jumps"
    WITH_STATEMENT = "with obj do ... field-shorthand access blocks"

    # OOP
    CLASS_BODY = "class body with fields, methods, and properties"
    PROPERTY_ACCESSORS = (
        "property Prop: T read FField write FField accessor declarations"
    )
    FIELD_ACCESSORS = "getter/setter field accessor method declarations"
    INHERITED = "inherited method invocation in overriding methods"
    QUALIFIED_PROCEDURE = "TClass.Method qualified method declarations"
    METHOD_DECLARATION = "method declarations within class body"
    VISIBILITY_MODIFIERS = "public, private, protected, published visibility sections"

    # Exception handling
    TRY_EXCEPT = "try ... except ... end exception handling blocks"
    TRY_FINALLY = "try ... finally ... end cleanup blocks"
    EXCEPTION_HANDLER = "on E: ExcType do ... typed exception handler clauses"
    RAISE = "raise and raise ExcObj exception raising statements"

    # Misc
    FALLBACK = "fallback path for unsupported syntax nodes"
    VAR_TYPE_TRACKING = "tracking declared variable types through the IR"
    ASSIGNMENT_INTERCEPTION = "intercepting assignments for special Pascal semantics"
    FUNCTION_RESULT = "Result := value implicit function result variable"
