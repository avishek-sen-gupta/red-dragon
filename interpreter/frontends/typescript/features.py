# pyright: standard
"""Semantic feature enumeration for the TypeScript language frontend."""

from __future__ import annotations

from enum import Enum


class TypeScriptFeature(Enum):
    """Semantic features of the TypeScript language (beyond JavaScript)."""

    # Type system
    TYPE_ANNOTATION = ": Type annotations on variables, parameters, and return types"
    TYPE_ALIAS = "type Foo = Bar type alias declarations"
    INTERFACE = "interface declarations with member signatures"
    ENUM = "const and non-const enum declarations"
    GENERIC_TYPES = "generic type parameters <T> on functions and classes"

    # Type narrowing
    TYPE_ASSERTION = "expr as Type and <Type>expr casts"
    NON_NULL_ASSERTION = "expr! non-null assertion operator"
    SATISFIES_EXPRESSION = "expr satisfies Type constraint (TypeScript 4.9+)"

    # Declarations
    VARIABLE_DECLARATION = "let, const, and var variable declarations"
    FUNCTION_DECLARATION = "function f(...): ReturnType declarations"
    CLASS = "class declarations with TypeScript type members"

    # Expressions
    ARITHMETIC = "+, -, *, /, % arithmetic expressions"
    OPTIONAL_CHAIN = "obj?.prop and obj?.method() optional chaining"
    INSTANCEOF = "instanceof type-check expressions"

    # Functions
    FUNCTION_OVERLOAD = "multiple function overload signatures"
    AMBIENT_DECLARATION = "declare keyword for ambient type declarations"
    INSTANTIATION_EXPRESSION = (
        "Array<number> instantiation expressions (TypeScript 4.7+)"
    )

    # Control flow
    IF_ELSE = "if / else if / else conditional branching"
    FOR_LOOP = "for (init; cond; update) loops"
    WHILE_LOOP = "while (cond) loops"

    # Classes & OOP
    INHERITANCE = "extends clause in class declarations"
    INTERFACE_IMPLEMENTATION = "implements clause in class declarations"
    ABSTRACT_CLASS = "abstract class declarations"
    ABSTRACT_METHOD = "abstract method declarations in abstract classes"
    CLASS_STATIC_BLOCK = "static { } initializer blocks in classes"
    PUBLIC_FIELD = "public class field declarations"

    # Access modifiers
    PUBLIC_MODIFIER = "public visibility modifier on class members"
    PRIVATE_MODIFIER = "private visibility modifier on class members"
    PROTECTED_MODIFIER = "protected visibility modifier on class members"
    READONLY_MODIFIER = "readonly modifier on properties and parameters"
    STATIC_MODIFIER = "static modifier on class members"

    # Modules & Namespaces
    NAMESPACE = "namespace and module declarations"
    IMPORT = "import declarations"
    EXPORT = "export declarations"
    IMPORT_ALIAS = "import { X as Y } alias bindings"
    REQUIRE_IMPORT = 'require("module") CommonJS-style imports'
