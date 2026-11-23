"""Ejemplo inseguro sintético: eval sobre entrada no confiable (CG001)."""


def calculate(user_expression: str) -> float:
    return eval(user_expression)
