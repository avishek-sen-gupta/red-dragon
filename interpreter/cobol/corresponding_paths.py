"""The relative paths of the item pairs a CORRESPONDING phrase selects between two groups."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from interpreter.cobol.data_layout import DataLayout, FieldLayout

type DataItem = FieldLayout | DataLayout
type PairRule = Callable[[DataItem, DataItem], bool]


def corresponding_paths(
    source: DataLayout, target: DataLayout, pairs_with: PairRule
) -> tuple[tuple[str, ...], ...]:
    counterparts = {name.upper(): item for name, item in _children(target)}
    return tuple(
        path
        for name, item in _children(source)
        if _pairable(name, item, counterparts)
        for path in _paths_below(name, item, counterparts[name.upper()], pairs_with)
    )


def pairs_for_move(source: DataItem, target: DataItem) -> bool:
    return True


def pairs_for_arithmetic(source: DataItem, target: DataItem) -> bool:
    return _is_numeric(source) and _is_numeric(target)


def _children(layout: DataLayout) -> tuple[tuple[str, DataItem], ...]:
    return (*layout.fields.items(), *layout.groups.items())


def _pairable(name: str, item: DataItem, counterparts: Mapping[str, DataItem]) -> bool:
    return (
        name.upper() in counterparts
        and not _excluded(item)
        and not _excluded(counterparts[name.upper()])
    )


def _excluded(item: DataItem) -> bool:
    return item.occurs_count > 0 or item.redefines != ""


def _paths_below(
    name: str, source: DataItem, target: DataItem, pairs_with: PairRule
) -> tuple[tuple[str, ...], ...]:
    if isinstance(source, DataLayout) and isinstance(target, DataLayout):
        return tuple(
            (name, *path) for path in corresponding_paths(source, target, pairs_with)
        )
    return ((name,),) if pairs_with(source, target) else ()


def _is_numeric(item: DataItem) -> bool:
    return isinstance(item, FieldLayout) and item.type_descriptor.is_numeric
