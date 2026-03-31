from pathlib import Path
from experiments.java_stdlib.registry import STDLIB_REGISTRY


class TestRegistry:
    def test_array_list_present(self):
        assert Path("java/util/ArrayList.java") in STDLIB_REGISTRY

    def test_hash_map_present(self):
        assert Path("java/util/HashMap.java") in STDLIB_REGISTRY

    def test_math_present(self):
        assert Path("java/lang/Math.java") in STDLIB_REGISTRY

    def test_list_interface_aliases_array_list(self):
        assert (
            STDLIB_REGISTRY[Path("java/util/List.java")]
            is STDLIB_REGISTRY[Path("java/util/ArrayList.java")]
        )

    def test_map_interface_aliases_hash_map(self):
        assert (
            STDLIB_REGISTRY[Path("java/util/Map.java")]
            is STDLIB_REGISTRY[Path("java/util/HashMap.java")]
        )

    def test_collection_interface_aliases_array_list(self):
        assert (
            STDLIB_REGISTRY[Path("java/util/Collection.java")]
            is STDLIB_REGISTRY[Path("java/util/ArrayList.java")]
        )
