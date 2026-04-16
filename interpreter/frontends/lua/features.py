# pyright: standard
"""Semantic feature enumeration for the Lua language frontend."""

from __future__ import annotations

from enum import Enum


class LuaFeature(Enum):
    """Semantic features of the Lua language."""

    # Declarations
    LOCAL_VARIABLE_DECLARATION = "local x = expr local variable declarations"
    ASSIGNMENT = "x = expr and multi-target assignment statements"
    FUNCTION_DECLARATION = "function f(...) end named function declarations"
    DOTTED_FUNCTION_DECLARATION = (
        "function a.b.c(...) end dotted-name function declarations"
    )
    ANONYMOUS_FUNCTION = "function(...) end anonymous function expressions"

    # Expressions
    ARITHMETIC = "+, -, *, /, %, // arithmetic expressions"
    OPERATORS = "comparison, logical, and concatenation operators"
    FUNCTION_CALL = "f(...) function call expressions"
    METHOD_CALL = "obj:method(...) colon-style method call expressions"
    METHOD_INDEX_EXPRESSION = "obj:method and obj.field member index expressions"
    DOTTED_FUNCTION_CALL = "a.b.c(...) dotted-path function call expressions"
    VARARG = "... variadic argument expressions"
    BITWISE_XOR = "~ bitwise XOR operator (Lua 5.3+)"

    # Tables
    TABLE_CONSTRUCTOR = "{ k = v, ... } table constructor expressions"
    TABLE_ACCESS = "t[k] and t.k table field access expressions"

    # Control flow
    IF_ELSE = "if cond then ... elseif ... else ... end conditional branching"
    WHILE_LOOP = "while cond do ... end loop statements"
    FOR_LOOP = "for i = start, limit, step do ... end numeric for loops"
    REPEAT_UNTIL = "repeat ... until cond loop statements"
    GENERIC_FOR = "for k, v in iter do ... end generic for loops"
    BREAK = "break loop exit statements"
    GOTO = "goto label unconditional jumps (Lua 5.2+)"
    LABEL = "::label:: label declarations for goto targets"
    DO_BLOCK = "do ... end explicit block scope statements"

    # Strings
    STRING_ESCAPE = "escape sequences in string literals"
