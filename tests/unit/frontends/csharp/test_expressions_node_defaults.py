import inspect

from interpreter.frontends.context import NO_NODE
from interpreter.frontends.csharp.expressions import emit_byref_load, emit_byref_store
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_node_defaults_to_no_node_and_is_annotated():
    for fn in (emit_byref_load, emit_byref_store):
        sig = inspect.signature(fn)
        assert sig.parameters["node"].default is NO_NODE
        assert sig.parameters["node"].annotation is not inspect.Parameter.empty
