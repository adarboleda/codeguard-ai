"""Validation reference functions."""

import math


def validate_range(value: float, lo: float, hi: float, inclusive: bool = True) -> bool:
    """Check whether ``value`` lies within ``[lo, hi]`` or ``(lo, hi)``.

    Args:
        value: Numeric value to check (not ``bool``).
        lo: Lower bound (not ``bool``).
        hi: Upper bound (not ``bool``).
        inclusive: Closed interval if ``True``, open interval if ``False``.

    Returns:
        ``True`` if ``value`` falls inside the specified interval, else ``False``.

    Raises:
        TypeError: If ``value``, ``lo``, or ``hi`` is ``bool`` or non-numeric.
        ValueError: If any numeric argument is ``NaN``, or if ``lo > hi``.
    """
    for arg in (value, lo, hi):
        if isinstance(arg, bool) or not isinstance(arg, (int, float)):
            raise TypeError("value, lo, and hi must be real numbers (not bool)")
    if any(math.isnan(arg) for arg in (value, lo, hi)):
        raise ValueError("value, lo, and hi must not be NaN")
    if lo > hi:
        raise ValueError("lo must be less than or equal to hi")
    if inclusive:
        return bool(lo <= value <= hi)
    return bool(lo < value < hi)
