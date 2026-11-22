"""Defective seed loader and composite ProposalSource adapters (CG-08)."""

import re
from collections.abc import Sequence
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from codeguard.domain import (
    FunctionContract,
    ProposalSourceKind,
    RejectionReason,
    SpecError,
    TestProposal,
)
from codeguard.ports.generation import ProposalSource

_SAFE_FILE_NAME = re.compile(r"^[A-Za-z_]\w*\.py$", re.ASCII)


def _require_non_blank(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"'{field_name}' must not be empty")
    return value


class DefectiveSeedSchema(BaseModel):
    """Validation schema for one defective seed entry in ``seeds_defective.yaml``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    case_ids: list[str] = Field(min_length=1)
    target_module: str
    target_function: str
    file_name: str
    expected_reason: RejectionReason
    description: str
    code: str

    @field_validator("id", "target_module", "target_function", "description", "code")
    @classmethod
    def _validate_non_blank_strings(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field")
        return _require_non_blank(value, str(field_name))

    @field_validator("case_ids")
    @classmethod
    def _validate_case_ids(cls, value: list[str]) -> list[str]:
        for item in value:
            _require_non_blank(item, "case_ids[]")
        return value

    @field_validator("file_name")
    @classmethod
    def _validate_file_name(cls, value: str) -> str:
        if not _SAFE_FILE_NAME.match(value):
            raise ValueError(f"unsafe seed file_name: {value!r}")
        return value


class DefectiveSeedsFileSchema(BaseModel):
    """Top-level schema for ``specs/seeds_defective.yaml``."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    package: str
    seeds: list[DefectiveSeedSchema] = Field(min_length=1)

    @field_validator("package")
    @classmethod
    def _validate_package(cls, value: str) -> str:
        return _require_non_blank(value, "package")


class DefectiveSeedProposalSource:
    """``ProposalSource`` loading deliberate defective seeds from YAML (CG-08)."""

    def __init__(self, seeds_path: Path) -> None:
        self._seeds_path = Path(seeds_path)

    def generate(self, contracts: Sequence[FunctionContract]) -> tuple[TestProposal, ...]:
        """Load, validate, and convert defective seeds into ``TestProposal`` objects."""
        raw = _read_yaml(self._seeds_path)
        try:
            doc = DefectiveSeedsFileSchema.model_validate(raw)
        except ValidationError as error:
            raise SpecError(_format_validation_error(self._seeds_path, error)) from error
        _validate_unique_seed_ids(doc.seeds, self._seeds_path)
        if contracts:
            _validate_case_references(doc.seeds, contracts, self._seeds_path)
        return tuple(_to_proposal(doc.package, seed) for seed in doc.seeds)


class CompositeProposalSource:
    """Combines multiple ``ProposalSource`` strategies into a single proposal batch."""

    def __init__(self, sources: Sequence[ProposalSource]) -> None:
        if not sources:
            raise ValueError("CompositeProposalSource needs at least one source")
        self._sources = tuple(sources)

    def generate(self, contracts: Sequence[FunctionContract]) -> tuple[TestProposal, ...]:
        """Generate proposals from every configured source in order."""
        return tuple(
            proposal for source in self._sources for proposal in source.generate(contracts)
        )


def _read_yaml(path: Path) -> dict[str, object]:
    if not path.exists():
        raise SpecError(f"Defective seeds file not found: {path}")
    if path.is_dir():
        raise SpecError(f"Defective seeds path is a directory, expected a YAML file: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise SpecError(f"Failed to parse defective seeds YAML in '{path}': {error}") from error
    if not isinstance(raw, dict):
        raise SpecError(f"Defective seeds file '{path}' must have a YAML mapping at root level")
    return raw


def _format_validation_error(path: Path, error: ValidationError) -> str:
    details = [
        f"{'.'.join(str(part) for part in item['loc']) or '<root>'}: {item['msg']}"
        for item in error.errors()
    ]
    return f"Invalid defective seeds specification in '{path}': {'; '.join(details)}"


def _validate_unique_seed_ids(seeds: Sequence[DefectiveSeedSchema], path: Path) -> None:
    seen: set[str] = set()
    for seed in seeds:
        if seed.id in seen:
            raise SpecError(f"Duplicate seed id '{seed.id}' in '{path}'")
        seen.add(seed.id)


def _validate_case_references(
    seeds: Sequence[DefectiveSeedSchema],
    contracts: Sequence[FunctionContract],
    path: Path,
) -> None:
    known_case_ids = {case.case_id for contract in contracts for case in contract.cases}
    for seed in seeds:
        unknown = [case_id for case_id in seed.case_ids if case_id not in known_case_ids]
        if unknown:
            joined = ", ".join(unknown)
            raise SpecError(f"Seed '{seed.id}' in '{path}' references unknown case_id(s): {joined}")


def _resolve_module_name(package: str, module: str) -> str:
    if module == package or module.startswith(f"{package}."):
        return module
    return f"{package}.{module}"


def _to_proposal(package: str, seed: DefectiveSeedSchema) -> TestProposal:
    return TestProposal(
        proposal_id=seed.id,
        target_module=_resolve_module_name(package, seed.target_module),
        target_function=seed.target_function,
        source=ProposalSourceKind.DEFECTIVE_SEED,
        code=seed.code.rstrip("\n") + "\n",
        case_ids=tuple(seed.case_ids),
        file_name=seed.file_name,
    )
