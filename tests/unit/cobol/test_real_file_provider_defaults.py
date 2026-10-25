from interpreter.record_io.run_inputs import RunInputs
from tests.covers import NotLanguageFeature, covers


class TestRealFileIOProviderDefaults:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_file_control_and_path_overrides_default_to_empty(self):
        inputs = RunInputs()
        assert (
            inputs.file_control,
            dict(inputs.path_overrides),
            inputs.system_input,
            dict(inputs.switches),
        ) == ((), {}, (), {})
