# pyright: standard
"""Semantic feature enumeration for the PHP language frontend."""

from __future__ import annotations

from enum import Enum


class PhpFeature(Enum):
    """Semantic features of the PHP language."""

    # Declarations
    VARIABLE_ASSIGNMENT = "$x = expr variable assignment declarations"
    FUNCTION_DECLARATION = "function f(...) { } function declarations"
    CLASS = "class declarations"
    INTERFACE = "interface declarations with member signatures"
    TRAIT = "trait declarations for mixin composition"
    ENUM = "enum declarations (PHP 8.1+)"
    NAMESPACE = "namespace declarations"
    USE_DECLARATION = "use Class\\Name import declarations"

    # Expressions
    ARITHMETIC = "+, -, *, /, % arithmetic expressions"
    ASSIGNMENT_EXPRESSION = "= and compound assignment operator expressions"
    FUNCTION_CALL = "f(...) function call expressions"
    METHOD_CALL = "$obj->method(...) instance method call expressions"
    MEMBER_ACCESS = "$obj->prop member property access expressions"
    NULLSAFE_MEMBER_ACCESS = "$obj?->prop null-safe member access expressions"
    SCOPED_CALL = "Class::method(...) static method call expressions"
    SCOPED_PROPERTY_ACCESS = "Class::$prop static property access expressions"
    CLASS_CONSTANT_ACCESS = "Class::CONST class constant access expressions"
    ARROW_FUNCTION = "fn($x) => expr arrow function expressions (PHP 7.4+)"
    ANONYMOUS_FUNCTION = "function($x) { } anonymous function expressions"
    ARRAY_CREATION = "array(...) and [...] array creation expressions"
    STRING_INTERPOLATION = '"...{$expr}..." double-quoted string interpolation'
    HEREDOC = "<<<EOT ... EOT heredoc string literals"
    YIELD = "yield and yield from generator expressions"
    VARIADIC_UNPACKING = "...$args variadic unpacking in calls"
    DYNAMIC_VARIABLE = "$$var dynamic variable-variable expressions"
    REFERENCE_ASSIGNMENT = "$x = &$y reference assignment expressions"
    RELATIVE_SCOPE = "self::, parent::, static:: relative scope references"
    TYPE_CAST = "(int), (string) etc. type cast expressions"
    TERNARY = "cond ? a : b and cond ?: b ternary and Elvis expressions"
    OBJECT_CREATION = "new ClassName(...) object instantiation"
    CLONE = "clone $obj object cloning expressions"
    ERROR_SUPPRESSION = "@expr error-suppression operator"
    SEQUENCE_EXPRESSION = "a, b comma-separated sequential evaluation"

    # Control flow
    IF_ELSE = "if / elseif / else conditional branching"
    WHILE_LOOP = "while (cond) loops"
    FOR_LOOP = "for (init; cond; update) loops"
    FOREACH = "foreach ($arr as $k => $v) iteration loops"
    SWITCH_STATEMENT = "switch / case / default statements"
    DO_WHILE = "do { } while (cond) loops"
    MATCH_EXPRESSION = "match (expr) { pattern => value } expressions (PHP 8.0+)"
    RETURN = "return and return expr statements"
    THROW = "throw new ExcType(...) throw statements"
    GOTO = "goto label unconditional jumps"
    LABELED_STATEMENT = "label: statement labels for goto targets"
    TRY_CATCH_FINALLY = "try / catch / finally exception handling"

    # OOP
    PROPERTY_DECLARATION = "public/private/protected $prop property declarations"

    # Misc
    ECHO = "echo expr output statements"
    STATIC_DECLARATION = "static $x = val static variable declarations in functions"
    GLOBAL_DECLARATION = "global $x global variable import declarations"
    INCLUDE_REQUIRE = "include, require, include_once, require_once file inclusion"
    ENUM_CASE = "case Name enum case declarations"
    PRINT = "print expr output expressions"
    FALLBACK = "fallback path for unsupported syntax nodes"
    CONST_DECLARATION = "const NAME = value constant declarations"
    NAMESPACE_USE = "use Foo\\Bar namespace import declarations"
