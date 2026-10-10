---
name: pyronaut-project
description: Understand and modify Pyronaut project structure, pyproject.toml metadata, dependency scopes, resources, generated files, and IDE schema/stub support.
---

# Pyronaut Project

Use this skill when working in a Python project generated for Pyronaut, especially when editing `pyproject.toml`, changing project layout, adding resources, or interpreting generated files under `__pyronaut__/`.

## Project Shape

A Pyronaut project is identified by `pyproject.toml` with `[tool.pyronaut]` sections. The normal generated layout is:

- `src/`: application Python sources.
- `tests/`: pytest tests and JUnit 5 Python module tests.
- `config/`: application resources, including `application.toml`.
- `tests-config/`: test-only resources.
- `__pyronaut__/`: generated dependency manifests, processed classes, IDE stubs, schemas, reports, and local caches. Do not edit this directory by hand.
- `.micronaut/test-resources/`: test-resources client state when a reusable server is active.

Pyronaut reads directory names from `[tool.pyronaut.sources]` in `pyproject.toml`. Directory values are relative to the project root. Keep generated projects on the default layout unless the user asks to reorganize them.

## pyproject.toml

Keep the file structured around these sections:

- `[project]`: Python package name, version, and metadata.
- `[build-system]`: Python build backend metadata.
- `[tool.pyronaut]`: repositories and top-level Pyronaut options.
- `[tool.pyronaut.core]`: Micronaut Core version used by Pyronaut.
- `[tool.pyronaut.platform]`: Micronaut platform version used for managed dependencies.
- `[tool.pyronaut.sources]`: source and resource directories.
- `[tool.pyronaut.processor]`: processing mode.
- `[tool.pyronaut.ide-stubs]`: Java-backed Python stub generation.
- `[tool.pyronaut.validation]`: lifecycle configuration validation.
- `[tool.pyronaut.test-resources]`: test resources support when enabled.
- `[tool.pyronaut.dependencies]`: runtime, build, and test dependency coordinates.

Prefer kebab-case option names, such as `python-test`, `test-resources`, and `additional-modules`.

## Dependencies

Add JVM dependency coordinates in `[tool.pyronaut.dependencies]`:

- `runtime`: application runtime libraries, such as HTTP server, serde, data, security, cloud, messaging, views, and logging modules.
- `build`: annotation processors and compile-time support, such as `micronaut-serde-processor`, `micronaut-security-processor`, or `micronaut-data-processor`.
- `test`: pytest integration, JUnit 5 support, test clients, test-resources modules, and test-only libraries.

Use managed coordinates without versions when the Micronaut platform manages them. Add explicit versions only for unmanaged third-party artifacts.

Run `pyronaut install` after changing dependencies, repositories, source layout, or IDE stub settings. It refreshes scoped manifests and local schema/stub support.

## Configuration

Application configuration belongs in `config/application.toml`. Test-only configuration belongs in `tests-config/` or test environment files. Use TOML tables rather than flattened dotted keys when practical:

```toml
[micronaut.application]
name = "demo"
```

Avoid `bootstrap.properties` and `bootstrap.toml`; Pyronaut projects should use normal application configuration and exclude features that require bootstrap configuration.

## Generated Files

`pyronaut install` creates local JSON schemas and schema directives for `pyproject.toml` and `application.toml` when those files exist. It also writes IDE stubs under `__pyronaut__/ide-stubs` so imports such as `micronaut.http.annotation` and `jakarta.inject` resolve in editors. Treat those files as generated output and rerun `pyronaut install` instead of editing them.
