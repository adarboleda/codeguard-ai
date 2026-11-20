"""Pydantic schemas for validating ``specs/contracts.yaml`` (CG-06)."""

from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from codeguard.domain import CaseKind

_KIND_ALIASES: dict[str, CaseKind] = {
    "normal": CaseKind.NORMAL,
    "frontera": CaseKind.BOUNDARY,
    "boundary": CaseKind.BOUNDARY,
    "invalido": CaseKind.INVALID,
    "inválido": CaseKind.INVALID,
    "invalid": CaseKind.INVALID,
}


def _require_non_blank(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"'{field_name}' must not be empty")
    return value


class ContractCaseSchema(BaseModel):
    """Validation schema for one contract test case."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    inputs: dict[str, object]
    expected: object = None
    raises: str | None = None
    oracle: str
    rel_tol: float | None = None
    witness_for: list[str] = Field(default_factory=list)
    equivalent_to: list[str] = Field(default_factory=list)

    @field_validator("id", "oracle")
    @classmethod
    def _validate_non_blank_fields(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field")
        return _require_non_blank(value, str(field_name))

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _KIND_ALIASES:
            allowed = ", ".join(sorted(_KIND_ALIASES))
            raise ValueError(f"invalid case kind '{value}'; expected one of: {allowed}")
        return normalized

    @model_validator(mode="after")
    def _validate_expectation_and_tolerance(self) -> Self:
        has_expected = "expected" in self.model_fields_set
        has_raises = "raises" in self.model_fields_set
        if has_expected and has_raises:
            raise ValueError("case cannot define both 'expected' and 'raises'")
        if not has_expected and not has_raises:
            raise ValueError("case must define either 'expected' or 'raises'")
        if has_raises and (self.raises is None or not self.raises.strip()):
            raise ValueError("'raises' must be a non-empty exception class name")
        if self.rel_tol is not None and self.rel_tol < 0.0:
            raise ValueError("'rel_tol' must be non-negative")
        return self

    def parsed_kind(self) -> CaseKind:
        """Map the validated YAML kind label to the domain ``CaseKind`` enum."""
        return _KIND_ALIASES[self.kind]


class FunctionSpecSchema(BaseModel):
    """Validation schema for one function contract block."""

    model_config = ConfigDict(extra="forbid")

    name: str
    module: str
    signature: str
    contract: str
    notes: str | None = None
    cases: list[ContractCaseSchema] = Field(min_length=1)

    @field_validator("name", "module", "signature", "contract")
    @classmethod
    def _validate_required_strings(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field")
        return _require_non_blank(value, str(field_name))


class ContractsFileSchema(BaseModel):
    """Top-level schema for ``specs/contracts.yaml``."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    package: str
    responsable: str | None = None
    revisor: str | None = None
    fecha: date | str | None = None
    fecha_revision: date | str | None = None
    estado_revision: str | None = None
    functions: list[FunctionSpecSchema] = Field(min_length=1)

    @field_validator("package")
    @classmethod
    def _validate_package(cls, value: str) -> str:
        return _require_non_blank(value, "package")
