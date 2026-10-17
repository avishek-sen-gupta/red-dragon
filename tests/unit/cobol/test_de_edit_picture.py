"""Tests for de-editing: the numeric value recovered from a numeric-edited image."""

from cobol_asg.edit_picture import de_edit
from cobol_numeric.number import from_literal
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


@covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
def test_de_edit_recovers_value_and_sign_from_the_edited_image():
    cases = [
        (" $123.45CR", "$(4)9.99CR", "$", "-123.45"),
        (" $123.45  ", "$(4)9.99CR", "$", "123.45"),
        ("   42.00DB", "Z(4)9.99DB", "$", "-42.00"),
        ("-42 .98 76/00", "--9B.99B99/99", "$", "-42.987600"),
        (" -123.45", "-(4)9.99", "$", "-123.45"),
        ("+0012", "+9(4)", "$", "12"),
        ("-0012", "+9(4)", "$", "-12"),
        ("0012-", "9(4)-", "$", "-12"),
        ("*1,234.50", "**,***.99", "$", "1234.50"),
        ("      ", "ZZZ.ZZ", "$", "0"),
        ("1234", "ZZ9V9", "$", "123.4"),
        ("120", "ZZ9PP", "$", "12000"),
        ("12", "PPZ9", "$", "0.0012"),
        ("£12.50", "£££.99", "£", "12.50"),
    ]
    results = [
        (image, pic, de_edit(image, pic, currency)) for image, pic, currency, _ in cases
    ]
    assert results == [
        (image, pic, from_literal(expected)) for image, pic, _, expected in cases
    ]
