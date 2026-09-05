import subprocess
import sys

from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_importing_cobol_memory_does_not_load_the_interpreter():
    """The reason cobol_memory is a sibling of interpreter, not a subpackage.

    Importing interpreter.anything runs interpreter/__init__.py, which loads the
    VM. A static-only consumer must be able to reach the byte-extent algebra
    without paying for that.
    """
    code = (
        "import sys;"
        "import cobol_memory.field_extent;"
        "print(any(m == 'interpreter' or m.startswith('interpreter.')"
        " for m in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_field_extent_surface_is_importable_from_the_new_home():
    from cobol_memory.field_extent import FieldExtent, Precision
    from cobol_memory.region_id import RegionId

    extent = FieldExtent(
        region=RegionId.WORKING_STORAGE,
        start=10,
        length=5,
        precision=Precision.EXACT,
        field_name="FLD-A",
    )
    assert extent.end == 15
    assert extent.is_present() is True
