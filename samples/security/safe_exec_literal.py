"""Ejemplo seguro sintético: exec sobre un literal fijo (no se marca)."""


def bootstrap() -> None:
    exec("VALUE = 42")
