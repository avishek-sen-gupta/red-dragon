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
