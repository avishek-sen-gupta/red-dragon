"""Tests for source root discovery."""

from pathlib import Path

import pytest

from interpreter.project.source_roots import (
    ExplicitSourceRootDiscovery,
    MavenSourceRootDiscovery,
)


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
