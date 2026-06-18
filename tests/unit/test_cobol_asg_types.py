from interpreter.cobol.asg_types import CobolSection, UseClause
from tests.covers import NotLanguageFeature, covers


class TestUseClauseParsing:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_named_file_use_clause(self):
        sec = CobolSection.from_dict(
            {
                "name": "RL-FS2-01",
                "use": {"global": False, "target": "FILE", "files": ["RL-FS2"]},
            }
        )
        assert sec.use == UseClause(is_global=False, target="FILE", files=("RL-FS2",))

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_no_use_clause_is_none(self):
        assert CobolSection.from_dict({"name": "X"}).use is None

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_open_mode_use_clause(self):
        sec = CobolSection.from_dict(
            {"name": "S", "use": {"global": True, "target": "OUTPUT"}}
        )
        assert sec.use == UseClause(is_global=True, target="OUTPUT", files=())
