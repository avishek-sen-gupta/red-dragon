from interpreter.frontends._base import NO_NODE
from tests.covers import NotLanguageFeature, covers


class TestNONode:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_no_node_is_a_stable_singleton(self):
        from interpreter.frontends._base import NO_NODE as no_node_again

        assert NO_NODE is no_node_again
