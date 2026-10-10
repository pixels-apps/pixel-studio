---
name: pyronaut-coding
description: Write idiomatic Pyronaut application code with typed Python, dataclasses, classless controllers, Micronaut annotations, Java-backed imports, dependency injection, JUnit 5 Python modules, pytest tests, and reflection-free JSON/data patterns.
---

# Pyronaut Coding

Use this skill when adding or changing Python application code in a Pyronaut project.

## Source Style

- Write typed Python. Add parameter and return type annotations for route handlers, services, clients, repositories, DTOs, entities, configuration objects, and tests.
- Prefer Python dataclasses for structured data: request bodies, response models, DTOs, configuration properties, JSON schema inputs, and data entities.
- Keep required values non-optional. Use `None` and `| None` only for values that are genuinely optional or framework-populated, such as generated IDs and timestamps.
- Use `@Serdeable` on dataclasses that cross JSON or HTTP boundaries. Add `@JsonSchema` when schema generation is part of the feature.
- Use `@MappedEntity` plus `typing.Annotated` metadata for Micronaut Data entities.
- Keep module names snake_case under `src/<package>/`.

## Controllers And Beans

Prefer classless route modules for simple HTTP routes:

```python
from typing import Annotated

from jakarta.inject import Inject
from micronaut.http.annotation import Body, Get, Post

from .services import MessageService, Person

message_service: Annotated[MessageService, Inject]

@Get(value="/hello/{name}", produces="application/json")
def hello(name: str) -> dict[str, str]:
    return {"message": message_service.say_hello(name)}

@Post(value="/hello")
def create(person: Annotated[Person, Body]) -> Person:
    return person
```

Move business logic into injected services. Use classes when the Micronaut feature requires a type, such as clients, filters, repositories, configuration properties, MCP tools, or framework interfaces.

Constructor injection is preferred for class beans. Module-level injection with `Annotated[Type, Inject]` is idiomatic for classless route modules.

## Imports

Import Java-backed Micronaut APIs through the generated Python package names:

- Use `from micronaut.http.annotation import Get`, not `from io.micronaut.http.annotation import Get`.
- Use `from micronaut.serde.annotation import Serdeable`.
- Use `from jakarta.inject import Singleton` or `Inject`.
- Use `import java` and `java.type("fully.qualified.JavaType")` when a Java class is not exposed as a Python stub or needs an exact JVM type.

The Java `io.micronaut` package is exposed as the Python package `micronaut` because Python already has a standard `io` module. When a Java package segment conflicts with a Python keyword, use the generated trailing-underscore package segment, such as `from micronaut.core.async_.annotation import SingleResult`.

## Dependencies And Unsupported Patterns

Add Micronaut and Java dependencies in `pyproject.toml`, not Gradle or Maven build files. Put annotation processors in the `build` dependency scope.

Avoid Java reflection-dependent features in Pyronaut code. In particular, do not use `micronaut-jackson-databind`, `hibernate-jpa`, or `hibernate-validator` as implementation shortcuts. Prefer Micronaut Serialization, typed dataclasses, compile-time data/introspection support, and Pyronaut-compatible validation.

## Tests

Write normal pytest tests under `tests/`. Use `pyronaut.test` fixtures when a Micronaut application context is needed, and use the Pyronaut `requests` integration for HTTP requests when available.

For tests that must be run directly (for example, `pyronaut test test_main.py`), write a JUnit 5 Python module. Do not wrap the tests in a class, use `self`, add a `@Test` decorator, or add a `-> None` return annotation. Import and call `MicronautTest()` at module scope, then define ordinary `test_*` functions:

```python
from typing import Annotated

from jakarta.inject import Inject
from micronaut.context import ApplicationContext
from micronaut.test.extensions.junit5.annotation import MicronautTest

MicronautTest()
context: Annotated[ApplicationContext, Inject]

def test_root():
    assert context is not None
```

JUnit modules use JUnit lifecycle and dependency-injection semantics (`@BeforeAll`, `@BeforeEach`, and Micronaut injection). Pytest modules use pytest fixtures and hooks. Keep the styles separate; a pytest module cannot be executed through direct in-memory source execution.

Run:

```bash
pyronaut test
```

For configuration-sensitive changes, also run:

```bash
pyronaut validate-config --scenario test
```
