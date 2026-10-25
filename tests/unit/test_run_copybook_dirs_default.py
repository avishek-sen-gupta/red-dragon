import inspect

from interpreter.record_io.io_provider import NO_IO_PROVIDER
from interpreter.run import run
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_copybook_dirs_defaults_to_empty_list():
    sig = inspect.signature(run)
    assert sig.parameters["copybook_dirs"].default == []
    assert sig.parameters["llm_client"].default is None
    assert sig.parameters["io_provider"].default is NO_IO_PROVIDER
