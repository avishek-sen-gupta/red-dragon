"""NEXT SENTENCE and a paragraph's sentence ends survive the ASG's dict form."""

from cobol_asg.asg_types import CobolParagraph
from cobol_asg.cobol_statements import IfStatement, NextSentenceStatement
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


@covers(CobolFeature.NEXT_SENTENCE)
def test_next_sentence_and_sentence_ends_read_and_write_back() -> None:
    data = {
        "name": "P1",
        "statements": [
            {"type": "IF", "children": [{"type": "NEXT_SENTENCE"}]},
            {"type": "CONTINUE"},
        ],
        "sentence_ends": [1],
    }

    paragraph = CobolParagraph.from_dict(data)

    first = paragraph.statements[0]
    assert isinstance(first, IfStatement)
    assert first.children == [NextSentenceStatement()]
    assert paragraph.sentence_ends == [1]
    assert CobolParagraph.from_dict(paragraph.to_dict()) == paragraph
    assert CobolParagraph.from_dict({"name": "P2"}).to_dict() == {"name": "P2"}
