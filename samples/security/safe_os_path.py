"""Ejemplo seguro sintético: operaciones de rutas sin ejecutar procesos (no se marca)."""

import os


def backup_name(name: str) -> str:
    return os.path.join("backups", os.path.basename(name) + ".tgz")
