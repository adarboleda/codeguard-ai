"""Ejemplo inseguro sintético: exec sobre código construido en tiempo de ejecución (CG001)."""


def run_snippet(name: str) -> None:
    code = "print('hola ' + " + repr(name) + ")"
    exec(code)
