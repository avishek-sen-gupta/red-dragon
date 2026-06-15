from interpreter.cobol.file_enums import OpenMode, FileOrganization, AccessMode
from tests.covers import covers, NotLanguageFeature
import pytest


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_open_mode_from_string():
    assert OpenMode("INPUT") == OpenMode.INPUT
    assert OpenMode("OUTPUT") == OpenMode.OUTPUT
    assert OpenMode("I-O") == OpenMode.IO
    assert OpenMode("EXTEND") == OpenMode.EXTEND


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_file_organization_from_string():
    assert FileOrganization("SEQUENTIAL") == FileOrganization.SEQUENTIAL
    assert FileOrganization("INDEXED") == FileOrganization.INDEXED
    assert FileOrganization("RELATIVE") == FileOrganization.RELATIVE


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_access_mode_from_string():
    assert AccessMode("SEQUENTIAL") == AccessMode.SEQUENTIAL
    assert AccessMode("RANDOM") == AccessMode.RANDOM
    assert AccessMode("DYNAMIC") == AccessMode.DYNAMIC


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_invalid_open_mode_raises():
    with pytest.raises(ValueError):
        OpenMode("BOGUS")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_open_mode_is_str():
    assert OpenMode.INPUT == "INPUT"
    assert OpenMode.IO == "I-O"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_file_organization_is_str():
    assert FileOrganization.INDEXED == "INDEXED"
