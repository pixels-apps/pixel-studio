---
name: pyronaut-cli
description: Run, test, validate, install, process, and troubleshoot Pyronaut projects with the pyronaut CLI and its delegated toolchain.
---

# Pyronaut CLI

Use this skill when running Pyronaut commands, validating configuration, debugging generated manifests, or working with test resources.

## Command Model

The `pyronaut` command is a Python orchestrator. It delegates to focused tools for install, processing, run, test, native build, config validation, and test-resources server management.

From the project root, `--project-dir .` is unnecessary because the CLI defaults to the current directory.

## Common Workflow

Use this sequence after creating or changing a project:

```bash
pyronaut install
pyronaut validate-config
pyronaut process
pyronaut test
```

Use `pyronaut run` to launch the application.

## Commands

- `pyronaut install`: resolves dependencies, writes scoped manifests under `__pyronaut__/`, materializes TOML schemas, and generates IDE stubs.
- `pyronaut process`: processes `src/` and `tests/` sources into `__pyronaut__/classes` and `__pyronaut__/test-classes`.
- `pyronaut run`: validates config for the `run` scenario, performs install/process preflight, starts the app, and manages test resources when enabled.
- `pyronaut test`: validates config for the `test` scenario, performs install/process preflight, runs the configured JUnit and/or pytest engines, and writes reports under `__pyronaut__/reports/tests`.
- `pyronaut test <file.py>`: directly compiles and runs a Python test module in memory. Direct execution currently supports JUnit 5 modules only; pytest tests require files on disk and must be run with project-mode `pyronaut test`.
- `pyronaut validate-config --scenario run|test|production`: validates lifecycle configuration for a specific scenario and writes reports under `__pyronaut__/reports/config-validation/<scenario>`.
- `pyronaut test-resources-server start|status|stop`: manages a reusable test-resources server. `run` and `test` can also start an owned server automatically when test resources are enabled.

`pyronaut run` and `pyronaut test` validate by default. Use `--no-validate` only for short diagnostics where validation itself is the blocker.

## Troubleshooting

- If imports from Micronaut or Jakarta packages fail in the editor, run `pyronaut install` so `__pyronaut__/ide-stubs` and editor settings are refreshed.
- If dependency changes are not reflected, run `pyronaut install --refresh`.
- If cache state looks corrupt, run `pyronaut install --no-cache`.
- For delegation diagnostics, set `PYRONAUT_TRACE_DELEGATION=true`.
- Do not edit generated manifests, processed classes, schemas, or reports under `__pyronaut__/`; change source files or `pyproject.toml` and rerun the relevant command.
