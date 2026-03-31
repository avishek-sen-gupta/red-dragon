from pathlib import Path

from interpreter.project.types import ModuleUnit

from experiments.java_stdlib.stubs.java_io_print_stream import PRINT_STREAM_MODULE
from experiments.java_stdlib.stubs.java_lang_math import MATH_MODULE
from experiments.java_stdlib.stubs.java_lang_string import STRING_MODULE
from experiments.java_stdlib.stubs.java_lang_system import SYSTEM_MODULE
from experiments.java_stdlib.stubs.java_util_array_list import ARRAY_LIST_MODULE
from experiments.java_stdlib.stubs.java_util_hash_map import HASH_MAP_MODULE

STDLIB_REGISTRY: dict[Path, ModuleUnit] = {
    # Concrete classes (PrintStream must precede System — System.__init__ allocates a PrintStream)
    Path("java/lang/Math.java"): MATH_MODULE,
    Path("java/lang/String.java"): STRING_MODULE,
    Path("java/io/PrintStream.java"): PRINT_STREAM_MODULE,
    Path("java/lang/System.java"): SYSTEM_MODULE,
    Path("java/util/ArrayList.java"): ARRAY_LIST_MODULE,
    Path("java/util/HashMap.java"): HASH_MAP_MODULE,
    # Interface aliases — same ModuleUnit as concrete implementation
    Path("java/util/List.java"): ARRAY_LIST_MODULE,
    Path("java/util/Collection.java"): ARRAY_LIST_MODULE,
    Path("java/util/Map.java"): HASH_MAP_MODULE,
}
