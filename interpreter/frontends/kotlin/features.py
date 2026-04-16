# pyright: standard
"""Semantic feature enumeration for the Kotlin language frontend."""

from __future__ import annotations

from enum import Enum


class KotlinFeature(Enum):
    """Semantic features of the Kotlin language."""

    # Declarations
    VAL_DECLARATION = "val immutable variable declarations"
    VAR_DECLARATION = "var mutable variable declarations"
    FUNCTION_DECLARATION = "fun f(...): ReturnType function declarations"
    CLASS = "class declarations"
    INTERFACE = "interface declarations"
    OBJECT_DECLARATION = "object Foo singleton declarations"
    OBJECT_LITERAL = "object : Type { } anonymous object expressions"
    COMPANION_OBJECT = "companion object { } companion singleton declarations"
    ENUM_CLASS = "enum class declarations with entries"
    TYPE_ALIAS = "typealias Foo = Bar type alias declarations"

    # Constructors and properties
    PRIMARY_CONSTRUCTOR = "class Foo(val x: T) primary constructor declarations"
    SECONDARY_CONSTRUCTOR = "constructor(...) secondary constructor declarations"
    PROPERTY_ACCESSOR = "get() and set(v) property accessor declarations"
    SETTER = "set(value) { } property setter declarations"
    GETTER = "get() { } property getter declarations"

    # Parameters and defaults
    DEFAULT_PARAMETERS = "function parameters with default values"

    # Expressions
    ARITHMETIC = "+, -, *, /, % arithmetic expressions"
    FUNCTION_CALL = "f(...) function call expressions"
    METHOD_CALL = "obj.method(...) method call expressions"
    NAVIGATION_EXPRESSION = "obj.member dot navigation expressions"
    LAMBDA = "{ x -> expr } and { expr } lambda expressions"
    ANONYMOUS_FUNCTION = "fun(x: T) anonymous function expressions"
    STRING_INTERPOLATION = '"${expr}" and "$name" string interpolation'
    TEMPLATE_STRING = 'multi-line """...""" template strings'
    CALLABLE_REFERENCE = "Foo::bar and obj::method callable references"
    RANGE_EXPRESSION = "a..b and a until b range expressions"
    INFIX_EXPRESSION = "infix function calls like a to b"
    INDEXING = "a[i] index access expressions"
    SPREAD = "*array spread operator in function calls"
    CHECK_EXPRESSION = "is and !is type-check expressions"
    TYPE_TEST = "expr is Type type test expressions"
    AS_EXPRESSION = "expr as Type safe and unsafe cast expressions"
    ELVIS_EXPRESSION = "expr ?: default Elvis operator"
    NOT_NULL_ASSERTION = "expr!! non-null assertion operator"
    THROW_EXPRESSION = "throw Exc() used as an expression"
    BITWISE = "and, or, xor, shl, shr bitwise operations"
    CHAR_LITERAL = "'c' character literals"
    HEX_LITERAL = "0x-prefixed hexadecimal integer literals"
    UNSIGNED_LITERAL = "42u and 42uL unsigned integer literals"
    NULL_LITERAL = "null null value literal"

    # Control flow
    IF_EXPRESSION = "if (cond) expr else expr conditional expressions"
    WHEN_EXPRESSION = "when (x) { P -> expr } expression form"
    WHEN_STATEMENT = "when (x) { P -> stmt } statement form"
    WHEN_SUBJECT_BINDING = "when (val x = expr) { } subject binding in when"
    WHILE_LOOP = "while (cond) { } loop statements"
    DO_WHILE_LOOP = "do { } while (cond) loop statements"
    FOR_LOOP = "for (x in collection) loop statements"
    FOR_LOOP_DESTRUCTURING = "for ((a, b) in pairs) destructuring for loops"
    RETURN = "return and return@label statements"
    BREAK_CONTINUE = "break, continue, break@label, continue@label statements"
    LABELED_STATEMENT = "label@ statement labels for targeted returns and jumps"

    # Type system
    GENERIC_TYPES = "generic type parameters and arguments"
    DESTRUCTURING = "(a, b) = pair component destructuring"

    # Assignment
    ASSIGNMENT = "= and compound assignment operators"

    # Exception handling
    EXCEPTION_HANDLING = "try / catch / finally exception handling"

    # Implicit features
    IMPLICIT_THIS = "implicit this in member access and method calls"

    # Misc
    WILDCARD_IMPORT = "import foo.* wildcard imports"
    LINE_COMMENT = "// single-line comment handling"
    OVERLOAD_RESOLUTION = "operator overloading and overload resolution"
