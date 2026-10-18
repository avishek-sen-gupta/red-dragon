# pyright: standard
"""The bridge's compilation unit read as a tree of programs (red-dragon-ljku.1)."""

from collections.abc import Mapping

from cobol_asg.compilation_unit import CobolCompilationUnit, programs_in_preorder
from cobol_asg.program_attribute import ProgramAttribute
from interpreter.cobol.features import CobolFeature
from tests.covers import covers

_WRITTEN = {
    "programs": [
        {
            "program_id": "OUTER",
            "attribute": "",
            "paragraphs": [{"name": "OUTER-PARA", "statements": []}],
            "programs": [
                {
                    "program_id": "MIDDLE",
                    "attribute": "COMMON",
                    "programs": [
                        {"program_id": "INNER", "attribute": "INITIAL", "programs": []}
                    ],
                },
                {"program_id": "SIBLING", "attribute": "", "programs": []},
            ],
        },
        {"program_id": "BATCHED", "attribute": "", "programs": []},
    ]
}


def _shape(asg):
    return (asg.program_id, asg.attribute, tuple(_shape(p) for p in asg.programs))


@covers(CobolFeature.NESTED_PROGRAMS)
@covers(CobolFeature.BATCHED_PROGRAMS)
def test_a_compilation_unit_reads_as_its_tree_of_programs_each_preprocessed_alone():
    def preprocessor(data: Mapping[str, str]) -> dict[str, str]:
        return {**data, "program_id": f"{data['program_id']}:{','.join(sorted(data))}"}

    unit = CobolCompilationUnit.from_dict(_WRITTEN, preprocessor=preprocessor)

    assert (
        tuple(_shape(p) for p in unit.programs),
        [p.name for p in unit.first_program.paragraphs],
    ) == (
        (
            (
                "OUTER:attribute,paragraphs,program_id",
                ProgramAttribute.NONE,
                (
                    (
                        "MIDDLE:attribute,program_id",
                        ProgramAttribute.COMMON,
                        (("INNER:attribute,program_id", ProgramAttribute.INITIAL, ()),),
                    ),
                    ("SIBLING:attribute,program_id", ProgramAttribute.NONE, ()),
                ),
            ),
            ("BATCHED:attribute,program_id", ProgramAttribute.NONE, ()),
        ),
        ["OUTER-PARA"],
    )


@covers(CobolFeature.NESTED_PROGRAMS)
@covers(CobolFeature.BATCHED_PROGRAMS)
def test_programs_in_preorder_yields_each_program_alone_with_its_enclosing_programs():
    assert [
        (
            p["program_id"],
            sorted(p),
            [(e["program_id"], sorted(e)) for e in p.get("enclosing", [])],
        )
        for p in programs_in_preorder(_WRITTEN)
    ] == [
        ("OUTER", ["attribute", "paragraphs", "program_id"], []),
        (
            "MIDDLE",
            ["attribute", "enclosing", "program_id"],
            [("OUTER", ["attribute", "paragraphs", "program_id"])],
        ),
        (
            "INNER",
            ["attribute", "enclosing", "program_id"],
            [
                ("MIDDLE", ["attribute", "program_id"]),
                ("OUTER", ["attribute", "paragraphs", "program_id"]),
            ],
        ),
        (
            "SIBLING",
            ["attribute", "enclosing", "program_id"],
            [("OUTER", ["attribute", "paragraphs", "program_id"])],
        ),
        ("BATCHED", ["attribute", "program_id"], []),
    ]
