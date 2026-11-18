"""Prueba mínima para que la CI tenga algo que ejecutar desde el primer PR (CG-01)."""

import codeguard


def test_package_exposes_version() -> None:
    assert codeguard.__version__ == "0.1.0"
