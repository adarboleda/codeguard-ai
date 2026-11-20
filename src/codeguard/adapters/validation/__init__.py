"""Validation rules (adapters of the ``ValidationRule`` port)."""

from .import_rule import ImportRule
from .syntax_rule import SyntaxRule

__all__ = ["ImportRule", "SyntaxRule"]
