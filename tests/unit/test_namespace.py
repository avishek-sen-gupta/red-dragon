# tests/unit/test_namespace.py
"""Tests for namespace tree data structures and resolution algorithm."""

from __future__ import annotations

from interpreter.namespace import (
    NamespaceNode,
    NamespaceTree,
    NamespaceType,
)
from interpreter.refs.class_ref import NO_CLASS_REF


class TestNamespaceTreeResolve:
    def test_resolve_type_at_leaf(self):
        """java.util.Arrays → (NamespaceType('Arrays'), [], 'java.util.Arrays')."""
        tree = NamespaceTree()
        ns_type = NamespaceType(short_name="Arrays")
        tree.register_type("java.util.Arrays", ns_type)

        resolved, remaining, qualified = tree.resolve(["java", "util", "Arrays"])
        assert resolved is ns_type
        assert remaining == []
        assert qualified == "java.util.Arrays"

    def test_resolve_type_with_remaining_chain(self):
        """java.util.Arrays.fill → (NamespaceType, ['fill'], ...)."""
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))

        resolved, remaining, qualified = tree.resolve(
            ["java", "util", "Arrays", "fill"]
        )
        assert resolved is not None
        assert resolved.short_name == "Arrays"
        assert remaining == ["fill"]
        assert qualified == "java.util.Arrays"

    def test_resolve_no_match(self):
        """com.unknown.Foo → (None, original_chain, '')."""
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))

        resolved, remaining, qualified = tree.resolve(["com", "unknown", "Foo"])
        assert resolved is None
        assert remaining == ["com", "unknown", "Foo"]
        assert qualified == ""

    def test_resolve_partial_namespace_no_type(self):
        """java.util → no type at 'util', returns None."""
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))

        resolved, remaining, qualified = tree.resolve(["java", "util"])
        assert resolved is None

    def test_register_multiple_types_same_namespace(self):
        """java.util has both Arrays and ArrayList."""
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))
        tree.register_type("java.util.ArrayList", NamespaceType(short_name="ArrayList"))

        r1, _, _ = tree.resolve(["java", "util", "Arrays"])
        r2, _, _ = tree.resolve(["java", "util", "ArrayList"])
        assert r1 is not None and r1.short_name == "Arrays"
        assert r2 is not None and r2.short_name == "ArrayList"

    def test_resolve_single_segment_type(self):
        """String at root → (NamespaceType, [], 'String')."""
        tree = NamespaceTree()
        tree.register_type("String", NamespaceType(short_name="String"))

        resolved, remaining, qualified = tree.resolve(["String"])
        assert resolved is not None
        assert resolved.short_name == "String"
        assert remaining == []

    def test_empty_chain_returns_none(self):
        tree = NamespaceTree()
        resolved, remaining, qualified = tree.resolve([])
        assert resolved is None


class TestNamespaceResolverBase:
    def test_base_resolver_returns_no_resolution(self):
        from interpreter.namespace import NamespaceResolver, NO_RESOLUTION

        resolver = NamespaceResolver()
        result = resolver.try_resolve_field_access(None, None)
        assert result is NO_RESOLUTION

    def test_no_resolution_is_falsy(self):
        from interpreter.namespace import NO_RESOLUTION

        assert not NO_RESOLUTION

    def test_no_chain_is_falsy(self):
        from interpreter.namespace import NO_CHAIN

        assert not NO_CHAIN

    def test_register_is_not_no_resolution(self):
        from interpreter.namespace import NO_RESOLUTION
        from interpreter.register import Register

        reg = Register("%0")
        assert reg is not NO_RESOLUTION


class TestNamespaceTreeRegister:
    def test_register_creates_intermediate_nodes(self):
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))

        assert "java" in tree.root.children
        assert "util" in tree.root.children["java"].children
        assert "Arrays" in tree.root.children["java"].children["util"].types

    def test_register_preserves_class_ref(self):
        from interpreter.refs.class_ref import ClassRef
        from interpreter.class_name import ClassName
        from interpreter.ir import CodeLabel

        ref = ClassRef(
            name=ClassName("Arrays"),
            label=CodeLabel("class_Arrays_0"),
            parents=(),
        )
        ns_type = NamespaceType(short_name="Arrays", class_ref=ref)
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", ns_type)

        resolved, _, _ = tree.resolve(["java", "util", "Arrays"])
        assert resolved is not None
        assert resolved.class_ref is ref


class TestContextNamespaceResolver:
    def test_default_resolver_is_base(self):
        from interpreter.frontends.context import (
            TreeSitterEmitContext,
            GrammarConstants,
        )
        from interpreter.constants import Language
        from interpreter.frontends._base import NullFrontendObserver
        from interpreter.namespace import NamespaceResolver, NO_RESOLUTION

        ctx = TreeSitterEmitContext(
            source=b"",
            language=Language.JAVA,
            observer=NullFrontendObserver(),
            constants=GrammarConstants(),
        )
        assert isinstance(ctx.namespace_resolver, NamespaceResolver)
        assert (
            ctx.namespace_resolver.try_resolve_field_access(ctx, None) is NO_RESOLUTION
        )


class TestCompileModuleNamespaceResolver:
    def test_compile_module_accepts_namespace_resolver(self):
        """compile_module() should accept an optional namespace_resolver param."""
        from interpreter.project.compiler import compile_module
        from interpreter.constants import Language
        from interpreter.namespace import NamespaceResolver
        from pathlib import Path
        import tempfile

        java_src = "class Foo { }"
        with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False) as f:
            f.write(java_src)
            f.flush()
            path = Path(f.name)

        resolver = NamespaceResolver()
        module = compile_module(path, Language.JAVA, namespace_resolver=resolver)
        assert module is not None
        path.unlink()
