# pyright: standard
"""z390 stopped before execution and left no LOG; carries asmlg's exit code and the ERR text."""


class Z390AssemblyFailed(Exception):
    def __init__(self, log_name: str, exit_code: int, err: str) -> None:
        super().__init__(f"z390 left no {log_name}: asmlg exited {exit_code}\n{err}")
