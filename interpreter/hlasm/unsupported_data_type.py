# pyright: standard
"""A DC type the lowering cannot encode yet, naming the issue that tracks it."""


class UnsupportedDataType(Exception):
    def __init__(self, type_code: str, issue: str) -> None:
        super().__init__(f"DC type {type_code} is not supported yet — {issue}")
