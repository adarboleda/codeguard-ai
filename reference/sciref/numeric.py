"""Numeric reference functions with explicit contract validation."""

from collections.abc import Sequence


def weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    """Compute the weighted arithmetic mean ``sum(w_i * v_i) / sum(w_i)``.

    Args:
        values: Non-empty sequence of numeric values.
        weights: Non-negative weights matching ``values`` in length.

    Returns:
        Weighted mean as a ``float``.

    Raises:
        ValueError: If ``values`` is empty, lengths differ, any weight is negative,
            or ``sum(weights) == 0``.
    """
    if not values:
        raise ValueError("values must not be empty")
    if len(values) != len(weights):
        raise ValueError("values and weights must have the same length")
    if any(w < 0 for w in weights):
        raise ValueError("weights must be non-negative")
    total_weight = sum(weights)
    if total_weight == 0:
        raise ValueError("sum of weights must be positive")
    weighted_sum = sum(v * w for v, w in zip(values, weights, strict=True))
    return float(weighted_sum / total_weight)


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp ``x`` to the closed interval ``[lo, hi]``.

    Args:
        x: Input value.
        lo: Lower bound (must satisfy ``lo <= hi``).
        hi: Upper bound.

    Returns:
        ``float(lo)`` if ``x < lo``, ``float(hi)`` if ``x > hi``, else ``float(x)``.

    Raises:
        ValueError: If ``lo > hi``.
    """
    if lo > hi:
        raise ValueError("lo must be less than or equal to hi")
    if x < lo:
        return float(lo)
    if x > hi:
        return float(hi)
    return float(x)


def normalize_minmax(values: Sequence[float]) -> list[float]:
    """Scale ``values`` into ``[0.0, 1.0]`` via ``(v - min) / (max - min)``.

    Args:
        values: Non-empty sequence of numeric values (never mutated).

    Returns:
        New ``list[float]``; returns all ``0.0`` if every element is equal.

    Raises:
        ValueError: If ``values`` is empty.
    """
    if not values:
        raise ValueError("values must not be empty")
    v_min = min(values)
    v_max = max(values)
    span = v_max - v_min
    if span == 0:
        return [0.0] * len(values)
    return [float((v - v_min) / span) for v in values]
