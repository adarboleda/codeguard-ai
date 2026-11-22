"""Ejemplo inseguro sintético: os.system con cadena construida (CG002)."""

import os


def archive(name: str) -> None:
    os.system("tar -czf backup.tgz " + name)
