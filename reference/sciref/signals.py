"""Signal processing reference functions."""

from collections.abc import Sequence


def moving_average(values: Sequence[float], window: int) -> list[float]:
    """Compute the simple moving average over contiguous windows of size ``window``.

    Args:
        values: Non-empty sequence of numeric values (never mutated).
        window: Window length satisfying ``1 <= window <= len(values)``.

    Returns:
        ``list[float]`` of length ``len(values) - window + 1``.

    Raises:
        ValueError: If ``values`` is empty, ``window < 1``, or ``window > len(values)``.
    """
    n = len(values)
    if window < 1 or window > n:
        raise ValueError("values must not be empty and window must satisfy 1 <= window <= n")
    return [sum(values[i : i + window]) / window for i in range(n - window + 1)]


def threshold_crossings(values: Sequence[float], threshold: float) -> list[int]:
    """Return indices ``i >= 1`` where ``values[i - 1] < threshold <= values[i]``.

    Args:
        values: Sequence of numeric values (never mutated).
        threshold: Upward crossing threshold.

    Returns:
        Ascending ``list[int]`` of crossing indices (empty if ``len(values) < 2``).
    """
    return [i for i in range(1, len(values)) if values[i - 1] < threshold <= values[i]]
