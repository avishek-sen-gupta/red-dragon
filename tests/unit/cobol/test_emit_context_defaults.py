import inspect

from interpreter.cobol.emit_context import EmitContext
from interpreter.frontend_observer import NullFrontendObserver
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_observer_and_asg_default_away_from_none():
    sig = inspect.signature(EmitContext.__init__)
    assert isinstance(sig.parameters["observer"].default, NullFrontendObserver)
    assert sig.parameters["asg"].default is not None
