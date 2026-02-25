"""Named constants — eliminates magic strings across the codebase."""

from __future__ import annotations

PARAM_PREFIX = "param:"

FUNC_REF_PATTERN = r"<function:(\w+)@(\w+)>"
CLASS_REF_PATTERN = r"<class:(\w+)@(\w+)>"

FUNC_REF_TEMPLATE = "<function:{name}@{label}>"
CLASS_REF_TEMPLATE = "<class:{name}@{label}>"

OBJ_ADDR_PREFIX = "obj_"
ARR_ADDR_PREFIX = "arr_"

FUNC_LABEL_PREFIX = "func_"
CLASS_LABEL_PREFIX = "class_"
END_CLASS_LABEL_PREFIX = "end_class_"

MAIN_FRAME_NAME = "<main>"
CFG_ENTRY_LABEL = "entry"

FRONTEND_DETERMINISTIC = "deterministic"
FRONTEND_LLM = "llm"
