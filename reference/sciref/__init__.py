"""Reference scientific computing package under test by CodeGuard AI."""

from .numeric import clamp, normalize_minmax, weighted_mean
from .signals import moving_average, threshold_crossings
from .validation import validate_range

__all__ = [
    "clamp",
    "moving_average",
    "normalize_minmax",
    "threshold_crossings",
    "validate_range",
    "weighted_mean",
]
