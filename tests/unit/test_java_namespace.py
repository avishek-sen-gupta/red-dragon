# tests/unit/test_java_namespace.py
"""Tests for Java namespace resolution: pre-scan, tree builder, resolver."""

from __future__ import annotations

from interpreter.frontends.java.namespace import (
    JavaPreScanResult,
    java_pre_scan,
)


class TestJavaPreScan:
    def test_single_class_with_package(self):
        source = b"""
package com.example;
public class Helper { }
"""
        result = java_pre_scan(source)
        assert result.package == "com.example"
        assert result.class_names == ["Helper"]

    def test_multiple_classes(self):
        source = b"""
package com.test;
class Foo { }
interface Bar { }
enum Baz { }
"""
        result = java_pre_scan(source)
        assert result.package == "com.test"
        assert sorted(result.class_names) == ["Bar", "Baz", "Foo"]

    def test_no_package(self):
        source = b"class Main { }"
        result = java_pre_scan(source)
        assert result.package is None
        assert result.class_names == ["Main"]

    def test_imports_extracted(self):
        source = b"""
package com.test;
import java.util.Arrays;
import java.io.*;
class Main { }
"""
        result = java_pre_scan(source)
        assert len(result.imports) == 2
        assert any(
            imp.module_path == "java.util" and "Arrays" in imp.names
            for imp in result.imports
        )

    def test_record_declaration(self):
        source = b"""
package com.dto;
record Point(int x, int y) { }
"""
        result = java_pre_scan(source)
        assert result.class_names == ["Point"]


from pathlib import Path

from interpreter.frontends.java.namespace import build_java_namespace_tree
from interpreter.namespace import NamespaceType
from interpreter.refs.class_ref import NO_CLASS_REF, ClassRef
from interpreter.class_name import ClassName
from interpreter.ir import CodeLabel
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.constants import Language


def _make_stub_module(class_name: str, label_str: str) -> ModuleUnit:
    """Minimal stub ModuleUnit for testing."""
    from interpreter.instructions import Label_, Branch, Const, DeclVar
    from interpreter.register import Register
    from interpreter.var_name import VarName

    cls_label = f"class_{class_name}_0"
    end_label = f"end_class_{class_name}_1"
    return ModuleUnit(
        path=Path(f"stub/{class_name}.java"),
        language=Language.JAVA,
        ir=(
            Label_(label=CodeLabel(f"entry_{class_name}")),
            Branch(label=CodeLabel(end_label)),
            Label_(label=CodeLabel(cls_label)),
            Label_(label=CodeLabel(end_label)),
            Const(result_reg=Register("%0"), value=cls_label),
            DeclVar(name=VarName(class_name), value_reg=Register("%0")),
        ),
        exports=ExportTable(
            classes={ClassName(class_name): CodeLabel(cls_label)},
        ),
        imports=(),
    )


class TestBuildJavaNamespaceTree:
    def test_stub_registry_populates_tree(self):
        stub = _make_stub_module("Arrays", "class_Arrays_0")
        registry = {Path("java/util/Arrays.java"): stub}

        tree = build_java_namespace_tree(
            scan_results={},
            stdlib_registry=registry,
        )

        resolved, remaining, qualified = tree.resolve(["java", "util", "Arrays"])
        assert resolved is not None
        assert resolved.short_name == "Arrays"
        assert resolved.module is stub
        assert remaining == []

    def test_project_classes_populate_tree(self):
        scan_results = {
            Path("/proj/Helper.java"): JavaPreScanResult(
                package="com.test", class_names=["Helper"]
            ),
        }

        tree = build_java_namespace_tree(
            scan_results=scan_results,
            stdlib_registry={},
        )

        resolved, _, _ = tree.resolve(["com", "test", "Helper"])
        assert resolved is not None
        assert resolved.short_name == "Helper"
        assert resolved.class_ref is NO_CLASS_REF
        assert resolved.module is None

    def test_project_class_overrides_stub(self):
        stub = _make_stub_module("Arrays", "class_Arrays_0")
        registry = {Path("java/util/Arrays.java"): stub}
        scan_results = {
            Path("/proj/Arrays.java"): JavaPreScanResult(
                package="java.util", class_names=["Arrays"]
            ),
        }

        tree = build_java_namespace_tree(
            scan_results=scan_results,
            stdlib_registry=registry,
        )

        resolved, _, _ = tree.resolve(["java", "util", "Arrays"])
        assert resolved is not None
        assert resolved.module is None  # project override, not stub

    def test_no_package_class_not_registered(self):
        """Classes without a package are not registered in namespace tree."""
        scan_results = {
            Path("/proj/Main.java"): JavaPreScanResult(
                package=None, class_names=["Main"]
            ),
        }

        tree = build_java_namespace_tree(
            scan_results=scan_results,
            stdlib_registry={},
        )

        resolved, _, _ = tree.resolve(["Main"])
        assert resolved is None


from interpreter.frontends.java.namespace import (
    JavaNamespaceResolver,
    _collect_field_access_chain,
)
from interpreter.namespace import NO_CHAIN, NO_RESOLUTION, NamespaceTree
from interpreter.frontends.context import TreeSitterEmitContext, GrammarConstants
from interpreter.frontends._base import NullFrontendObserver
from interpreter.ir import Opcode
from interpreter.parser import TreeSitterParserFactory

_PARSER = TreeSitterParserFactory()


def _parse_expr_node(java_expr: str):
    """Parse a Java expression and return the root expression node."""
    source = f"class X {{ void m() {{ {java_expr}; }} }}".encode()
    parser = _PARSER.get_parser("java")
    tree = parser.parse(source)
    # Navigate: program > class_declaration > class_body > method_declaration
    #   > method body (block) > expression_statement > expression
    cls = tree.root_node.children[0]
    body = cls.child_by_field_name("body")
    method = [c for c in body.children if c.type == "method_declaration"][0]
    block = method.child_by_field_name("body")
    expr_stmt = [c for c in block.children if c.type == "expression_statement"][0]
    return expr_stmt.children[0], source


def _make_java_ctx(source: bytes, resolver=None) -> TreeSitterEmitContext:
    from interpreter.frontends.java.frontend import JavaFrontend

    frontend = JavaFrontend(_PARSER, "java")
    constants = frontend._build_constants()
    ctx = TreeSitterEmitContext(
        source=source,
        language=Language.JAVA,
        observer=NullFrontendObserver(),
        constants=constants,
        **({"namespace_resolver": resolver} if resolver else {}),
    )
    return ctx


class TestCollectFieldAccessChain:
    def test_simple_chain(self):
        """java.util.Arrays → ['java', 'util', 'Arrays']."""
        node, source = _parse_expr_node("java.util.Arrays")
        ctx = _make_java_ctx(source)
        chain = _collect_field_access_chain(ctx, node)
        assert chain == ["java", "util", "Arrays"]

    def test_deeper_chain(self):
        """java.util.Arrays.fill → ['java', 'util', 'Arrays', 'fill']."""
        node, source = _parse_expr_node("java.util.Arrays.fill")
        ctx = _make_java_ctx(source)
        chain = _collect_field_access_chain(ctx, node)
        assert chain == ["java", "util", "Arrays", "fill"]

    def test_non_identifier_root_returns_no_chain(self):
        """this.field → NO_CHAIN (root is 'this', not identifier)."""
        node, source = _parse_expr_node("this.field")
        ctx = _make_java_ctx(source)
        chain = _collect_field_access_chain(ctx, node)
        assert chain is NO_CHAIN


class TestJavaNamespaceResolver:
    def test_resolve_qualified_type(self):
        """java.util.Arrays → LoadVar('Arrays')."""
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))
        resolver = JavaNamespaceResolver(tree)

        node, source = _parse_expr_node("java.util.Arrays")
        ctx = _make_java_ctx(source, resolver)

        result = resolver.try_resolve_field_access(ctx, node)
        assert result is not NO_RESOLUTION
        load_vars = [i for i in ctx.instructions if i.opcode == Opcode.LOAD_VAR]
        assert len(load_vars) == 1
        assert load_vars[0].name.value == "Arrays"

    def test_resolve_with_remaining_field(self):
        """java.sql.Types.VARCHAR → LoadVar('Types') + LoadField('VARCHAR')."""
        tree = NamespaceTree()
        tree.register_type("java.sql.Types", NamespaceType(short_name="Types"))
        resolver = JavaNamespaceResolver(tree)

        node, source = _parse_expr_node("java.sql.Types.VARCHAR")
        ctx = _make_java_ctx(source, resolver)

        result = resolver.try_resolve_field_access(ctx, node)
        assert result is not NO_RESOLUTION
        load_vars = [i for i in ctx.instructions if i.opcode == Opcode.LOAD_VAR]
        load_fields = [i for i in ctx.instructions if i.opcode == Opcode.LOAD_FIELD]
        assert len(load_vars) == 1
        assert load_vars[0].name.value == "Types"
        assert len(load_fields) == 1
        assert load_fields[0].field_name.value == "VARCHAR"

    def test_declared_local_skips_resolution(self):
        """If 'java' is a local variable, skip namespace resolution."""
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))
        resolver = JavaNamespaceResolver(tree)

        node, source = _parse_expr_node("java.util.Arrays")
        ctx = _make_java_ctx(source, resolver)
        ctx._method_declared_names.add("java")

        result = resolver.try_resolve_field_access(ctx, node)
        assert result is NO_RESOLUTION

    def test_no_tree_match_falls_through(self):
        """com.unknown.Foo → NO_RESOLUTION."""
        tree = NamespaceTree()
        resolver = JavaNamespaceResolver(tree)

        node, source = _parse_expr_node("com.unknown.Foo")
        ctx = _make_java_ctx(source, resolver)

        result = resolver.try_resolve_field_access(ctx, node)
        assert result is NO_RESOLUTION


class TestFieldAccessWithResolver:
    def test_qualified_reference_emits_load_var(self):
        """Full pipeline: java.util.Arrays resolves to LoadVar('Arrays')."""
        from interpreter.frontends.java.frontend import JavaFrontend

        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))
        resolver = JavaNamespaceResolver(tree)

        source = b"class X { void m() { java.util.Arrays.fill(arr, 0); } }"
        frontend = JavaFrontend(_PARSER, "java")
        ir = frontend.lower(source, namespace_resolver=resolver)

        # Should have LoadVar("Arrays"), NOT LoadVar("java")
        load_vars = [i for i in ir if i.opcode == Opcode.LOAD_VAR]
        load_var_names = [i.name.value for i in load_vars]
        assert (
            "Arrays" in load_var_names
        ), f"Expected LoadVar('Arrays'), got: {load_var_names}"
        assert (
            "java" not in load_var_names
        ), f"LoadVar('java') should not appear: {load_var_names}"


class TestCompileDirectoryNamespaceResolution:
    def test_compile_directory_uses_namespace_tree(self, tmp_path):
        """compile_directory() should pre-scan, build tree, and resolve namespaces."""
        from interpreter.project.compiler import compile_directory
        from interpreter.project.types import LinkedProgram

        # Two-file project: Helper in com.test package, Main uses it qualified
        helper_src = """\
package com.test;
public class Helper {
    public static int add(int a, int b) { return a + b; }
}
"""
        main_src = """\
package com.app;
import com.test.Helper;
public class Main {
    public static void main() {
        int result = com.test.Helper.add(1, 2);
    }
}
"""
        # Maven-style layout
        helper_dir = tmp_path / "src" / "main" / "java" / "com" / "test"
        helper_dir.mkdir(parents=True)
        (helper_dir / "Helper.java").write_text(helper_src)

        main_dir = tmp_path / "src" / "main" / "java" / "com" / "app"
        main_dir.mkdir(parents=True)
        (main_dir / "Main.java").write_text(main_src)

        linked = compile_directory(tmp_path, Language.JAVA)
        assert isinstance(linked, LinkedProgram)

        # Verify: LoadVar("Helper") appears, LoadVar("com") does NOT
        load_vars = [i for i in linked.merged_ir if i.opcode == Opcode.LOAD_VAR]
        load_var_names = [i.name.value for i in load_vars]
        assert (
            "Helper" in load_var_names
        ), f"Expected LoadVar('Helper') from namespace resolution, got: {load_var_names}"
        assert (
            "com" not in load_var_names
        ), f"LoadVar('com') should not appear after namespace resolution: {load_var_names}"
