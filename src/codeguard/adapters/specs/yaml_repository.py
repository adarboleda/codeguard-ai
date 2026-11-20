"""YAML + Pydantic SpecRepository with ``inspect.signature`` verification (CG-06)."""

import ast
import importlib
import inspect
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import yaml
from pydantic import ValidationError

from codeguard.adapters.specs.schemas import ContractsFileSchema, FunctionSpecSchema
from codeguard.domain import ContractCase, FunctionContract, SpecError


class YamlSpecRepository:
    """Loads contract YAML files, validates schemas, and verifies signatures against Python code."""

    def __init__(
        self,
        specs_path: Path,
        search_paths: Sequence[Path] = (),
        *,
        verify_signatures: bool = True,
    ) -> None:
        self._specs_path = Path(specs_path)
        self._search_paths = tuple(Path(path).resolve() for path in search_paths)
        self._verify_signatures = verify_signatures

    def load(self) -> tuple[FunctionContract, ...]:
        """Read, validate, and convert ``specs_path`` into immutable domain contracts."""
        raw = _read_yaml(self._specs_path)
        try:
            doc = ContractsFileSchema.model_validate(raw)
        except ValidationError as error:
            raise SpecError(_format_validation_error(self._specs_path, error)) from error
        contracts = _build_contracts(doc)
        if self._verify_signatures:
            _verify_all_signatures(contracts, self._search_paths)
        return contracts


def _read_yaml(path: Path) -> dict[str, object]:
    if not path.exists():
        raise SpecError(f"Specifications file not found: {path}")
    if path.is_dir():
        raise SpecError(f"Specifications path is a directory, expected a YAML file: {path}")
    try:
        text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text)
    except (OSError, yaml.YAMLError) as error:
        raise SpecError(f"Failed to parse YAML specifications in '{path}': {error}") from error
    if not isinstance(raw, dict):
        raise SpecError(f"Specifications file '{path}' must have a YAML mapping at root level")
    return raw


def _format_validation_error(path: Path, error: ValidationError) -> str:
    details = []
    for item in error.errors():
        loc = ".".join(str(part) for part in item["loc"]) or "<root>"
        details.append(f"{loc}: {item['msg']}")
    joined = "; ".join(details)
    return f"Invalid contract specification in '{path}': {joined}"


def _resolve_module_name(package: str, module: str) -> str:
    if module == package or module.startswith(f"{package}."):
        return module
    return f"{package}.{module}"


def _to_contract(package: str, spec: FunctionSpecSchema) -> FunctionContract:
    cases = tuple(
        ContractCase(
            case_id=case.id,
            kind=case.parsed_kind(),
            description=case.oracle,
            inputs=case.inputs,
            expected=case.expected,
            expected_exception=case.raises,
            rel_tol=case.rel_tol,
        )
        for case in spec.cases
    )
    docstring = f"{spec.contract}\n{spec.notes}" if spec.notes else spec.contract
    return FunctionContract(
        module=_resolve_module_name(package, spec.module),
        name=spec.name,
        signature=spec.signature,
        docstring=docstring,
        cases=cases,
    )


def _build_contracts(doc: ContractsFileSchema) -> tuple[FunctionContract, ...]:
    contracts: list[FunctionContract] = []
    seen_functions: set[str] = set()
    for spec in doc.functions:
        try:
            contract = _to_contract(doc.package, spec)
        except ValueError as error:
            raise SpecError(
                f"Invalid contract domain rule for '{spec.module}.{spec.name}': {error}"
            ) from error
        if contract.qualified_name in seen_functions:
            raise SpecError(f"Duplicate function contract: '{contract.qualified_name}'")
        seen_functions.add(contract.qualified_name)
        contracts.append(contract)
    return tuple(contracts)


@contextmanager
def _import_context(search_paths: Sequence[Path]) -> Iterator[None]:
    previous_sys_path = list(sys.path)
    previous_dont_write = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        for path in reversed(search_paths):
            path_str = str(path)
            if path_str not in sys.path:
                sys.path.insert(0, path_str)
        importlib.invalidate_caches()
        yield
    finally:
        sys.path[:] = previous_sys_path
        sys.dont_write_bytecode = previous_dont_write


def _verify_all_signatures(
    contracts: tuple[FunctionContract, ...],
    search_paths: Sequence[Path],
) -> None:
    with _import_context(search_paths):
        for contract in contracts:
            _verify_contract_signature(contract)


def _verify_contract_signature(contract: FunctionContract) -> None:
    try:
        module = importlib.import_module(contract.module)
    except ImportError as error:
        raise SpecError(
            f"Cannot import module '{contract.module}' for '{contract.qualified_name}': {error}"
        ) from error

    target = getattr(module, contract.name, None)
    if target is None or not callable(target):
        raise SpecError(f"Function '{contract.name}' does not exist in module '{contract.module}'")

    declared_params, declared_defaults = _parse_declared_signature(
        contract.signature, contract.name
    )
    real_sig = inspect.signature(target)
    real_params = list(real_sig.parameters.keys())
    if declared_params != real_params:
        raise SpecError(
            f"Signature mismatch for '{contract.qualified_name}': "
            f"declared parameters {declared_params}, "
            f"actual signature is '{contract.name}{real_sig}'"
        )
    _check_defaults(contract, declared_defaults, real_sig)
    _check_case_bindings(contract, real_sig)


def _parse_declared_signature(
    signature: str, expected_name: str
) -> tuple[list[str], dict[str, ast.expr]]:
    try:
        tree = ast.parse(f"def {signature}: pass")
    except SyntaxError as error:
        raise SpecError(f"Invalid signature syntax '{signature}': {error.msg}") from error
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise SpecError(f"Invalid function signature declaration: '{signature}'")
    func_def = tree.body[0]
    if func_def.name != expected_name:
        raise SpecError(
            f"Signature name '{func_def.name}' does not match function name '{expected_name}'"
        )
    positional = [*func_def.args.posonlyargs, *func_def.args.args]
    param_names = [arg.arg for arg in positional]
    offset = len(positional) - len(func_def.args.defaults)
    defaults: dict[str, ast.expr] = {
        positional[offset + idx].arg: expr for idx, expr in enumerate(func_def.args.defaults)
    }
    for arg, kw_default in zip(func_def.args.kwonlyargs, func_def.args.kw_defaults, strict=True):
        param_names.append(arg.arg)
        if kw_default is not None:
            defaults[arg.arg] = kw_default
    return param_names, defaults


def _check_defaults(
    contract: FunctionContract,
    declared_defaults: dict[str, ast.expr],
    real_sig: inspect.Signature,
) -> None:
    for param_name, param in real_sig.parameters.items():
        has_real = param.default is not inspect.Parameter.empty
        has_decl = param_name in declared_defaults
        if has_real != has_decl:
            raise SpecError(
                f"Default value mismatch for '{param_name}' in '{contract.qualified_name}': "
                f"declared default={has_decl}, actual default={has_real}"
            )
        if not has_decl:
            continue
        try:
            decl_value = ast.literal_eval(declared_defaults[param_name])
        except (ValueError, SyntaxError):
            continue
        if type(decl_value) is not type(param.default) or decl_value != param.default:
            raise SpecError(
                f"Default value mismatch for '{param_name}' in '{contract.qualified_name}': "
                f"declared={decl_value!r}, actual={param.default!r}"
            )


def _check_case_bindings(contract: FunctionContract, real_sig: inspect.Signature) -> None:
    for case in contract.cases:
        try:
            real_sig.bind(**dict(case.inputs))
        except TypeError as error:
            raise SpecError(
                f"Case '{case.case_id}' inputs do not match signature of "
                f"'{contract.qualified_name}': {error}"
            ) from error
