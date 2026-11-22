"""Ejemplo seguro sintético: eval solo sobre un literal fijo (no se marca)."""


def constant_value() -> int:
    return eval("1 + 1")
