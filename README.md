# CodeGuard AI

[![CI](https://github.com/adarboleda/codeguard-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/adarboleda/codeguard-ai/actions/workflows/ci.yml)

Herramienta CLI en Python que genera pruebas `pytest` desde contratos YAML, las filtra, las ejecuta con cobertura de líneas y ramas, las enfrenta a mutantes controlados y emite alertas estáticas para `eval` y `shell=True`. Todo se exporta a JSON, CSV y HTML y se reproduce con un solo comando.

> **Estado:** Sprint 0, infraestructura. La instalación, los comandos y la reproducción paso a paso se documentan en CG-26.

## Estructura

```text
src/codeguard/      domain/ application/ ports/ adapters/ cli/ templates/
reference/sciref/   paquete bajo estudio (nunca se modifica)
specs/              contratos YAML y semillas defectuosas
mutants/            catálogo de mutantes
samples/security/   ejemplos seguros e inseguros para las reglas estáticas
tests/              pruebas del propio CodeGuard
docs/               plan, informe y presentación
```

## Entorno de desarrollo

Requisitos: Python 3.12 y [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras          # crea .venv con las versiones exactas de uv.lock
uv run pre-commit install     # activa los hooks (ruff, mypy, gitleaks) en cada commit
uv run pre-commit run --all-files
uv run pytest
```

Antes de cada PR: `uv run ruff check .`, `uv run ruff format .`, `uv run mypy` y `uv run pytest` deben pasar; la CI repite lo mismo en Ubuntu y Windows y además corre gitleaks sobre el historial.

## Cómo trabajamos

- GitHub Flow: `main` protegida; una rama por historia (`feat/CG-09-validator-syntax`), PR con 1 aprobación y squash merge.
- Commits con [Conventional Commits](https://www.conventionalcommits.org/): `feat(validator): reject tautological asserts (CG-11)`.
- Nunca se suben `.env`, claves ni `out/`. Copia `.env.example` a `.env` para usar la extensión opcional con Groq.

Plan completo: [docs/plan-de-proyecto.md](docs/plan-de-proyecto.md).

## Equipo

Abner · Christian · Marcelo

## Licencia

[MIT](LICENSE)
