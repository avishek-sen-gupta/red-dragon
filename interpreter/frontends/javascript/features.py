# pyright: standard
"""Semantic feature enumeration for the JavaScript language frontend."""

from __future__ import annotations

from enum import Enum


class JavaScriptFeature(Enum):
    """Semantic features of the JavaScript language."""

    # Declarations
    VARIABLE_DECLARATION = "let, const, and var variable declarations"

    # Expressions
    ARITHMETIC = "+, -, *, /, % arithmetic expressions"
    TERNARY = "cond ? a : b ternary expressions"
    TEMPLATE_LITERAL = "backtick template literal strings with ${} interpolation"
    FUNCTION_CALL = "f(...) function call expressions"
    METHOD_CALL = "obj.method(...) method call expressions"
    OBJECT_LITERAL = "{ key: value } object literal expressions"
    ARRAY_LITERAL = "[a, b, c] array literal expressions"
    INCREMENT_DECREMENT = "x++, x--, ++x, --x increment/decrement operators"
    SEQUENCE_EXPRESSION = "a, b comma-separated sequential evaluation expressions"
    MODULE_METADATA = "import.meta module metadata property expression"
    NEW_TARGET = "new.target meta-property expression in constructors"

    # Control flow
    IF_ELSE = "if / else if / else conditional branching"
    WHILE_LOOP = "while (cond) loops"
    FOR_LOOP = "for (init; cond; update) loops"
    FOR_IN_LOOP = "for (key in obj) property enumeration loops"
    FOR_OF_LOOP = "for (val of iterable) value iteration loops"
    BREAK_CONTINUE = "break and continue statements"
    SWITCH_STATEMENT = "switch / case / default statements"
    TRY_CATCH = "try / catch / finally exception handling"
    THROW = "throw expr exception throwing"
    WITH_STATEMENT = "with (obj) { } scope extension statements"

    # Functions
    FUNCTION_DECLARATION = "function f(...) { } function declarations"
    ARROW_FUNCTION = "(x) => expr and (x) => { } arrow function expressions"
    LAMBDA = "anonymous function expressions"
    ASYNC_AWAIT = "async function declarations and await expressions"
    GENERATOR = "function* generator declarations and yield expressions"

    # Classes
    CLASS = "class declarations"
    OBJECT_CREATION = "new Foo() object instantiation"
    SUPER = "super keyword for parent class access"

    # Misc
    IMPORT = "import declarations (ES modules)"
    EXPORT = "default export declarations"
    EXPORT_NAMED = "export { a, b } clause of locally-declared names"
    EXPORT_REEXPORT = "export { a } from './module' re-export from another module"
    SPREAD = "...expr spread and rest operators"
    DESTRUCTURING = "{ a, b } = obj and [a, b] = arr destructuring assignments"
    OPTIONAL_CHAIN = "obj?.prop and obj?.method() optional chaining"
    DO_WHILE_LOOP = "do { } while (cond) loops"
    LABELED_STATEMENT = "label: statement labels for targeted break/continue"
    REGEX_LITERAL = "/pattern/flags regular expression literals"
