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
