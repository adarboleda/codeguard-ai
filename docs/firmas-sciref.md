# Firmas y contratos acordados — Paquete `sciref` (CG-05)

Documento de referencia para el **Issue #6 (`CG-05`)** y para el cálculo independiente del oráculo en `specs/contracts.yaml` (`CG-04`). Define únicamente las firmas, tipos, contratos, excepciones y casos frontera de las 6 funciones de referencia, **sin revelar ni incluir código de implementación** (evita el oráculo circular).

## Convenciones generales

- **Módulos canónicos:** `sciref.numeric`, `sciref.signals` y `sciref.validation` (las 6 funciones se re-exportan además desde `sciref.__init__`).
- **Secuencias de entrada:** tipadas como `Sequence[float]` (`from collections.abc import Sequence`); aceptan `list` o `tuple` de `int` o `float` y **nunca mutan** la secuencia de entrada.
- **Paso de argumentos:** todos los parámetros son posicionales o por nombre (`POSITIONAL_OR_KEYWORD`), compatibles con `inspect.signature().bind(...)`.
- **Retornos numéricos:** los valores flotantes retornan como `float` (o `list[float]`) y se comparan en pruebas con `pytest.approx(rel=1e-9)`.

## Resumen rápido de firmas

```python
from collections.abc import Sequence


# sciref.numeric
def weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float: ...
def clamp(x: float, lo: float, hi: float) -> float: ...
def normalize_minmax(values: Sequence[float]) -> list[float]: ...


# sciref.signals
def moving_average(values: Sequence[float], window: int) -> list[float]: ...
def threshold_crossings(values: Sequence[float], threshold: float) -> list[int]: ...


# sciref.validation
def validate_range(value: float, lo: float, hi: float, inclusive: bool = True) -> bool: ...
```

---

## Especificación detallada por módulo y función

### 1. Módulo `sciref.numeric`

#### `weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float`

- **Contrato:** calcula la media ponderada `sum(w_i * v_i) / sum(w_i)`.
- **Parámetros:**
  - `values: Sequence[float]` — valores numéricos de entrada.
  - `weights: Sequence[float]` — pesos no negativos asociados a cada valor.
- **Retorno:** `float`.
- **Excepciones:**
  - `ValueError` si `values` está vacía (`len(values) == 0`).
  - `ValueError` si `len(values) != len(weights)`.
  - `ValueError` si algún peso es negativo (`w < 0`).
  - `ValueError` si la suma total de pesos es cero (`sum(weights) == 0`).
- **Casos frontera:**
  - Se permiten pesos individuales iguales a `0` siempre que `sum(weights) > 0`.
  - Una secuencia de longitud `1` con peso positivo devuelve `float(values[0])`.
  - `values` puede contener valores negativos o `0`.

#### `clamp(x: float, lo: float, hi: float) -> float`

- **Contrato:** acota `x` al intervalo `[lo, hi]`; devuelve `float(lo)` si `x < lo`, `float(hi)` si `x > hi` y `float(x)` en caso contrario.
- **Parámetros:**
  - `x: float` — valor a acotar.
  - `lo: float` — límite inferior del intervalo.
  - `hi: float` — límite superior del intervalo.
- **Retorno:** `float`.
- **Excepciones:**
  - `ValueError` si `lo > hi`.
- **Casos frontera:**
  - `x == lo` devuelve `float(lo)`.
  - `x == hi` devuelve `float(hi)`.
  - `lo == hi` es válido y devuelve `float(lo)`.

#### `normalize_minmax(values: Sequence[float]) -> list[float]`

- **Contrato:** normaliza cada elemento al rango `[0.0, 1.0]` mediante `(v - min) / (max - min)`.
- **Parámetros:**
  - `values: Sequence[float]` — serie numérica a normalizar.
- **Retorno:** nueva `list[float]` de la misma longitud que `values`.
- **Excepciones:**
  - `ValueError` si `values` está vacía (`len(values) == 0`).
- **Casos frontera:**
  - Si todos los elementos son iguales (`max == min`, incluido el caso de longitud `1`), devuelve `[0.0] * len(values)` (sin `ZeroDivisionError`).
  - No muta la secuencia original.

---

### 2. Módulo `sciref.signals`

#### `moving_average(values: Sequence[float], window: int) -> list[float]`

- **Contrato:** calcula la media aritmética de cada ventana contigua de tamaño `window`; la salida tiene longitud `len(values) - window + 1`.
- **Parámetros:**
  - `values: Sequence[float]` — serie numérica de entrada.
  - `window: int` — tamaño de la ventana móvil.
- **Retorno:** `list[float]`.
- **Excepciones:**
  - `ValueError` si `values` está vacía (`len(values) == 0`).
  - `ValueError` si `window < 1`.
  - `ValueError` si `window > len(values)`.
- **Casos frontera:**
  - `window == 1` devuelve `[float(v) for v in values]`.
  - `window == len(values)` devuelve `[sum(values) / len(values)]` (lista de longitud `1`).
  - No muta la secuencia original.

#### `threshold_crossings(values: Sequence[float], threshold: float) -> list[int]`

- **Contrato:** devuelve los índices `i` en orden ascendente (`1 <= i < len(values)`) donde ocurre un cruce ascendente del umbral, es decir, `values[i - 1] < threshold <= values[i]`.
- **Parámetros:**
  - `values: Sequence[float]` — serie numérica de entrada.
  - `threshold: float` — umbral de comparación.
- **Retorno:** `list[int]`.
- **Excepciones:** ninguna para entradas válidas (`Sequence[float]`, `float`).
- **Casos frontera:**
  - Una serie de `0` o `1` elementos devuelve `[]`.
  - El índice `0` nunca se incluye (no compara contra `values[-1]`).
  - `values[i - 1] < threshold` y `values[i] == threshold` **sí** cuenta como cruce.
  - `values[i - 1] == threshold` y `values[i] >= threshold` **no** cuenta como cruce.
  - Un flanco descendente (`values[i - 1] >= threshold > values[i]`) **no** cuenta como cruce.

---

### 3. Módulo `sciref.validation`

#### `validate_range(value: float, lo: float, hi: float, inclusive: bool = True) -> bool`

- **Contrato:** devuelve `True` si `lo <= value <= hi` cuando `inclusive=True` (intervalo cerrado) o si `lo < value < hi` cuando `inclusive=False` (intervalo abierto); devuelve `False` en caso contrario.
- **Parámetros:**
  - `value: float` — valor a validar.
  - `lo: float` — límite inferior.
  - `hi: float` — límite superior.
  - `inclusive: bool = True` — indica si los extremos se consideran incluidos.
- **Retorno:** `bool`.
- **Excepciones:**
  - `TypeError` si `value`, `lo` o `hi` es de tipo `bool` o no es numérico (`int` / `float`, por ejemplo `str` o `None`).
  - `ValueError` si `value`, `lo` o `hi` es `NaN` (`math.isnan(...)`), o si `lo > hi`.
- **Casos frontera:**
  - Precedencia de validación: `TypeError` se evalúa antes que `ValueError`.
  - `value == lo` y `value == hi` devuelven `True` con `inclusive=True` y `False` con `inclusive=False`.
  - Si `lo == hi`: solo `value == lo` con `inclusive=True` devuelve `True`; con `inclusive=False` siempre devuelve `False`.
  - El parámetro `inclusive` puede pasarse de forma posicional o por nombre (`inclusive=False`).
