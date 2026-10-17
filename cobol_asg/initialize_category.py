"""The data categories an INITIALIZE REPLACING phrase can name."""

from enum import StrEnum


class InitializeCategory(StrEnum):
    """One REPLACING category, spelled as the bridge sends it."""

    ALPHABETIC = "ALPHABETIC"
    ALPHANUMERIC = "ALPHANUMERIC"
    NUMERIC = "NUMERIC"
    ALPHANUMERIC_EDITED = "ALPHANUMERIC_EDITED"
    NUMERIC_EDITED = "NUMERIC_EDITED"
