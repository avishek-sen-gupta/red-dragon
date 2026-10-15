# pyright: standard
"""A run asked to enter a program the linked image does not hold."""


class ProgramNotInImage(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"program {name} is not in the image")
