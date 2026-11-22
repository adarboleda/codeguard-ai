"""Ejemplo inseguro sintético: subprocess con shell=True (CG002)."""

import subprocess


def list_directory(path: str) -> None:
    subprocess.run("ls -l " + path, shell=True, check=True)
