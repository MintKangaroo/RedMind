# Architecture

## Current state

The foundation consists of a typed Python package under `src/redmind`, unit tests, and
a CI quality gate. It has no runtime or network boundary.

## Intended boundaries

Future work may introduce `apps/api`, `apps/worker`, and packages for core, domain,
and integrations. Domain policy must not depend on FastAPI, SQLAlchemy, Celery, or vendor
SDKs. Infrastructure adapters will depend inward on domain interfaces.

## Quality attributes

Security defaults are deny-by-default. Inputs are validated at trust boundaries,
errors use a stable machine-readable envelope, logs are structured and redacted, and
external processes receive argument arrays rather than interpolated shell commands.

