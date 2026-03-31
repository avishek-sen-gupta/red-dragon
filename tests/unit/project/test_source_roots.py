"""Tests for source root discovery."""

from pathlib import Path

import pytest

from interpreter.project.source_roots import (
    ExplicitSourceRootDiscovery,
    MavenSourceRootDiscovery,
)
from interpreter.project.compiler import compile_directory
from interpreter.constants import Language


class TestExplicitSourceRootDiscovery:
    def test_returns_provided_roots(self):
        roots = [Path("/a/src/main/java"), Path("/b/src/main/java")]
        discovery = ExplicitSourceRootDiscovery(roots)
        assert discovery.discover(Path("/project")) == roots

    def test_empty_roots(self):
        discovery = ExplicitSourceRootDiscovery([])
        assert discovery.discover(Path("/project")) == []


class TestMavenSourceRootDiscovery:
    def test_discovers_single_module(self, tmp_path):
        (tmp_path / "src" / "main" / "java" / "com" / "example").mkdir(parents=True)
        (
            tmp_path / "src" / "main" / "java" / "com" / "example" / "App.java"
        ).write_text("class App {}")

        discovery = MavenSourceRootDiscovery()
        roots = discovery.discover(tmp_path)
        assert roots == [tmp_path / "src" / "main" / "java"]

    def test_discovers_sibling_modules(self, tmp_path):
        (tmp_path / "module-a" / "src" / "main" / "java").mkdir(parents=True)
        (tmp_path / "module-a" / "src" / "main" / "java" / "A.java").write_text(
            "class A {}"
        )
        (tmp_path / "module-b" / "src" / "main" / "java").mkdir(parents=True)
        (tmp_path / "module-b" / "src" / "main" / "java" / "B.java").write_text(
            "class B {}"
        )

        discovery = MavenSourceRootDiscovery()
        roots = sorted(discovery.discover(tmp_path))
        assert len(roots) == 2
        assert tmp_path / "module-a" / "src" / "main" / "java" in roots
        assert tmp_path / "module-b" / "src" / "main" / "java" in roots

    def test_discovers_nested_modules(self, tmp_path):
        (tmp_path / "parent" / "child" / "src" / "main" / "java").mkdir(parents=True)
        (tmp_path / "parent" / "child" / "src" / "main" / "java" / "C.java").write_text(
            "class C {}"
        )

        discovery = MavenSourceRootDiscovery()
        roots = discovery.discover(tmp_path)
        assert tmp_path / "parent" / "child" / "src" / "main" / "java" in roots

    def test_no_maven_structure_returns_empty(self, tmp_path):
        (tmp_path / "code").mkdir()
        (tmp_path / "code" / "App.java").write_text("class App {}")

        discovery = MavenSourceRootDiscovery()
        roots = discovery.discover(tmp_path)
        assert roots == []


class TestCompileDirectoryMultiRoot:
    def test_compile_directory_discovers_maven_roots(self, tmp_path):
        """compile_directory should discover sibling Maven modules and resolve
        cross-module imports."""
        # module-a/src/main/java/com/math/Adder.java
        math_pkg = tmp_path / "module-a" / "src" / "main" / "java" / "com" / "math"
        math_pkg.mkdir(parents=True)
        (math_pkg / "Adder.java").write_text("""
package com.math;
public class Adder {
    int base;
    Adder(int b) { this.base = b; }
    public int add(int x) { return this.base + x; }
}
""")

        # module-b/src/main/java/com/app/Main.java
        app_pkg = tmp_path / "module-b" / "src" / "main" / "java" / "com" / "app"
        app_pkg.mkdir(parents=True)
        (app_pkg / "Main.java").write_text("""
package com.app;
import com.math.Adder;
public class Main {
    public static void main(String[] args) {
        Adder a = new Adder(10);
        int result = a.add(5);
    }
}
""")

        linked = compile_directory(tmp_path, Language.JAVA)

        # Both modules should be linked
        assert len(linked.merged_ir) > 0
        # Adder's class label should be in the merged IR — this only appears if
        # Adder.java from module-a was actually discovered and compiled.
        from interpreter.instructions import Label_

        labels = [str(inst) for inst in linked.merged_ir if isinstance(inst, Label_)]
        assert any(
            "class_Adder" in label for label in labels
        ), f"Adder class label not found in linked IR labels: {labels}"
