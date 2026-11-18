# CodeGuard AI

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

## Cómo trabajamos

- GitHub Flow: `main` protegida; una rama por historia (`feat/CG-09-validator-syntax`), PR con 1 aprobación y squash merge.
- Commits con [Conventional Commits](https://www.conventionalcommits.org/): `feat(validator): reject tautological asserts (CG-11)`.
- Nunca se suben `.env`, claves ni `out/`. Copia `.env.example` a `.env` para usar la extensión opcional con Groq.

Plan completo: [docs/plan-de-proyecto.md](docs/plan-de-proyecto.md).

## Equipo

Abner · Christian · Marcelo

## Licencia

[MIT](LICENSE)
