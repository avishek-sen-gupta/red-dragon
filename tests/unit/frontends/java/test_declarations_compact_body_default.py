import inspect

from interpreter.frontends.context import NO_NODE
from interpreter.frontends.java.declarations import _emit_record_init
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compact_body_defaults_to_no_node_and_is_annotated():
    sig = inspect.signature(_emit_record_init)
    assert sig.parameters["compact_body"].default is NO_NODE
    assert sig.parameters["compact_body"].annotation is not inspect.Parameter.empty
