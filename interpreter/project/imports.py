"""Import extraction — parse source and return ImportRef list.

Dispatches to per-language extraction functions. Each language implements
a pure function that walks the tree-sitter AST to find import nodes.
"""

from __future__ import annotations

import re
from pathlib import Path

from interpreter.constants import Language
from interpreter.parser import TreeSitterParserFactory
from interpreter.project.types import ImportRef

_parser_factory = TreeSitterParserFactory()


def extract_imports(
    source: bytes,
    source_file: Path,
    language: Language,
) -> list[ImportRef]:
    """Extract import statements from source code.

    Parses with tree-sitter and walks top-level children to find
    import nodes. Dispatches to per-language extractors.

    Args:
        source: Raw source bytes.
        source_file: Path of the source file (used in ImportRef.source_file).
        language: Source language.

    Returns:
        List of ImportRef objects found in the source.
    """
    # COBOL uses a separate parser (ProLeap), not tree-sitter.
    # Use regex-based extraction directly on source bytes.
    if language == Language.COBOL:
        return _extract_cobol_imports(source, source_file)

    extractor = _EXTRACTORS.get(language)
    if extractor is None:
        return []

    parser = _parser_factory.get_parser(language)
    tree = parser.parse(source)
    refs: list[ImportRef] = []

    for child in tree.root_node.children:
        extracted = extractor(child, source, source_file)
        if extracted:
            refs.extend(extracted)

    return refs


# ── Helpers ──────────────────────────────────────────────────────


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")


# ── Python import extraction ─────────────────────────────────────


def _extract_python_import(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Dispatch Python import node types."""
    if node.type == "import_statement":
        return _python_import_statement(node, source, source_file)
    if node.type == "import_from_statement":
        return _python_import_from_statement(node, source, source_file)
    return None


def _python_import_statement(
    node, source: bytes, source_file: Path
) -> list[ImportRef]:
    """Handle: import os, import os.path, import numpy as np"""
    refs: list[ImportRef] = []

    for child in node.children:
        if child.type == "dotted_name":
            refs.append(
                ImportRef(
                    source_file=source_file,
                    module_path=_node_text(child, source),
                    kind="import",
                )
            )
        elif child.type == "aliased_import":
            # import numpy as np → aliased_import > dotted_name + identifier
            module_path = ""
            alias = None
            for sub in child.children:
                if sub.type == "dotted_name":
                    module_path = _node_text(sub, source)
                elif sub.type == "identifier":
                    alias = _node_text(sub, source)
            if module_path:
                refs.append(
                    ImportRef(
                        source_file=source_file,
                        module_path=module_path,
                        kind="import",
                        alias=alias,
                    )
                )

    return refs


def _python_import_from_statement(
    node, source: bytes, source_file: Path
) -> list[ImportRef]:
    """Handle: from X import Y, from . import Z, from ..pkg import W"""
    is_relative = False
    relative_level = 0
    module_path = ""

    # Look for relative_import node
    for child in node.children:
        if child.type == "relative_import":
            is_relative = True
            for sub in child.children:
                if sub.type == "import_prefix":
                    prefix_text = _node_text(sub, source)
                    relative_level = prefix_text.count(".")
                elif sub.type == "dotted_name":
                    module_path = _node_text(sub, source)
            break

    # If not relative, look for module_name field or dotted_name before 'import'
    if not is_relative:
        module_node = node.child_by_field_name("module_name")
        if module_node:
            module_path = _node_text(module_node, source)
        else:
            for child in node.children:
                if child.type == "import":
                    break
                if child.type == "dotted_name":
                    module_path = _node_text(child, source)

    # Collect imported names
    names: list[str] = []
    found_import_keyword = False
    for child in node.children:
        if child.type == "import":
            found_import_keyword = True
            continue
        if not found_import_keyword:
            continue

        if child.type == "wildcard_import" or _node_text(child, source) == "*":
            names = ["*"]
            break
        if child.type in ("dotted_name", "identifier"):
            names.append(_node_text(child, source))
        elif child.type == "aliased_import":
            name_node = child.child_by_field_name("name")
            if name_node:
                names.append(_node_text(name_node, source))

    return [
        ImportRef(
            source_file=source_file,
            module_path=module_path,
            names=tuple(names),
            is_relative=is_relative,
            relative_level=relative_level,
            kind="import",
        )
    ]


# ── JavaScript / TypeScript import extraction ────────────────────


def _extract_js_import(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Dispatch JS/TS import node types."""
    if node.type == "import_statement":
        return _js_import_statement(node, source, source_file)
    # CJS require: lexical_declaration or expression_statement containing require()
    if node.type in ("lexical_declaration", "expression_statement"):
        return _js_require_call(node, source, source_file)
    return None


def _js_import_statement(
    node, source: bytes, source_file: Path
) -> list[ImportRef]:
    """Handle ESM: import { foo } from './utils'; import X from 'mod'"""
    # Find the source string (after 'from')
    source_str = ""
    for child in node.children:
        if child.type == "string":
            source_str = _extract_string_content(child, source)
            break

    if not source_str:
        return []

    is_relative = source_str.startswith(".") or source_str.startswith("/")
    is_system = not is_relative

    # Collect imported names
    names: list[str] = []
    for child in node.children:
        if child.type == "import_clause":
            for sub in child.children:
                if sub.type == "named_imports":
                    for spec in sub.children:
                        if spec.type == "import_specifier":
                            name_node = spec.child_by_field_name("name")
                            if name_node:
                                names.append(_node_text(name_node, source))
                            else:
                                # Simple identifier child
                                for sc in spec.children:
                                    if sc.type == "identifier":
                                        names.append(_node_text(sc, source))
                                        break
                elif sub.type == "identifier":
                    # Default import: import Foo from 'bar'
                    names.append(_node_text(sub, source))
                elif sub.type == "namespace_import":
                    names = ["*"]

    return [
        ImportRef(
            source_file=source_file,
            module_path=source_str,
            names=tuple(names),
            is_relative=is_relative,
            is_system=is_system,
            kind="import",
        )
    ]


def _js_require_call(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Handle CJS: const X = require('./utils')"""
    # Walk to find a call_expression with identifier 'require'
    calls = _find_nodes_by_type(node, "call_expression")
    refs: list[ImportRef] = []
    for call in calls:
        func_node = call.child_by_field_name("function")
        if func_node and func_node.type == "identifier" and _node_text(func_node, source) == "require":
            args = call.child_by_field_name("arguments")
            if args:
                for arg_child in args.children:
                    if arg_child.type == "string":
                        path = _extract_string_content(arg_child, source)
                        is_relative = path.startswith(".") or path.startswith("/")
                        refs.append(
                            ImportRef(
                                source_file=source_file,
                                module_path=path,
                                kind="require",
                                is_relative=is_relative,
                                is_system=not is_relative,
                            )
                        )
    return refs or None


# ── Java import extraction ───────────────────────────────────────


def _extract_java_import(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Dispatch Java import_declaration."""
    if node.type == "import_declaration":
        return _java_import_declaration(node, source, source_file)
    return None


def _java_import_declaration(
    node, source: bytes, source_file: Path
) -> list[ImportRef]:
    """Handle: import com.example.Utils; import static com.example.Math.add;"""
    text = _node_text(node, source).strip().rstrip(";").strip()

    # Remove 'import' keyword and optional 'static'
    is_static = "static" in text
    text = text.replace("import", "").replace("static", "").strip()

    # Check for wildcard
    names: tuple[str, ...] = ()
    if text.endswith(".*"):
        text = text[:-2]
        names = ("*",)
    else:
        # Last segment is the imported name
        parts = text.rsplit(".", 1)
        if len(parts) == 2:
            names = (parts[1],)
            text = parts[0]

    _JAVA_SYSTEM_PREFIXES = ("java.", "javax.", "sun.", "com.sun.")
    is_system = any(text.startswith(p) for p in _JAVA_SYSTEM_PREFIXES)

    return [
        ImportRef(
            source_file=source_file,
            module_path=text,
            names=names,
            kind="import",
            is_system=is_system,
        )
    ]


# ── Go import extraction ────────────────────────────────────────


def _extract_go_import(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Dispatch Go import_declaration."""
    if node.type == "import_declaration":
        return _go_import_declaration(node, source, source_file)
    return None


def _go_import_declaration(
    node, source: bytes, source_file: Path
) -> list[ImportRef]:
    """Handle: import "fmt"; import ("fmt"; "os/exec")"""
    refs: list[ImportRef] = []

    specs = _find_nodes_by_type(node, "import_spec")
    for spec in specs:
        # Alias (optional: named before the string)
        alias = None
        path_str = ""
        for child in spec.children:
            if child.type in ("interpreted_string_literal", "raw_string_literal"):
                path_str = _extract_string_content(child, source)
            elif child.type in ("package_identifier", "blank_identifier", "dot"):
                alias = _node_text(child, source)

        if not path_str:
            continue

        # System check: no dots in path = stdlib
        is_system = "." not in path_str and "/" not in path_str
        is_relative = path_str.startswith("./") or path_str.startswith("../")

        refs.append(
            ImportRef(
                source_file=source_file,
                module_path=path_str,
                kind="import",
                is_system=is_system,
                is_relative=is_relative,
                alias=alias,
            )
        )

    return refs


# ── Rust import extraction ───────────────────────────────────────


def _extract_rust_import(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Dispatch Rust use_declaration and mod_item."""
    if node.type == "use_declaration":
        return _rust_use_declaration(node, source, source_file)
    if node.type == "mod_item":
        return _rust_mod_item(node, source, source_file)
    return None


def _rust_use_declaration(
    node, source: bytes, source_file: Path
) -> list[ImportRef]:
    """Handle: use crate::utils; use std::collections::HashMap;"""
    text = _node_text(node, source).strip().rstrip(";").strip()
    text = text.removeprefix("use").strip()

    _RUST_SYSTEM_PREFIXES = ("std::", "core::", "alloc::")
    is_system = any(text.startswith(p) for p in _RUST_SYSTEM_PREFIXES)
    is_relative = text.startswith("crate::") or text.startswith("self::") or text.startswith("super::")

    # Extract names from use_list: use foo::{A, B}
    names: tuple[str, ...] = ()
    if "{" in text:
        brace_start = text.index("{")
        brace_end = text.index("}")
        inner = text[brace_start + 1 : brace_end]
        names = tuple(n.strip() for n in inner.split(",") if n.strip())
        text = text[:brace_start].rstrip(":")
    elif "::" in text:
        parts = text.rsplit("::", 1)
        if parts[1] == "*":
            names = ("*",)
            text = parts[0]
        else:
            names = (parts[1],)
            text = parts[0]

    return [
        ImportRef(
            source_file=source_file,
            module_path=text,
            names=names,
            kind="use",
            is_system=is_system,
            is_relative=is_relative,
        )
    ]


def _rust_mod_item(
    node, source: bytes, source_file: Path
) -> list[ImportRef]:
    """Handle: mod helpers;"""
    # Only external mod declarations (no body block)
    has_body = any(c.type == "declaration_list" for c in node.children)
    if has_body:
        return []

    mod_name = ""
    for child in node.children:
        if child.type == "identifier":
            mod_name = _node_text(child, source)
            break

    if not mod_name:
        return []

    return [
        ImportRef(
            source_file=source_file,
            module_path=mod_name,
            kind="mod",
            is_relative=True,
        )
    ]


# ── C / C++ import extraction ────────────────────────────────────


def _extract_c_import(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Dispatch C/C++ preproc_include."""
    if node.type == "preproc_include":
        return _c_preproc_include(node, source, source_file)
    return None


def _c_preproc_include(
    node, source: bytes, source_file: Path
) -> list[ImportRef]:
    """Handle: #include "header.h", #include <stdio.h>"""
    for child in node.children:
        if child.type == "system_lib_string":
            # <stdio.h> → system include
            path = _node_text(child, source).strip("<>")
            return [
                ImportRef(
                    source_file=source_file,
                    module_path=path,
                    kind="include",
                    is_system=True,
                )
            ]
        if child.type == "string_literal":
            path = _extract_string_content(child, source)
            return [
                ImportRef(
                    source_file=source_file,
                    module_path=path,
                    kind="include",
                    is_system=False,
                )
            ]
    return []


# ── C# import extraction ────────────────────────────────────────


def _extract_csharp_import(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Dispatch C# using_directive."""
    if node.type == "using_directive":
        return _csharp_using_directive(node, source, source_file)
    return None


def _csharp_using_directive(
    node, source: bytes, source_file: Path
) -> list[ImportRef]:
    """Handle: using System; using static System.Math; using X = System.Text;"""
    text = _node_text(node, source).strip().rstrip(";").strip()
    text = text.removeprefix("using").strip()

    alias = None
    is_static = False

    if text.startswith("static"):
        is_static = True
        text = text.removeprefix("static").strip()

    if "=" in text:
        parts = text.split("=", 1)
        alias = parts[0].strip()
        text = parts[1].strip()

    _CSHARP_SYSTEM_PREFIXES = ("System", "Microsoft")
    is_system = any(text.startswith(p) for p in _CSHARP_SYSTEM_PREFIXES)

    return [
        ImportRef(
            source_file=source_file,
            module_path=text,
            kind="using",
            is_system=is_system,
            alias=alias,
        )
    ]


# ── Kotlin import extraction ────────────────────────────────────


def _extract_kotlin_import(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Dispatch Kotlin import_list → import_header."""
    if node.type == "import_list":
        refs: list[ImportRef] = []
        for child in node.children:
            if child.type == "import_header":
                r = _kotlin_import_header(child, source, source_file)
                if r:
                    refs.extend(r)
        return refs or None
    if node.type == "import_header":
        return _kotlin_import_header(node, source, source_file)
    return None


def _kotlin_import_header(
    node, source: bytes, source_file: Path
) -> list[ImportRef]:
    """Handle: import com.example.Utils"""
    text = _node_text(node, source).strip()
    text = text.removeprefix("import").strip()

    names: tuple[str, ...] = ()
    alias = None

    # Handle alias: import com.example.Utils as U
    if " as " in text:
        parts = text.split(" as ", 1)
        text = parts[0].strip()
        alias = parts[1].strip()

    # Handle wildcard: import com.example.*
    if text.endswith(".*"):
        text = text[:-2]
        names = ("*",)
    elif "." in text:
        parts = text.rsplit(".", 1)
        text = parts[0]
        names = (parts[1],)

    _KOTLIN_SYSTEM_PREFIXES = ("java.", "javax.", "kotlin.", "kotlinx.")
    is_system = any(text.startswith(p) or (text + ".").startswith(p) for p in _KOTLIN_SYSTEM_PREFIXES)

    return [
        ImportRef(
            source_file=source_file,
            module_path=text,
            names=names,
            kind="import",
            is_system=is_system,
            alias=alias,
        )
    ]


# ── Scala import extraction ─────────────────────────────────────


def _extract_scala_import(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Dispatch Scala import_declaration."""
    if node.type == "import_declaration":
        return _scala_import_declaration(node, source, source_file)
    return None


def _scala_import_declaration(
    node, source: bytes, source_file: Path
) -> list[ImportRef]:
    """Handle: import scala.collection.mutable.{Map, Set}; import scala.io._"""
    text = _node_text(node, source).strip()
    text = text.removeprefix("import").strip()

    names: tuple[str, ...] = ()

    # Handle namespace_selectors: {A, B}
    if "{" in text:
        brace_start = text.index("{")
        brace_end = text.index("}")
        inner = text[brace_start + 1 : brace_end]
        names = tuple(n.strip() for n in inner.split(",") if n.strip())
        text = text[:brace_start].rstrip(".")
    elif text.endswith("._"):
        text = text[:-2]
        names = ("*",)
    elif "." in text:
        parts = text.rsplit(".", 1)
        text = parts[0]
        names = (parts[1],)

    _SCALA_SYSTEM_PREFIXES = ("scala.", "java.", "javax.")
    is_system = any(text.startswith(p) or (text + ".").startswith(p) for p in _SCALA_SYSTEM_PREFIXES)

    return [
        ImportRef(
            source_file=source_file,
            module_path=text,
            names=names,
            kind="import",
            is_system=is_system,
        )
    ]


# ── Ruby import extraction ──────────────────────────────────────


def _extract_ruby_import(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Dispatch Ruby require/require_relative calls."""
    if node.type == "call":
        func_node = None
        for child in node.children:
            if child.type == "identifier":
                func_node = child
                break
        if func_node is None:
            return None
        func_name = _node_text(func_node, source)
        if func_name in ("require", "require_relative"):
            return _ruby_require(node, source, source_file, func_name)
    return None


def _ruby_require(
    node, source: bytes, source_file: Path, func_name: str
) -> list[ImportRef]:
    """Handle: require "utils"; require_relative "./helpers" """
    arg_list = None
    for child in node.children:
        if child.type == "argument_list":
            arg_list = child
            break

    if arg_list is None:
        return []

    for child in arg_list.children:
        if child.type == "string":
            path = _extract_string_content(child, source)
            is_relative = func_name == "require_relative" or path.startswith("./") or path.startswith("../")
            is_system = not is_relative and "/" not in path and "." not in path
            return [
                ImportRef(
                    source_file=source_file,
                    module_path=path,
                    kind="require",
                    is_relative=is_relative,
                    is_system=is_system,
                )
            ]
    return []


# ── PHP import extraction ────────────────────────────────────────


def _extract_php_import(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Dispatch PHP namespace_use_declaration, require*, include*."""
    if node.type == "namespace_use_declaration":
        return _php_use_declaration(node, source, source_file)
    if node.type == "expression_statement":
        # require/include wrapped in expression_statement
        for child in node.children:
            if child.type in (
                "require_expression",
                "require_once_expression",
                "include_expression",
                "include_once_expression",
            ):
                return _php_require_include(child, source, source_file)
    return None


def _php_use_declaration(
    node, source: bytes, source_file: Path
) -> list[ImportRef]:
    """Handle: use App\\Models\\User;"""
    text = _node_text(node, source).strip().rstrip(";").strip()
    text = text.removeprefix("use").strip()

    # Extract the qualified name
    parts = text.rsplit("\\", 1)
    if len(parts) == 2:
        module_path = parts[0]
        names = (parts[1],)
    else:
        module_path = text
        names = ()

    return [
        ImportRef(
            source_file=source_file,
            module_path=module_path.replace("\\", "."),
            names=names,
            kind="use",
        )
    ]


def _php_require_include(
    node, source: bytes, source_file: Path
) -> list[ImportRef]:
    """Handle: require_once "helpers.php";"""
    for child in node.children:
        if child.type in ("string", "encapsed_string"):
            path = _extract_string_content(child, source)
            kind = "require" if "require" in node.type else "include"
            return [
                ImportRef(
                    source_file=source_file,
                    module_path=path,
                    kind=kind,
                    is_relative=path.startswith("./") or path.startswith("../"),
                )
            ]
    return []


# ── Lua import extraction ────────────────────────────────────────


def _extract_lua_import(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Dispatch Lua require() calls."""
    # require can appear as function_call at top level or inside variable_declaration
    if node.type == "function_call":
        return _lua_require_call(node, source, source_file)
    if node.type == "variable_declaration":
        # local utils = require("utils")
        calls = _find_nodes_by_type(node, "function_call")
        for call in calls:
            result = _lua_require_call(call, source, source_file)
            if result:
                return result
    return None


def _lua_require_call(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Handle: require("utils"), require "helpers" """
    # Check the function name is 'require'
    func_name = ""
    for child in node.children:
        if child.type == "identifier":
            func_name = _node_text(child, source)
            break

    if func_name != "require":
        return None

    # Find the string argument
    for child in node.children:
        if child.type == "arguments":
            for arg in child.children:
                if arg.type == "string":
                    path = _extract_string_content(arg, source)
                    is_relative = path.startswith("./") or path.startswith("../")
                    is_system = not is_relative and "." not in path and "/" not in path
                    return [
                        ImportRef(
                            source_file=source_file,
                            module_path=path,
                            kind="require",
                            is_relative=is_relative,
                            is_system=is_system,
                        )
                    ]
        elif child.type == "string":
            # require "helpers" (no parens)
            path = _extract_string_content(child, source)
            is_relative = path.startswith("./") or path.startswith("../")
            is_system = not is_relative and "." not in path and "/" not in path
            return [
                ImportRef(
                    source_file=source_file,
                    module_path=path,
                    kind="require",
                    is_relative=is_relative,
                    is_system=is_system,
                )
            ]
    return None


# ── Pascal import extraction ─────────────────────────────────────


def _extract_pascal_import(
    node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Dispatch Pascal declUses."""
    if node.type == "declUses":
        return _pascal_uses(node, source, source_file)
    return None


def _pascal_uses(
    node, source: bytes, source_file: Path
) -> list[ImportRef]:
    """Handle: uses SysUtils, Classes;"""
    _PASCAL_SYSTEM_UNITS = frozenset({
        "sysutils", "classes", "system", "types", "variants",
        "math", "strutils", "dateutils", "generics.collections",
        "generics.defaults", "rtlconsts", "character",
    })

    refs: list[ImportRef] = []
    for child in node.children:
        if child.type == "moduleName":
            for sub in child.children:
                if sub.type == "identifier":
                    name = _node_text(sub, source)
                    is_system = name.lower() in _PASCAL_SYSTEM_UNITS
                    refs.append(
                        ImportRef(
                            source_file=source_file,
                            module_path=name,
                            kind="using",
                            is_system=is_system,
                        )
                    )
    return refs


# ── COBOL import extraction (regex-based, no tree-sitter) ────────

# COPY copybook-name [OF|IN library-name].
_COBOL_COPY_RE = re.compile(
    r"\bCOPY\s+([A-Za-z0-9][\w-]*)",
    re.IGNORECASE,
)

# CALL 'program-name' or CALL "program-name"
# Dynamic CALL (CALL variable-name) is intentionally not matched.
_COBOL_CALL_RE = re.compile(
    r'\bCALL\s+["\']([A-Za-z0-9][\w-]*)["\']',
    re.IGNORECASE,
)


def _extract_cobol_imports(source: bytes, source_file: Path) -> list[ImportRef]:
    """Extract COPY and CALL statements from COBOL source via regex.

    COBOL doesn't use tree-sitter — the ProLeap bridge handles parsing.
    For import discovery, we use simple regex patterns on the raw source
    to find COPY (copybook inclusion) and CALL (subprogram invocation).
    """
    text = source.decode("utf-8", errors="replace")
    refs: list[ImportRef] = []

    # COPY statements → include kind (like #include)
    for m in _COBOL_COPY_RE.finditer(text):
        copybook_name = m.group(1)
        refs.append(
            ImportRef(
                source_file=source_file,
                module_path=copybook_name,
                kind="include",
            )
        )

    # CALL 'literal' statements → require kind (runtime linkage)
    for m in _COBOL_CALL_RE.finditer(text):
        program_name = m.group(1)
        refs.append(
            ImportRef(
                source_file=source_file,
                module_path=program_name,
                kind="require",
            )
        )

    return refs


# ── Shared helpers ───────────────────────────────────────────────


def _extract_string_content(node, source: bytes) -> str:
    """Extract the inner text of a string node (strip quotes)."""
    # Try to find a string_content / string_fragment child
    for child in node.children:
        if child.type in ("string_content", "string_fragment", "interpreted_string_literal_content"):
            return _node_text(child, source)
    # Fallback: strip quotes from the raw text
    text = _node_text(node, source)
    if len(text) >= 2 and text[0] in ('"', "'", "`") and text[-1] in ('"', "'", "`"):
        return text[1:-1]
    return text


def _find_nodes_by_type(node, node_type: str) -> list:
    """Recursively find all descendant nodes of a given type."""
    result = []
    if node.type == node_type:
        result.append(node)
    for child in node.children:
        result.extend(_find_nodes_by_type(child, node_type))
    return result


# ── Extractor registry ───────────────────────────────────────────

_EXTRACTORS: dict[Language, callable] = {
    Language.PYTHON: _extract_python_import,
    Language.JAVASCRIPT: _extract_js_import,
    Language.TYPESCRIPT: _extract_js_import,  # same AST structure
    Language.JAVA: _extract_java_import,
    Language.GO: _extract_go_import,
    Language.RUST: _extract_rust_import,
    Language.C: _extract_c_import,
    Language.CPP: _extract_c_import,  # same as C
    Language.CSHARP: _extract_csharp_import,
    Language.KOTLIN: _extract_kotlin_import,
    Language.SCALA: _extract_scala_import,
    Language.RUBY: _extract_ruby_import,
    Language.PHP: _extract_php_import,
    Language.LUA: _extract_lua_import,
    Language.PASCAL: _extract_pascal_import,
}
