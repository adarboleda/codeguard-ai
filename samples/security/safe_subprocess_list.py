"""Ejemplo seguro sintético: subprocess con lista de argumentos, sin shell (no se marca)."""

import subprocess


def list_directory(path: str) -> None:
    subprocess.run(["ls", "-l", path], check=True)
